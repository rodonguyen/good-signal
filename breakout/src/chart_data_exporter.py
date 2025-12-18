"""Helper module to export portfolio data for JavaScript chart visualization.

This module provides functions to export portfolio data in the format
expected by the portfolio-chart.js module.
"""

import pandas as pd
import json
from pathlib import Path
from typing import Dict, List, Optional


def export_chart_data(
    trades_df: pd.DataFrame,
    price_df: pd.DataFrame,
    equity_curve: pd.Series,
    output_file: Optional[str] = None
) -> Dict:
    """Export portfolio data in format expected by portfolio-chart.js.
    
    Args:
        trades_df: DataFrame with trades (must have columns: entry_time, exit_time,
                  entry_price, exit_price, direction, stop_level, upper_level,
                  lower_level, exit_reason, portfolio_pnl)
        price_df: DataFrame with price data (must have columns: timestamp, open,
                 high, low, close)
        equity_curve: Series with equity values indexed by timestamp
        output_file: Optional path to save JSON file
        
    Returns:
        Dictionary with chart data in format expected by JavaScript module
    """
    # Process candlestick data
    price_df = price_df.copy()
    if price_df["timestamp"].dtype == "object":
        price_df["timestamp"] = pd.to_datetime(price_df["timestamp"], utc=True)
    price_df["time"] = (price_df["timestamp"].astype("int64") // 10**9).astype(int)
    
    candlestick_data = []
    for _, row in price_df.iterrows():
        candlestick_data.append({
            "time": int(row["time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"])
        })
    
    # Process equity data
    equity_df = pd.DataFrame({
        "timestamp": equity_curve.index,
        "equity": equity_curve.values
    })
    if equity_df["timestamp"].dtype == "object":
        equity_df["timestamp"] = pd.to_datetime(equity_df["timestamp"], utc=True)
    equity_df["time"] = (equity_df["timestamp"].astype("int64") // 10**9).astype(int)
    
    equity_data = []
    for _, row in equity_df.iterrows():
        if pd.notna(row["equity"]):
            equity_data.append({
                "time": int(row["time"]),
                "value": float(row["equity"])
            })
    
    # Process trades data (raw format for JS to process)
    trades_df = trades_df.copy()
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"], utc=True)
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"], utc=True)
    
    trades = []
    for idx, trade in trades_df.iterrows():
        entry_time = int(pd.Timestamp(trade["entry_time"]).timestamp())
        exit_time = int(pd.Timestamp(trade["exit_time"]).timestamp())
        
        trade_obj = {
            "entryTime": entry_time,
            "exitTime": exit_time,
            "entryPrice": float(trade["entry_price"]),
            "exitPrice": float(trade["exit_price"]),
            "direction": str(trade["direction"]).lower(),
            "portfolioPnl": float(trade["portfolio_pnl"]) if pd.notna(trade["portfolio_pnl"]) else 0.0
        }
        
        # Add optional fields
        if "stop_level" in trade.index and pd.notna(trade["stop_level"]):
            trade_obj["stopLevel"] = float(trade["stop_level"])
        
        if "upper_level" in trade.index and pd.notna(trade["upper_level"]):
            trade_obj["upperLevel"] = float(trade["upper_level"])
        
        if "lower_level" in trade.index and pd.notna(trade["lower_level"]):
            trade_obj["lowerLevel"] = float(trade["lower_level"])
        
        if "exit_reason" in trade.index and pd.notna(trade["exit_reason"]):
            trade_obj["exitReason"] = str(trade["exit_reason"]).lower()
        else:
            trade_obj["exitReason"] = "end_of_day"
        
        trades.append(trade_obj)
    
    # Combine all data
    chart_data = {
        "candlestickData": candlestick_data,
        "equityData": equity_data,
        "trades": trades
    }
    
    # Save to file if specified
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(chart_data, f, indent=2)
        print(f"Chart data exported to: {output_path}")
    
    return chart_data


def export_chart_data_from_portfolio(
    portfolio_file: str,
    price_data_file: str,
    output_file: Optional[str] = None,
    symbol: Optional[str] = None
) -> Dict:
    """Export chart data from portfolio CSV and price data files.
    
    Args:
        portfolio_file: Path to portfolio trades CSV
        price_data_file: Path to price data CSV
        output_file: Optional path to save JSON file
        symbol: Optional symbol name (if not in portfolio file)
        
    Returns:
        Dictionary with chart data
    """
    # Load portfolio trades
    trades_df = pd.read_csv(portfolio_file)
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"], utc=True)
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"], utc=True)
    
    # Get symbol from trades if not provided
    if symbol is None and "symbol" in trades_df.columns:
        symbol = trades_df["symbol"].iloc[0]
    
    # Load price data
    price_df = pd.read_csv(price_data_file)
    price_df["timestamp"] = pd.to_datetime(price_df["timestamp"], utc=True)
    
    # Get equity curve
    equity_curve = pd.Series(
        trades_df["equity"].values,
        index=trades_df["exit_time"]
    ).sort_index()
    
    return export_chart_data(trades_df, price_df, equity_curve, output_file)

