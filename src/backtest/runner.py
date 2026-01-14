"""
Backtest runner (orchestrates steps for configured strategies and symbols).

Initial scope:
- Load 1m CSV data from disk
- Run enabled strategies (starting with bb_trendline_rr4)
- Write per-symbol trade CSVs under data/trades/{strategy_id}/
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
import pandas as pd

from datetime import datetime
from src.backtest.contracts import BacktestContext
from src.backtest.data.ohlcv_store import OhlcvStore, OhlcvStoreConfig
from src.backtest.data.bybit_provider import BybitDataProvider
from src.backtest.strategies.bb_trendline_rr4 import BBTrendlineRR4BacktestStrategy
from src.backtest.strategies.atr_breakout import AtrBreakoutStrategy
from src.backtest.strategies.supertrend import SupertrendStrategy
from src.backtest.filters.factory import load_filter_pipeline
from src.backtest.utils.crypto_day_utils import aggregate_24h_periods
from src.backtest.steps.portfolio import run_portfolio_step
from src.backtest.steps.analysis import run_analysis_step


@dataclass(frozen=True)
class BacktestConfig:
    raw: Mapping[str, Any]

    @property
    def fee_rate(self) -> float:
        return float(self.raw["engine"]["fee_rate"])

    @property
    def debug(self) -> bool:
        return bool(self.raw.get("engine", {}).get("debug", False))

    @property
    def cache(self) -> Mapping[str, Any]:
        return self.raw.get("engine", {}).get("cache", {}) or {}

    @property
    def outputs(self) -> Mapping[str, str]:
        return self.raw["engine"]["outputs"]

    @property
    def raw_1m_dir(self) -> str:
        return str(self.raw["data"]["raw_1m_dir"])

    @property
    def data_config(self) -> Mapping[str, Any]:
        """Get data configuration."""
        return self.raw.get("data", {})

    @property
    def enabled_blocks(self) -> list[int]:
        """Get list of enabled block numbers (1-5)."""
        return list(self.raw.get("steps", {}).get("enabled_blocks", [1, 2, 3, 4, 5]))

    @property
    def symbols(self) -> list[str]:
        return list(self.raw["universe"]["symbols"])

    @property
    def strategies(self) -> list[Mapping[str, Any]]:
        return list(self.raw.get("strategies", []))

    @property
    def filters_config(self) -> Mapping[str, Any]:
        """Get filter step configuration."""
        return self.raw.get("steps", {}).get("filters", {})

    @property
    def portfolio_config(self) -> Mapping[str, Any]:
        """Get portfolio step configuration."""
        return self.raw.get("steps", {}).get("portfolio", {})

    @property
    def analysis_config(self) -> Mapping[str, Any]:
        """Get analysis step configuration."""
        return self.raw.get("steps", {}).get("analysis", {})


def load_backtest_config(path: str | Path) -> BacktestConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return BacktestConfig(raw=raw)


def _strategy_factory(strategy_type: str):
    if strategy_type == "bb_trendline_rr4":
        return BBTrendlineRR4BacktestStrategy()
    if strategy_type == "atr_breakout":
        return AtrBreakoutStrategy()
    if strategy_type == "supertrend":
        return SupertrendStrategy()
    raise ValueError(f"Unknown backtest strategy type: {strategy_type}")


def _run_step1_data_download(config: BacktestConfig) -> None:
    """Step 1: Download historical data if enabled.

    Downloads data for all symbols in the universe if:
    - Block 1 is enabled in enabled_blocks
    - data.download.enabled is true
    """
    data_cfg = config.data_config
    download_cfg = data_cfg.get("download", {})

    if not download_cfg.get("enabled", False):
        if config.debug:
            print("Step 1 (data download) is disabled in config.")
        return

    provider_name = download_cfg.get("provider", "bybit")
    if provider_name != "bybit":
        raise ValueError(f"Unsupported data provider: {provider_name}. Only 'bybit' is currently supported.")

    # Initialize provider
    crypto_config_path = download_cfg.get("crypto_config_path", "breakout/src/config/crypto_symbols.yaml")
    raw_data_dir = data_cfg.get("raw_dir") or data_cfg.get("raw_1m_dir", "data/raw/crypto")
    provider = BybitDataProvider(
        crypto_config_path=crypto_config_path,
        raw_data_dir=raw_data_dir,
    )

    # Parse date range
    start_date_str = download_cfg.get("start_date")
    end_date_str = download_cfg.get("end_date")

    start_date = None
    end_date = None

    if end_date_str and end_date_str not in ("null", "", None):
        end_date = datetime.strptime(str(end_date_str), "%Y-%m-%d")
    else:
        end_date = datetime.now()

    if start_date_str and start_date_str not in ("null", "", None):
        start_date = datetime.strptime(str(start_date_str), "%Y-%m-%d")
    else:
        # Default to 1 year ago if not specified
        start_date = end_date - pd.Timedelta(days=365)

    print(f"\n=== Step 1: Data Download ===")
    print(f"Provider: {provider_name}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")

    for symbol in config.symbols:
        print(f"\n  {symbol}: ensuring data exists...")
        try:
            result = provider.ensure_data(
                symbol=symbol,
                start=start_date,
                end=end_date,
                timeframe="1m",
            )
            if isinstance(result, Path):
                print(f"  {symbol}: data available at {result}")
            else:
                print(f"  {symbol}: data loaded ({len(result)} rows)")
        except Exception as e:
            print(f"  {symbol}: ERROR - {e}")
            if config.debug:
                import traceback

                traceback.print_exc()

    print(f"\n✓ Step 1 complete")


class BacktestRunner:
    def __init__(self, config: BacktestConfig):
        self.config = config
        cache_cfg = self.config.cache
        store_cfg = OhlcvStoreConfig(
            raw_1m_dir=self.config.raw_1m_dir,
            cache_dir=str(cache_cfg.get("dir", "data/cache/backtest")),
            cache_enabled=bool(cache_cfg.get("enabled", True)),
            cache_version=str(cache_cfg.get("version", "v1")),
        )
        self.store = OhlcvStore(store_cfg)

    def run(self) -> None:
        enabled_blocks = self.config.enabled_blocks

        # Step 1: Data Download
        if 1 in enabled_blocks:
            _run_step1_data_download(self.config)

        # If only step 1 is enabled, exit early
        if enabled_blocks == [1]:
            print("\n✓ Backtest complete (data download only)")
            return

        # Steps 2-5 require strategies
        out_root = Path(self.config.outputs["trades_dir"])
        out_root.mkdir(parents=True, exist_ok=True)

        enabled_strategies = [s for s in self.config.strategies if bool(s.get("enabled", True))]
        if not enabled_strategies:
            print("No enabled strategies found in config.")
            return

        for strat_cfg in enabled_strategies:
            strategy_type = str(strat_cfg["type"])
            strategy_id = str(strat_cfg.get("id", strategy_type))
            strategy = _strategy_factory(strategy_type)

            strat_out_dir = out_root / strategy_id
            strat_out_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n=== Running strategy: {strategy_id} ({strategy_type}) ===")

            for symbol in self.config.symbols:
                print(f"  {symbol}: loading 1m data...")
                minute_df = self.store.load_1m(symbol)
                print(f"  {symbol}: loaded {len(minute_df):,} 1m rows")

                # Filter by start_date and end_date if provided
                data_cfg = self.config.data_config
                start_date = data_cfg.get("start_date")
                end_date = data_cfg.get("end_date")

                if start_date or end_date:
                    original_len = len(minute_df)
                    # Ensure timestamp column is datetime
                    if 'timestamp' in minute_df.columns:
                        if minute_df['timestamp'].dtype == 'object':
                            minute_df['timestamp'] = pd.to_datetime(minute_df['timestamp'], utc=True)

                        if start_date:
                            # Ensure timezone awareness matches the data
                            start_dt = pd.to_datetime(start_date, utc=True)
                            minute_df = minute_df[minute_df['timestamp'] >= start_dt]
                            print(f"  {symbol}: filtered by start_date {start_date}")

                        if end_date:
                            # Ensure timezone awareness matches the data
                            end_dt = pd.to_datetime(end_date, utc=True) + pd.Timedelta(days=1)  # Include full end day
                            minute_df = minute_df[minute_df['timestamp'] < end_dt]
                            print(f"  {symbol}: filtered by end_date {end_date}")

                        print(f"  {symbol}: {original_len:,} -> {len(minute_df):,} rows after date filtering")

                        if len(minute_df) == 0:
                            print(f"  {symbol}: WARNING - No data in date range, skipping")
                            continue

                ctx = BacktestContext(
                    symbol=symbol,
                    fee_rate=self.config.fee_rate,
                    raw_1m_dir=self.config.raw_1m_dir,
                    outputs=self.config.outputs,
                )

                # Load filter pipeline if filters are enabled (Step 3)
                filter_pipeline = None
                filters_cfg = self.config.filters_config
                if 3 in enabled_blocks and filters_cfg.get("enabled", False):
                    filter_config_path = filters_cfg.get("config_path", "config/backtest/filters.yaml")
                    filter_pipeline = load_filter_pipeline(filter_config_path)
                    if filter_pipeline is not None:
                        print(f"  {symbol}: filter pipeline loaded with {len(filter_pipeline.rules)} rule(s)")

                # Flatten config for strategy implementation
                signal_tf = str(strat_cfg.get("signal_timeframe", "1h"))
                params = {
                    "signal_timeframe": signal_tf,
                    "execution_timeframe": strat_cfg.get("execution_timeframe", "1m"),
                    "indicator_params": (strat_cfg.get("indicator", {}) or {}).get("params", {}),
                    "rr_take_profit": ((strat_cfg.get("execution", {}) or {}).get("rr_take_profit", 4.0)),
                    "conflict_resolution": ((strat_cfg.get("execution", {}) or {}).get("conflict_resolution", "stop_first")),
                    "debug": self.config.debug,  # Pass global debug flag to strategy
                    "filter_pipeline": filter_pipeline,  # Pass filter pipeline to strategy
                }

                # Add strategy-specific params (e.g., ATR breakout params)
                strategy_params = strat_cfg.get("params", {})
                if strategy_params:
                    params.update(strategy_params)

                # Provide cached signal timeframe bars (e.g., 1h) to avoid re-resampling every run.
                if signal_tf != "1m":
                    print(f"  {symbol}: loading cached {signal_tf} bars (parquet cache if available)...")
                    signal_df = self.store.load_resampled(symbol, timeframe=signal_tf)

                    # Filter signal bars by date range too
                    if start_date or end_date:
                        original_signal_len = len(signal_df)
                        if 'timestamp' in signal_df.columns:
                            if signal_df['timestamp'].dtype == 'object':
                                signal_df['timestamp'] = pd.to_datetime(signal_df['timestamp'], utc=True)

                            if start_date:
                                start_dt = pd.to_datetime(start_date, utc=True)
                                signal_df = signal_df[signal_df['timestamp'] >= start_dt]

                            if end_date:
                                end_dt = pd.to_datetime(end_date, utc=True) + pd.Timedelta(days=1)
                                signal_df = signal_df[signal_df['timestamp'] < end_dt]

                            print(f"  {symbol}: {signal_tf} bars filtered: {original_signal_len:,} -> {len(signal_df):,} rows")

                    # Apply filters to signal DataFrame if pipeline exists
                    if filter_pipeline is not None:
                        print(f"  {symbol}: applying filters to {signal_tf} bars...")
                        signal_df = filter_pipeline.apply(signal_df)

                    params["_signal_bars"] = signal_df
                    print(f"  {symbol}: loaded {len(signal_df):,} {signal_tf} rows")

                print(f"  {symbol}: generating trades...")
                trades_df = strategy.generate_trades(minute_df, context=ctx, params=params)

                out_file = strat_out_dir / f"{symbol}_trades.csv"
                trades_df.to_csv(out_file, index=False)

                print(f"  {symbol}: {len(trades_df)} trades -> {out_file}")

            # Combined file (all symbols) for convenience
            combined = []
            for symbol in self.config.symbols:
                f = out_root / strategy_id / f"{symbol}_trades.csv"
                if f.exists():
                    combined.append(pd.read_csv(f))
            if combined:
                combined_df = pd.concat(combined, ignore_index=True)
                combined_path = out_root / strategy_id / "all_trades.csv"
                combined_df.to_csv(combined_path, index=False)
                print(f"  Combined: {len(combined_df)} trades -> {combined_path}")

            # Run portfolio builder step (Block 4)
            portfolio_cfg = self.config.portfolio_config
            portfolio_file = None
            if 4 in enabled_blocks and portfolio_cfg.get("enabled", False):
                # Required values from frontend - no defaults
                if "initial_equity" not in portfolio_cfg:
                    raise ValueError("initial_equity is required in portfolio config")
                if "risk_per_trade" not in portfolio_cfg:
                    raise ValueError("risk_per_trade is required in portfolio config")

                print(f"\n=== Building portfolio for {strategy_id} ===")
                portfolio_file = run_portfolio_step(
                    trades_dir=str(self.config.outputs["trades_dir"]),
                    portfolio_dir=str(self.config.outputs["portfolio_dir"]),
                    symbols=self.config.symbols,
                    strategy_id=strategy_id,
                    initial_equity=float(portfolio_cfg["initial_equity"]),
                    risk_per_trade=float(portfolio_cfg["risk_per_trade"]),
                )
                if portfolio_file:
                    print(f"  Portfolio built: {portfolio_file}")

            # Run portfolio analysis step (Block 5)
            analysis_cfg = self.config.analysis_config
            if 5 in enabled_blocks and analysis_cfg.get("enabled", False) and portfolio_file:
                print(f"\n=== Generating analysis report for {strategy_id} ===")
                # Get strategy params for config display (all strategies)
                strategy_params = strat_cfg.get("params", {})

                report_file = run_analysis_step(
                    portfolio_file=portfolio_file,
                    reports_dir=str(self.config.outputs["reports_dir"]),
                    raw_data_dir=self.config.raw_1m_dir,
                    trades_dir=str(self.config.outputs["trades_dir"]),
                    strategy_id=strategy_id,
                    breakout_config_path=analysis_cfg.get("breakout_config_path"),
                    strategy_config=strategy_params,
                    fee_rate=self.config.fee_rate,
                    initial_equity=float(portfolio_cfg["initial_equity"]),
                    risk_per_trade=float(portfolio_cfg["risk_per_trade"]),
                )
                if report_file:
                    print(f"  Report generated: {report_file}")
