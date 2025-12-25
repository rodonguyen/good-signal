"""
Backtest strategy: Supertrend trend-following strategy.

Rules:
- Resample data to signal_timeframe (default 4h)
- Calculate Supertrend indicator on resampled data
- Entry: When Supertrend direction changes
  - Long entry: direction changes from -1 to 1 (trend turns bullish)
  - Short entry: direction changes from 1 to -1 (trend turns bearish)
- Stop Loss: The Supertrend line acts as a trailing stop
- Exit: When Supertrend direction changes (trend reversal)
- Fees: round-trip fee_rate on notional
"""

from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime

import pandas as pd
import numpy as np

from src.backtest.contracts import BaseBacktestStrategy, BacktestContext, validate_trades_df
from src.backtest.utils.fee_utils import calculate_pnl_with_fees
from src.backtest.utils.resample_utils import ensure_utc_timestamp
from src.indicators.supertrend import Supertrend


class SupertrendStrategy(BaseBacktestStrategy):
    """Supertrend trend-following backtest strategy."""

    @property
    def strategy_id(self) -> str:
        return "supertrend"

    def generate_trades(
        self, minute_df: pd.DataFrame, *, context: BacktestContext, params: Mapping[str, Any]
    ) -> pd.DataFrame:
        minute_df = ensure_utc_timestamp(minute_df, "timestamp").sort_values("timestamp").reset_index(drop=True)

        empty_cols = [
            "symbol",
            "strategy_id",
            "entry_time",
            "exit_time",
            "direction",
            "entry_price",
            "exit_price",
            "stop_level",
            "tp_level",
            "raw_pnl",
            "fees",
            "net_pnl",
            "exit_reason",
        ]

        if minute_df.empty:
            return pd.DataFrame(columns=empty_cols)

        # Get parameters
        atr_period = int(params.get("atr_period", 10))
        multiplier = float(params.get("multiplier", 3.0))
        signal_timeframe = params.get("signal_timeframe", "4h")
        filter_allow_map: dict[str, bool] = params.get("filter_allow_map", {})
        debug = bool(params.get("debug", False))

        # Resample to signal timeframe
        resampled_df = self._resample_to_timeframe(minute_df, signal_timeframe)

        if len(resampled_df) < atr_period + 5:
            if debug:
                print(f"Not enough data after resampling: {len(resampled_df)} bars, need at least {atr_period + 5}")
            return pd.DataFrame(columns=empty_cols)

        # Calculate Supertrend indicator
        indicator = Supertrend(atr_period=atr_period, multiplier=multiplier)
        resampled_df = indicator.calculate(resampled_df)

        # Drop NaN rows from indicator calculation
        resampled_df = resampled_df.dropna(subset=["supertrend", "supertrend_direction"]).reset_index(drop=True)

        if len(resampled_df) < 2:
            if debug:
                print(f"Not enough valid Supertrend data: {len(resampled_df)} bars")
            return pd.DataFrame(columns=empty_cols)

        # Detect trend changes (signal generation)
        resampled_df["direction_change"] = resampled_df["supertrend_direction"].diff()

        # Generate trades
        trades_out: list[dict[str, Any]] = []

        for i in range(1, len(resampled_df)):
            direction_change = resampled_df.iloc[i]["direction_change"]

            # Skip if no direction change
            if pd.isna(direction_change) or direction_change == 0:
                continue

            # Determine trade direction
            if direction_change > 0:  # Changed from bearish (-1) to bullish (1)
                trade_direction = "long"
            elif direction_change < 0:  # Changed from bullish (1) to bearish (-1)
                trade_direction = "short"
            else:
                continue

            # Entry on the signal bar
            entry_time = resampled_df.iloc[i]["timestamp"]
            entry_price = float(resampled_df.iloc[i]["close"])
            entry_supertrend = float(resampled_df.iloc[i]["supertrend"])

            # Find exit: look for next direction change or end of data
            exit_idx = None
            exit_price = None
            exit_time = None
            exit_reason = None
            exit_supertrend = None

            # Scan forward for next direction change
            for j in range(i + 1, len(resampled_df)):
                next_direction_change = resampled_df.iloc[j]["direction_change"]

                if not pd.isna(next_direction_change) and next_direction_change != 0:
                    # Direction changed - exit at this bar's close
                    exit_idx = j
                    exit_time = resampled_df.iloc[j]["timestamp"]
                    exit_price = float(resampled_df.iloc[j]["close"])
                    exit_supertrend = float(resampled_df.iloc[j]["supertrend"])
                    exit_reason = "trend_reversal"
                    break

            # If no reversal found, exit at the last bar
            if exit_idx is None:
                exit_idx = len(resampled_df) - 1
                exit_time = resampled_df.iloc[exit_idx]["timestamp"]
                exit_price = float(resampled_df.iloc[exit_idx]["close"])
                exit_supertrend = float(resampled_df.iloc[exit_idx]["supertrend"])
                exit_reason = "end_of_data"

            # Calculate stop level (use Supertrend line at entry)
            # For long: stop is the Supertrend line (below price)
            # For short: stop is the Supertrend line (above price)
            stop_level = entry_supertrend

            # Calculate PnL
            direction_int: int = 1 if trade_direction == "long" else -1
            size = 1.0  # Fixed size for now
            raw_pnl, fees, net_pnl = calculate_pnl_with_fees(
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                direction=direction_int,
                fee_rate=context.fee_rate,
            )

            trade = {
                "symbol": context.symbol,
                "strategy_id": self.strategy_id,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "direction": trade_direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "stop_level": stop_level,
                "tp_level": None,  # No fixed TP for Supertrend
                "raw_pnl": raw_pnl,
                "fees": fees,
                "net_pnl": net_pnl,
                "exit_reason": exit_reason,
            }

            trades_out.append(trade)

            if debug:
                print(
                    f"Trade: {trade_direction} @ {entry_price:.2f} ({entry_time}) -> "
                    f"{exit_price:.2f} ({exit_time}), PnL: {net_pnl:.2f}, Reason: {exit_reason}"
                )

        if not trades_out:
            if debug:
                print("No trades generated")
            return pd.DataFrame(columns=empty_cols)

        trades_df = pd.DataFrame(trades_out)
        validate_trades_df(trades_df)

        if debug:
            print(f"Generated {len(trades_df)} trades")

        return trades_df

    def _resample_to_timeframe(self, minute_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        Resample 1-minute data to the specified timeframe.

        Args:
            minute_df: DataFrame with 1-minute OHLCV data
            timeframe: Target timeframe (e.g., '4h', '1h', '1d')

        Returns:
            DataFrame resampled to the target timeframe
        """
        df = minute_df.copy()
        df = df.set_index("timestamp")

        # Resample using OHLCV aggregation
        resampled = df.resample(timeframe).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )

        # Drop rows with NaN (incomplete bars)
        resampled = resampled.dropna()

        # Reset index to have timestamp as a column
        resampled = resampled.reset_index()

        return resampled
