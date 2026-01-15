"""Analysis utilities for calculating performance statistics."""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime, timedelta


def calculate_statistics(equity_curve: pd.Series, trades_df: pd.DataFrame, initial_capital: float) -> Dict:
    """Calculate comprehensive performance statistics.

    Args:
        equity_curve: Series with equity values over time
        trades_df: DataFrame with trades
        initial_capital: Starting capital

    Returns:
        Dictionary with all performance statistics
    """
    stats = {}

    # Prepend initial capital at the start to capture full drawdown from initial equity
    if len(equity_curve) > 0 and len(trades_df) > 0:
        # Get the entry time of the first trade
        first_entry_time = trades_df["entry_time"].min()
        # Create a new equity curve that starts with initial capital before first trade
        initial_equity_point = pd.Series([initial_capital], index=[first_entry_time])
        equity_curve = pd.concat([initial_equity_point, equity_curve]).sort_index()
        # Remove duplicates, keeping the later (actual) values
        equity_curve = equity_curve[~equity_curve.index.duplicated(keep='last')]

    # Basic metrics
    final_equity = equity_curve.iloc[-1] if len(equity_curve) > 0 else initial_capital
    total_return = (final_equity / initial_capital - 1) * 100
    stats["initial_capital"] = initial_capital
    stats["final_equity"] = final_equity
    stats["total_return"] = total_return
    stats["total_return_pct"] = total_return

    # Time period
    if len(equity_curve) > 0:
        start_date = equity_curve.index[0]
        end_date = equity_curve.index[-1]
        days = (end_date - start_date).days
        years = days / 365.25 if days > 0 else 0
        stats["start_date"] = start_date
        stats["end_date"] = end_date
        stats["days"] = days
        stats["years"] = years

        # Annualized return
        if years > 0:
            annualized_return = ((final_equity / initial_capital) ** (1 / years) - 1) * 100
        else:
            annualized_return = 0
        stats["annualized_return"] = annualized_return
    else:
        stats["start_date"] = None
        stats["end_date"] = None
        stats["days"] = 0
        stats["years"] = 0
        stats["annualized_return"] = 0

    # Trade statistics
    if len(trades_df) > 0:
        stats["total_trades"] = len(trades_df)
        stats["long_trades"] = len(trades_df[trades_df["direction"] == "long"])
        stats["short_trades"] = len(trades_df[trades_df["direction"] == "short"])

        # Win/Loss
        winning_trades = trades_df[trades_df["portfolio_pnl"] > 0]
        losing_trades = trades_df[trades_df["portfolio_pnl"] < 0]

        stats["winning_trades"] = len(winning_trades)
        stats["losing_trades"] = len(losing_trades)
        stats["win_rate"] = len(winning_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0

        # Average PnL
        stats["avg_win"] = winning_trades["portfolio_pnl"].mean() if len(winning_trades) > 0 else 0
        stats["avg_loss"] = losing_trades["portfolio_pnl"].mean() if len(losing_trades) > 0 else 0
        stats["avg_trade"] = trades_df["portfolio_pnl"].mean()

        # Profit factor
        total_wins = winning_trades["portfolio_pnl"].sum() if len(winning_trades) > 0 else 0
        total_losses = abs(losing_trades["portfolio_pnl"].sum()) if len(losing_trades) > 0 else 0
        stats["profit_factor"] = total_wins / total_losses if total_losses > 0 else float("inf")

        # Trade duration
        trades_df["duration"] = (trades_df["exit_time"] - trades_df["entry_time"]).dt.total_seconds() / 3600  # hours
        stats["avg_trade_duration_hours"] = trades_df["duration"].mean()
        stats["avg_trade_duration_days"] = stats["avg_trade_duration_hours"] / 24

        # Trades per year
        if stats["years"] > 0:
            stats["trades_per_year"] = stats["total_trades"] / stats["years"]
        else:
            stats["trades_per_year"] = 0
    else:
        stats["total_trades"] = 0
        stats["long_trades"] = 0
        stats["short_trades"] = 0
        stats["winning_trades"] = 0
        stats["losing_trades"] = 0
        stats["win_rate"] = 0
        stats["avg_win"] = 0
        stats["avg_loss"] = 0
        stats["avg_trade"] = 0
        stats["profit_factor"] = 0
        stats["avg_trade_duration_hours"] = 0
        stats["avg_trade_duration_days"] = 0
        stats["trades_per_year"] = 0

    # Drawdown statistics
    if len(equity_curve) > 0:
        running_max = equity_curve.expanding().max()
        drawdown = (equity_curve - running_max) / running_max * 100

        stats["max_drawdown"] = drawdown.min()
        stats["avg_drawdown"] = drawdown[drawdown < 0].mean() if len(drawdown[drawdown < 0]) > 0 else 0

        # Calculate recovery time (simplified)
        drawdown_periods = (drawdown < 0).sum()
        stats["drawdown_periods"] = drawdown_periods
    else:
        stats["max_drawdown"] = 0
        stats["avg_drawdown"] = 0
        stats["drawdown_periods"] = 0

    # Risk-adjusted returns
    if len(equity_curve) > 1 and stats["years"] > 0:
        # Resample equity curve to daily frequency for consistent return calculation
        # Forward fill to handle irregular trade timestamps
        equity_daily = equity_curve.resample("D").last().ffill()

        # Calculate daily returns
        daily_returns = equity_daily.pct_change().dropna()

        if len(daily_returns) > 0:
            # Annualized risk-free rate (5% = 0.05)
            annual_risk_free_rate = 0.05
            # Convert to daily risk-free rate
            daily_risk_free_rate = (1 + annual_risk_free_rate) ** (1 / 252) - 1

            # Calculate mean and std of daily returns
            mean_daily_return = daily_returns.mean()
            std_daily_return = daily_returns.std()

            # Sharpe ratio: (Mean Daily Return - Daily Risk-Free Rate) / Std Daily Return * sqrt(252)
            # This annualizes the Sharpe ratio
            if std_daily_return > 0:
                excess_return = mean_daily_return - daily_risk_free_rate
                stats["sharpe_ratio"] = excess_return / std_daily_return * np.sqrt(252)
            else:
                stats["sharpe_ratio"] = 0

            # Sortino ratio (downside deviation only)
            downside_returns = daily_returns[daily_returns < 0]
            downside_std = downside_returns.std() if len(downside_returns) > 0 else 0
            if downside_std > 0:
                stats["sortino_ratio"] = (mean_daily_return - daily_risk_free_rate) / downside_std * np.sqrt(252)
            else:
                stats["sortino_ratio"] = 0
        else:
            stats["sharpe_ratio"] = 0
            stats["sortino_ratio"] = 0
    else:
        stats["sharpe_ratio"] = 0
        stats["sortino_ratio"] = 0

    return stats
