"""
Performance metrics calculation for backtest results.
"""

import pandas as pd
import numpy as np
from typing import Tuple


def calculate_sharpe_ratio(equity_curve: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """
    Calculate Sharpe ratio from equity curve.

    Args:
        equity_curve: Series with equity values indexed by datetime
        risk_free_rate: Annual risk-free rate (default 0.0)
        periods_per_year: Number of periods per year for annualization (default 252 trading days)

    Returns:
        Sharpe ratio (annualized), or 0.0 if insufficient data or zero volatility
    """
    if len(equity_curve) < 2:
        return 0.0

    # Calculate returns
    returns = equity_curve.pct_change().dropna()

    if len(returns) == 0:
        return 0.0

    # Calculate excess returns
    excess_returns = returns - (risk_free_rate / periods_per_year)

    # Calculate mean and std
    mean_return = excess_returns.mean()
    std_return = excess_returns.std()

    if std_return == 0 or np.isnan(std_return):
        return 0.0

    # Annualize
    sharpe = (mean_return / std_return) * np.sqrt(periods_per_year)

    return float(sharpe) if not np.isnan(sharpe) else 0.0


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate maximum drawdown from equity curve.

    Args:
        equity_curve: Series with equity values indexed by datetime

    Returns:
        Maximum drawdown as a percentage (negative value, e.g., -15.5 for -15.5%)
    """
    if len(equity_curve) == 0:
        return 0.0

    # Calculate running maximum
    running_max = equity_curve.expanding().max()

    # Calculate drawdown
    drawdown = (equity_curve - running_max) / running_max * 100

    max_dd = drawdown.min()

    return float(max_dd) if not np.isnan(max_dd) else 0.0


def calculate_win_rate(trades_df: pd.DataFrame) -> float:
    """
    Calculate win rate from trades DataFrame.

    Args:
        trades_df: DataFrame with 'net_pnl' or 'portfolio_pnl' column

    Returns:
        Win rate as a percentage (0-100)
    """
    if len(trades_df) == 0:
        return 0.0

    # Use portfolio_pnl if available, otherwise net_pnl
    pnl_col = "portfolio_pnl" if "portfolio_pnl" in trades_df.columns else "net_pnl"
    if pnl_col not in trades_df.columns:
        return 0.0

    winning_trades = (trades_df[pnl_col] > 0).sum()
    total_trades = len(trades_df)

    if total_trades == 0:
        return 0.0

    win_rate = (winning_trades / total_trades) * 100

    return float(win_rate) if not np.isnan(win_rate) else 0.0


def calculate_avg_win_loss(trades_df: pd.DataFrame) -> Tuple[float, float]:
    """
    Calculate average win and average loss from trades DataFrame.

    Args:
        trades_df: DataFrame with 'net_pnl' or 'portfolio_pnl' column

    Returns:
        Tuple of (avg_win, avg_loss)
    """
    if len(trades_df) == 0:
        return 0.0, 0.0

    # Use portfolio_pnl if available, otherwise net_pnl
    pnl_col = "portfolio_pnl" if "portfolio_pnl" in trades_df.columns else "net_pnl"
    if pnl_col not in trades_df.columns:
        return 0.0, 0.0

    winning_trades = trades_df[trades_df[pnl_col] > 0][pnl_col]
    losing_trades = trades_df[trades_df[pnl_col] < 0][pnl_col]

    avg_win = float(winning_trades.mean()) if len(winning_trades) > 0 else 0.0
    avg_loss = float(losing_trades.mean()) if len(losing_trades) > 0 else 0.0

    return avg_win if not np.isnan(avg_win) else 0.0, avg_loss if not np.isnan(avg_loss) else 0.0


def calculate_annualized_return(equity_curve: pd.Series, initial_capital: float, periods_per_year: int = 252) -> float:
    """
    Calculate annualized return from equity curve.

    Args:
        equity_curve: Series with equity values indexed by datetime
        initial_capital: Initial capital amount
        periods_per_year: Number of periods per year for annualization (default 252)

    Returns:
        Annualized return as a percentage
    """
    if len(equity_curve) == 0 or initial_capital <= 0:
        return 0.0

    final_equity = equity_curve.iloc[-1]
    total_return = (final_equity / initial_capital) - 1.0

    # Calculate number of years
    if len(equity_curve) < 2:
        return 0.0

    # Estimate periods from index if datetime, otherwise use length
    if isinstance(equity_curve.index, pd.DatetimeIndex):
        time_span = (equity_curve.index[-1] - equity_curve.index[0]).total_seconds() / (365.25 * 24 * 3600)
    else:
        time_span = len(equity_curve) / periods_per_year

    if time_span <= 0:
        return 0.0

    # Annualize
    annualized = ((1 + total_return) ** (1 / time_span) - 1) * 100

    return float(annualized) if not np.isnan(annualized) else 0.0


def calculate_total_return(equity_curve: pd.Series, initial_capital: float) -> float:
    """
    Calculate total return from equity curve.

    Args:
        equity_curve: Series with equity values indexed by datetime
        initial_capital: Initial capital amount

    Returns:
        Total return as a percentage
    """
    if len(equity_curve) == 0 or initial_capital <= 0:
        return 0.0

    final_equity = equity_curve.iloc[-1]
    total_return = ((final_equity / initial_capital) - 1.0) * 100

    return float(total_return) if not np.isnan(total_return) else 0.0


def calculate_total_pnl(trades_df: pd.DataFrame) -> float:
    """
    Calculate total PnL from trades DataFrame.

    Args:
        trades_df: DataFrame with 'net_pnl' or 'portfolio_pnl' column

    Returns:
        Total PnL
    """
    if len(trades_df) == 0:
        return 0.0

    # Use portfolio_pnl if available, otherwise net_pnl
    pnl_col = "portfolio_pnl" if "portfolio_pnl" in trades_df.columns else "net_pnl"
    if pnl_col not in trades_df.columns:
        return 0.0

    total = trades_df[pnl_col].sum()

    return float(total) if not np.isnan(total) else 0.0

