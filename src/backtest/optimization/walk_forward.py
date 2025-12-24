"""
Walk-forward optimization orchestrator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd

logger = logging.getLogger(__name__)

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
from src.backtest.optimization.checkpoint import CheckpointManager


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
        checkpoint_dir: Optional[Path] = None,
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
            checkpoint_dir: Optional directory for checkpoint files (enables resume)
        """
        self.config = config
        self.strategy_type = strategy_type
        self.symbol = symbol
        self.date_windows = date_windows
        self.breakout_range = breakout_range
        self.stop_range = stop_range
        self.optimization_target = optimization_target

        # Initialize checkpoint manager if directory provided
        self.checkpoint_manager = None
        if checkpoint_dir is not None:
            self.checkpoint_manager = CheckpointManager(checkpoint_dir)
            logger.info(f"Checkpoint/resume enabled: {checkpoint_dir}")

        # Initialize data store
        logger.info(f"Initializing data store for {symbol}...")
        cache_cfg = self.config.cache
        store_cfg = OhlcvStoreConfig(
            raw_1m_dir=self.config.raw_1m_dir,
            cache_dir=str(cache_cfg.get("dir", "data/cache/backtest")),
            cache_enabled=bool(cache_cfg.get("enabled", True)),
            cache_version=str(cache_cfg.get("version", "v1")),
        )
        self.store = OhlcvStore(store_cfg)
        logger.debug(f"Data store initialized: cache_enabled={store_cfg.cache_enabled}, cache_dir={store_cfg.cache_dir}")

        # Load full dataset once
        logger.info(f"Loading data for {symbol}...")
        self.full_minute_df = self.store.load_1m(symbol)
        logger.info(f"Loaded {len(self.full_minute_df):,} 1m rows")
        logger.debug(f"Data date range: {self.full_minute_df['timestamp'].min()} to {self.full_minute_df['timestamp'].max()}")

        # Initialize strategy
        logger.info(f"Initializing strategy: {strategy_type}")
        self.strategy = _strategy_factory(strategy_type)

        # Get strategy config from backtest config
        strategy_configs = [s for s in self.config.strategies if s.get("type") == strategy_type]
        if not strategy_configs:
            raise ValueError(f"Strategy type '{strategy_type}' not found in config")
        self.strategy_cfg = strategy_configs[0]
        logger.debug(f"Strategy config loaded: {self.strategy_cfg}")

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
        logger.debug(f"Running backtest: params={params}, period={start.date()} to {end.date()}")
        # Filter data to date range
        minute_df = self._filter_data_by_date(self.full_minute_df, start, end)
        if len(minute_df) == 0:
            logger.debug(f"No data available for period {start.date()} to {end.date()}")
            return None
        logger.debug(f"Filtered data: {len(minute_df):,} rows")

        # Build filter allow map
        logger.debug("Building filter allow map...")
        filter_allow_map = self._build_filter_allow_map(minute_df)
        if filter_allow_map:
            logger.debug(f"Filter allow map created: {len(filter_allow_map)} entries")

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
        logger.debug("Generating trades...")
        trades_df = self.strategy.generate_trades(minute_df, context=ctx, params=strategy_params)

        if len(trades_df) == 0:
            logger.debug("No trades generated")
            return None
        logger.debug(f"Generated {len(trades_df)} trades")

        # Build portfolio to get equity curve
        logger.debug("Building portfolio and equity curve...")
        portfolio_cfg = self.config.portfolio_config
        if not portfolio_cfg.get("enabled", False):
            # If portfolio building disabled, use simple equity curve
            logger.debug("Portfolio building disabled, using simple equity curve")
            initial_capital = 1000.0
            trades_df = trades_df.copy()
            trades_df["portfolio_pnl"] = trades_df["net_pnl"]
            equity_curve = pd.Series(
                initial_capital + trades_df.sort_values("exit_time")["portfolio_pnl"].cumsum().values,
                index=trades_df.sort_values("exit_time")["exit_time"],
            )
        else:
            # Use PortfolioBuilder
            logger.debug("Using PortfolioBuilder for equity curve")
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
            logger.debug(f"Saved temporary trades file: {temp_file}")

            # Build portfolio
            try:
                portfolio_df = builder.build_portfolio()
                initial_capital = builder.capital_config["initial"]
                equity_curve = pd.Series(
                    portfolio_df["equity"].values,
                    index=pd.to_datetime(portfolio_df["exit_time"], utc=True),
                ).sort_index()
                logger.debug(f"Portfolio built successfully: initial_capital={initial_capital}")
            except Exception as e:
                logger.warning(f"Portfolio building failed: {e}, using simple equity curve")
                initial_capital = 1000.0
                trades_df = trades_df.copy()
                trades_df["portfolio_pnl"] = trades_df["net_pnl"]
                equity_curve = pd.Series(
                    initial_capital + trades_df.sort_values("exit_time")["portfolio_pnl"].cumsum().values,
                    index=trades_df.sort_values("exit_time")["exit_time"],
                )

        # Calculate metrics
        logger.debug("Calculating performance metrics...")
        sharpe = calculate_sharpe_ratio(equity_curve)
        total_pnl = calculate_total_pnl(trades_df)
        max_dd = calculate_max_drawdown(equity_curve)
        total_ret = calculate_total_return(equity_curve, initial_capital)
        annual_ret = calculate_annualized_return(equity_curve, initial_capital)
        win_rate = calculate_win_rate(trades_df)
        avg_win, avg_loss = calculate_avg_win_loss(trades_df)
        final_equity = equity_curve.iloc[-1] if len(equity_curve) > 0 else initial_capital

        logger.debug(f"Metrics: Sharpe={sharpe:.2f}, PnL=${total_pnl:.2f}, Return={total_ret:.2f}%, WinRate={win_rate:.1f}%")

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
        logger.info("=" * 60)
        logger.info(f"Cycle {cycle_num}")
        logger.info(f"Training: {train_start.date()} to {train_end.date()}")
        logger.info(f"Testing: {test_start.date()} to {test_end.date()}")

        # Generate parameter grid
        logger.info("Generating parameter grid...")
        param_grid = generate_parameter_grid(self.breakout_range, self.stop_range)
        total_combinations = len(param_grid)
        logger.info(f"Testing {total_combinations} parameter combinations...")

        # Run grid search on training period
        logger.info("Starting grid search on training period...")
        grid_results = []
        for i, params in enumerate(param_grid, 1):
            if i % 20 == 0:
                logger.info(f"  Progress: {i}/{len(param_grid)} ({i/len(param_grid)*100:.1f}%)")
            result = self._run_single_backtest(params, train_start, train_end)
            if result is not None:
                grid_results.append(result)

        logger.info(f"Grid search completed: {len(grid_results)} valid results out of {len(param_grid)} combinations")

        if not grid_results:
            logger.warning("No valid results from training period")
            return None

        # Select best config
        logger.info("Selecting best configuration...")
        best_config = self._select_best_config(grid_results)
        logger.info(
            f"Best config: breakout_mult={best_config.params['breakout_multiplier']:.2f}, "
            f"stop_mult={best_config.params['stop_multiplier']:.2f}, "
            f"Sharpe={best_config.sharpe:.2f}, PnL=${best_config.total_pnl:.2f}, "
            f"Return={best_config.total_return:.2f}%"
        )

        # Run test period with best config
        logger.info("Running test period with best config...")
        test_result = self._run_single_backtest(best_config.params, test_start, test_end)

        if test_result is None:
            logger.warning("No trades in test period")
            return None

        logger.info(
            f"Test period results: Sharpe={test_result.sharpe:.2f}, PnL=${test_result.total_pnl:.2f}, "
            f"Return={test_result.total_return:.2f}%, Trades={test_result.total_trades}"
        )

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
        """
        Run all walk-forward cycles with checkpoint/resume support.

        Returns:
            List of all cycle results (from checkpoints + newly completed)
        """
        total_cycles = len(self.date_windows)
        logger.info(f"Starting walk-forward optimization: {total_cycles} cycles to process")

        # Load existing checkpoints if checkpoint manager is enabled
        completed_cycles = {}
        if self.checkpoint_manager is not None:
            completed_cycles = self.checkpoint_manager.get_completed_cycles(total_cycles)
            if completed_cycles:
                logger.info(f"Resuming: {len(completed_cycles)} cycles already completed")

        # Run cycles, skipping completed ones
        cycle_results = list(completed_cycles.values())
        for i, (train_start, train_end, test_start, test_end) in enumerate(self.date_windows, 1):
            cycle_num = i

            # Skip if already completed
            if cycle_num in completed_cycles:
                logger.info(f"Skipping cycle {cycle_num}/{total_cycles} (already completed)")
                continue

            logger.info(f"Processing cycle {cycle_num}/{total_cycles}")
            result = self.run_cycle(cycle_num, train_start, train_end, test_start, test_end)

            if result is not None:
                cycle_results.append(result)

                # Save checkpoint if checkpoint manager is enabled
                if self.checkpoint_manager is not None:
                    try:
                        self.checkpoint_manager.save_cycle(result)
                        logger.info(f"Cycle {cycle_num} completed and checkpointed")
                    except Exception as e:
                        logger.error(f"Failed to save checkpoint for cycle {cycle_num}: {e}")
                else:
                    logger.info(f"Cycle {cycle_num} completed successfully")
            else:
                logger.warning(f"Cycle {cycle_num} produced no results")

        # Sort results by cycle number to ensure correct order
        cycle_results.sort(key=lambda x: x.cycle_num)

        logger.info(f"All cycles completed: {len(cycle_results)} successful out of {total_cycles}")
        return cycle_results
