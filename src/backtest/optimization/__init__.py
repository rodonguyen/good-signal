"""
Walk-Forward Optimization module for backtesting.

This module provides tools for parameter optimization using walk-forward analysis,
including grid search, metrics calculation, and comprehensive reporting.
"""

from src.backtest.optimization.grid_search import generate_parameter_grid
from src.backtest.optimization.metrics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_avg_win_loss,
    calculate_annualized_return,
    calculate_total_return,
)
from src.backtest.optimization.wfo_config import calculate_wfo_windows
from src.backtest.optimization.walk_forward import WalkForwardOptimizer, BacktestResult, CycleResult
from src.backtest.optimization.wfo_report import WFOReportGenerator
from src.backtest.optimization.checkpoint import CheckpointManager

__all__ = [
    "generate_parameter_grid",
    "calculate_sharpe_ratio",
    "calculate_max_drawdown",
    "calculate_win_rate",
    "calculate_avg_win_loss",
    "calculate_annualized_return",
    "calculate_total_return",
    "calculate_wfo_windows",
    "WalkForwardOptimizer",
    "BacktestResult",
    "CycleResult",
    "WFOReportGenerator",
    "CheckpointManager",
]
