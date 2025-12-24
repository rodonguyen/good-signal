"""
Walk-forward optimization orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd

from src.backtest.contracts import BacktestContext, BaseBacktestStrategy
from src.backtest.runner import BacktestConfig, _strategy_factory
from src.backtest.historical_data_provider.ohlcv_store import OhlcvStore, OhlcvStoreConfig
from src.backtest.filters.factory import load_filter_pipeline
from src.backtest.utils.crypto_day_utils import aggregate_24h_periods
from src.backtest.steps.portfolio import PortfolioBuilder
from src.backtest.optimization.grid_search import generate_parameter_grid
from src.backtest.optimization.metrics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_avg_win_loss,
    calculate_annualized_return,
    calculate_total_return,
    calculate_total_pnl,
)


@dataclass
class BacktestResult:
    """Result of a single backtest run with specific parameters."""

    params: dict[str, float]
    trades_df: pd.DataFrame
    equity_curve: pd.Series
    sharpe: float
    total_pnl: float
    max_drawdown: float
    total_return: float
    annualized_return: float
    win_rate: float
    avg_win: float
    avg_loss: float
    total_trades: int
    initial_capital: float
    final_equity: float


@dataclass
class CycleResult:
    """Result of a complete walk-forward cycle (training + testing)."""

    cycle_num: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    grid_results: list[BacktestResult]  # All parameter combinations tested
    best_config: BacktestResult  # Best config selected by Sharpe
    test_result: BacktestResult  # Out-of-sample result with best config


class WalkForwardOptimizer:
    """Walk-forward optimization engine."""

    def __init__(
        self,
        config: BacktestConfig,
        strategy_type: str,
        symbol: str,
        date_windows: list[tuple[datetime, datetime, datetime, datetime]],
        breakout_range: tuple[float, float, float] = (0.24, 0.60, 0.02),
        stop_range: tuple[float, float, float] = (0.16, 0.50, 0.02),
        optimization_target: str = "sharpe",
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            config: Backtest configuration
            strategy_type: Strategy type (e.g., 'atr_breakout')
            symbol: Trading symbol (e.g., 'ETHUSDT')
            date_windows: List of (train_start, train_end, test_start, test_end) tuples
            breakout_range: (start, end, step) for breakout_multiplier
            stop_range: (start, end, step) for stop_multiplier
            optimization_target: Metric to optimize ('sharpe', 'pnl', 'return')
        """
        self.config = config
        self.strategy_type = strategy_type
        self.symbol = symbol
        self.date_windows = date_windows
        self.breakout_range = breakout_range
        self.stop_range = stop_range
        self.optimization_target = optimization_target

        # Initialize data store
        cache_cfg = self.config.cache
        store_cfg = OhlcvStoreConfig(
            raw_1m_dir=self.config.raw_1m_dir,
            cache_dir=str(cache_cfg.get("dir", "data/cache/backtest")),
            cache_enabled=bool(cache_cfg.get("enabled", True)),
            cache_version=str(cache_cfg.get("version", "v1")),
        )
        self.store = OhlcvStore(store_cfg)

        # Load full dataset once
        print(f"Loading data for {symbol}...")
        self.full_minute_df = self.store.load_1m(symbol)
        print(f"Loaded {len(self.full_minute_df):,} 1m rows")

        # Initialize strategy
        self.strategy = _strategy_factory(strategy_type)

        # Get strategy config from backtest config
        strategy_configs = [s for s in self.config.strategies if s.get("type") == strategy_type]
        if not strategy_configs:
            raise ValueError(f"Strategy type '{strategy_type}' not found in config")
        self.strategy_cfg = strategy_configs[0]

    def _filter_data_by_date(self, df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
        """Filter DataFrame by date range."""
        if "timestamp" not in df.columns:
            return df
        
        # Convert to Timestamp and ensure UTC timezone
        # Handle both timezone-aware and naive datetime objects
        start_ts = pd.Timestamp(start)
        if start_ts.tz is None:
            start_ts = start_ts.tz_localize("UTC")
        else:
            start_ts = start_ts.tz_convert("UTC")
        
        end_ts = pd.Timestamp(end)
        if end_ts.tz is None:
            end_ts = end_ts.tz_localize("UTC")
        else:
            end_ts = end_ts.tz_convert("UTC")
        
        mask = (df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)
        return df[mask].copy()

    def _build_filter_allow_map(self, minute_df: pd.DataFrame) -> dict[str, bool]:
        """Build filter allow map if filters are enabled."""
        filter_allow_map: dict[str, bool] = {}
        filters_cfg = self.config.filters_config
        if filters_cfg.get("enabled", False):
            filter_config_path = filters_cfg.get("config_path", "config/backtest/filters.yaml")
            pipeline = load_filter_pipeline(filter_config_path)
            if pipeline is not None:
                signal_tf = str(self.strategy_cfg.get("signal_timeframe", "1h"))
                hourly_df = self.store.load_resampled(self.symbol, timeframe="1h")
                daily_df = aggregate_24h_periods(minute_df, day_start_hour=13)
                filter_allow_map = pipeline.build_allow_map(minute_df, hourly_df, daily_df)
        return filter_allow_map

    def _run_single_backtest(
        self,
        params: dict[str, float],
        start: datetime,
        end: datetime,
    ) -> Optional[BacktestResult]:
        """
        Run a single backtest with given parameters and date range.

        Args:
            params: Strategy parameters (breakout_multiplier, stop_multiplier, etc.)
            start: Start date
            end: End date

        Returns:
            BacktestResult or None if no trades generated
        """
        # Filter data to date range
        minute_df = self._filter_data_by_date(self.full_minute_df, start, end)
        if len(minute_df) == 0:
            return None

        # Build filter allow map
        filter_allow_map = self._build_filter_allow_map(minute_df)

        # Create context
        ctx = BacktestContext(
            symbol=self.symbol,
            fee_rate=self.config.fee_rate,
            raw_1m_dir=self.config.raw_1m_dir,
            outputs=self.config.outputs,
        )

        # Prepare strategy parameters
        signal_tf = str(self.strategy_cfg.get("signal_timeframe", "1h"))
        strategy_params = {
            "signal_timeframe": signal_tf,
            "execution_timeframe": self.strategy_cfg.get("execution_timeframe", "1m"),
            "indicator_params": (self.strategy_cfg.get("indicator", {}) or {}).get("params", {}),
            "rr_take_profit": ((self.strategy_cfg.get("execution", {}) or {}).get("rr_take_profit", 4.0)),
            "conflict_resolution": ((self.strategy_cfg.get("execution", {}) or {}).get("conflict_resolution", "stop_first")),
            "debug": False,  # Disable debug for WFO
            "filter_allow_map": filter_allow_map,
        }

        # Add strategy-specific params (merge with provided params)
        base_params = self.strategy_cfg.get("params", {}) or {}
        strategy_params.update(base_params)
        strategy_params.update(params)  # Override with provided params

        # Load signal bars if needed
        if signal_tf != "1m":
            hourly_df = self.store.load_resampled(self.symbol, timeframe=signal_tf)
            hourly_df = self._filter_data_by_date(hourly_df, start, end)
            strategy_params["_signal_bars"] = hourly_df

        # Generate trades
        trades_df = self.strategy.generate_trades(minute_df, context=ctx, params=strategy_params)

        if len(trades_df) == 0:
            return None

        # Build portfolio to get equity curve
        portfolio_cfg = self.config.portfolio_config
        if not portfolio_cfg.get("enabled", False):
            # If portfolio building disabled, use simple equity curve
            initial_capital = 1000.0
            trades_df = trades_df.copy()
            trades_df["portfolio_pnl"] = trades_df["net_pnl"]
            equity_curve = pd.Series(
                initial_capital + trades_df.sort_values("exit_time")["portfolio_pnl"].cumsum().values,
                index=trades_df.sort_values("exit_time")["exit_time"],
            )
        else:
            # Use PortfolioBuilder
            portfolio_config_path = portfolio_cfg.get("config_path", "config/backtest/portfolio_config.yaml")
            builder = PortfolioBuilder(config_path=portfolio_config_path)
            builder.paths["trades_dir"] = str(Path(self.config.outputs["trades_dir"]) / "wfo_temp")
            builder.paths["filtered_dir"] = str(Path(self.config.outputs["trades_dir"]) / "wfo_temp")
            builder.paths["use_filtered"] = False
            builder.symbols = [self.symbol]

            # Save trades temporarily
            temp_dir = Path(self.config.outputs["trades_dir"]) / "wfo_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / f"{self.symbol}_trades.csv"
            trades_df.to_csv(temp_file, index=False)

            # Build portfolio
            try:
                portfolio_df = builder.build_portfolio()
                initial_capital = builder.capital_config["initial"]
                equity_curve = pd.Series(
                    portfolio_df["equity"].values,
                    index=pd.to_datetime(portfolio_df["exit_time"], utc=True),
                ).sort_index()
            except Exception as e:
                print(f"Warning: Portfolio building failed: {e}, using simple equity curve")
                initial_capital = 1000.0
                trades_df = trades_df.copy()
                trades_df["portfolio_pnl"] = trades_df["net_pnl"]
                equity_curve = pd.Series(
                    initial_capital + trades_df.sort_values("exit_time")["portfolio_pnl"].cumsum().values,
                    index=trades_df.sort_values("exit_time")["exit_time"],
                )

        # Calculate metrics
        sharpe = calculate_sharpe_ratio(equity_curve)
        total_pnl = calculate_total_pnl(trades_df)
        max_dd = calculate_max_drawdown(equity_curve)
        total_ret = calculate_total_return(equity_curve, initial_capital)
        annual_ret = calculate_annualized_return(equity_curve, initial_capital)
        win_rate = calculate_win_rate(trades_df)
        avg_win, avg_loss = calculate_avg_win_loss(trades_df)
        final_equity = equity_curve.iloc[-1] if len(equity_curve) > 0 else initial_capital

        return BacktestResult(
            params=params,
            trades_df=trades_df,
            equity_curve=equity_curve,
            sharpe=sharpe,
            total_pnl=total_pnl,
            max_drawdown=max_dd,
            total_return=total_ret,
            annualized_return=annual_ret,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_trades=len(trades_df),
            initial_capital=initial_capital,
            final_equity=final_equity,
        )

    def _select_best_config(self, results: list[BacktestResult]) -> Optional[BacktestResult]:
        """Select best configuration based on optimization target."""
        if not results:
            return None

        if self.optimization_target == "sharpe":
            return max(results, key=lambda r: r.sharpe)
        elif self.optimization_target == "pnl":
            return max(results, key=lambda r: r.total_pnl)
        elif self.optimization_target == "return":
            return max(results, key=lambda r: r.total_return)
        else:
            raise ValueError(f"Unknown optimization target: {self.optimization_target}")

    def run_cycle(
        self,
        cycle_num: int,
        train_start: datetime,
        train_end: datetime,
        test_start: datetime,
        test_end: datetime,
    ) -> Optional[CycleResult]:
        """
        Run a single walk-forward cycle.

        Args:
            cycle_num: Cycle number
            train_start: Training period start
            train_end: Training period end
            test_start: Test period start
            test_end: Test period end

        Returns:
            CycleResult or None if no valid results
        """
        print(f"\n=== Cycle {cycle_num} ===")
        print(f"Training: {train_start.date()} to {train_end.date()}")
        print(f"Testing: {test_start.date()} to {test_end.date()}")

        # Generate parameter grid
        param_grid = generate_parameter_grid(self.breakout_range, self.stop_range)
        print(f"Testing {len(param_grid)} parameter combinations...")

        # Run grid search on training period
        grid_results = []
        for i, params in enumerate(param_grid, 1):
            if i % 50 == 0:
                print(f"  Progress: {i}/{len(param_grid)}")
            result = self._run_single_backtest(params, train_start, train_end)
            if result is not None:
                grid_results.append(result)

        if not grid_results:
            print("  No valid results from training period")
            return None

        # Select best config
        best_config = self._select_best_config(grid_results)
        print(f"  Best config: breakout_mult={best_config.params['breakout_multiplier']:.2f}, "
              f"stop_mult={best_config.params['stop_multiplier']:.2f}, "
              f"Sharpe={best_config.sharpe:.2f}")

        # Run test period with best config
        print(f"  Running test period with best config...")
        test_result = self._run_single_backtest(best_config.params, test_start, test_end)

        if test_result is None:
            print("  No trades in test period")
            return None

        return CycleResult(
            cycle_num=cycle_num,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            grid_results=grid_results,
            best_config=best_config,
            test_result=test_result,
        )

    def run_all_cycles(self) -> list[CycleResult]:
        """Run all walk-forward cycles."""
        cycle_results = []
        for i, (train_start, train_end, test_start, test_end) in enumerate(self.date_windows, 1):
            result = self.run_cycle(i, train_start, train_end, test_start, test_end)
            if result is not None:
                cycle_results.append(result)
        return cycle_results

