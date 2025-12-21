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

from src.backtest.contracts import BacktestContext
from src.backtest.data.ohlcv_store import OhlcvStore, OhlcvStoreConfig
from src.backtest.strategies.bb_trendline_rr4 import BBTrendlineRR4BacktestStrategy
from src.backtest.filters.factory import load_filter_pipeline
from src.backtest.utils.crypto_day_utils import aggregate_24h_periods


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
    def symbols(self) -> list[str]:
        return list(self.raw["universe"]["symbols"])

    @property
    def strategies(self) -> list[Mapping[str, Any]]:
        return list(self.raw.get("strategies", []))

    @property
    def filters_config(self) -> Mapping[str, Any]:
        """Get filter step configuration."""
        return self.raw.get("steps", {}).get("filters", {})


def load_backtest_config(path: str | Path) -> BacktestConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return BacktestConfig(raw=raw)


def _strategy_factory(strategy_type: str):
    if strategy_type == "bb_trendline_rr4":
        return BBTrendlineRR4BacktestStrategy()
    raise ValueError(f"Unknown backtest strategy type: {strategy_type}")


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

                ctx = BacktestContext(
                    symbol=symbol,
                    fee_rate=self.config.fee_rate,
                    raw_1m_dir=self.config.raw_1m_dir,
                    outputs=self.config.outputs,
                )

                # Build filter allow_map if filters are enabled
                filter_allow_map: dict[str, bool] = {}
                filters_cfg = self.config.filters_config
                if filters_cfg.get("enabled", False):
                    filter_config_path = filters_cfg.get("config_path", "config/backtest/filters.yaml")
                    pipeline = load_filter_pipeline(filter_config_path)
                    if pipeline is not None:
                        print(f"  {symbol}: building filter allow map...")
                        # Load hourly bars for filters that need them
                        signal_tf = str(strat_cfg.get("signal_timeframe", "1h"))
                        hourly_df = None
                        if signal_tf == "1h":
                            hourly_df = self.store.load_resampled(symbol, timeframe="1h")
                        else:
                            # Load 1h anyway for filters
                            hourly_df = self.store.load_resampled(symbol, timeframe="1h")
                        
                        # Build daily bars for day-level filters
                        daily_df = aggregate_24h_periods(minute_df, day_start_hour=13)
                        
                        filter_allow_map = pipeline.build_allow_map(minute_df, hourly_df, daily_df)
                        allowed_count = sum(1 for v in filter_allow_map.values() if v)
                        print(f"  {symbol}: filter allow map: {allowed_count}/{len(filter_allow_map)} days allowed")

                # Flatten config for strategy implementation
                signal_tf = str(strat_cfg.get("signal_timeframe", "1h"))
                params = {
                    "signal_timeframe": signal_tf,
                    "execution_timeframe": strat_cfg.get("execution_timeframe", "1m"),
                    "indicator_params": (strat_cfg.get("indicator", {}) or {}).get("params", {}),
                    "rr_take_profit": ((strat_cfg.get("execution", {}) or {}).get("rr_take_profit", 4.0)),
                    "conflict_resolution": ((strat_cfg.get("execution", {}) or {}).get("conflict_resolution", "stop_first")),
                    "debug": self.config.debug,  # Pass global debug flag to strategy
                    "filter_allow_map": filter_allow_map,  # Pass filter allow map to strategy
                }

                # Provide cached signal timeframe bars (e.g., 1h) to avoid re-resampling every run.
                if signal_tf != "1m":
                    print(f"  {symbol}: loading cached {signal_tf} bars (parquet cache if available)...")
                    params["_signal_bars"] = self.store.load_resampled(symbol, timeframe=signal_tf)
                    print(f"  {symbol}: loaded {len(params['_signal_bars']):,} {signal_tf} rows")

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
