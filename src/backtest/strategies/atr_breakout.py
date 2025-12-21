"""
Backtest strategy: ATR Breakout on 24-hour crypto trading days.

Rules:
- Trading days start at day_start_hour UTC (default: 13:00).
- For each day, calculate breakout levels from previous day's close + ATR.
- Entry: first breakout (price crosses upper_level -> long, lower_level -> short).
- Stop: entry_price ± (stop_multiplier × prev_atr).
- Exit: stop loss hit OR end of day (13:00 UTC next day).
- One breakout attempt per day.
- Fees: round-trip fee_rate on notional.
"""

from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from src.backtest.contracts import BaseBacktestStrategy, BacktestContext, validate_trades_df
from src.backtest.utils.fee_utils import calculate_pnl_with_fees
from src.backtest.utils.resample_utils import ensure_utc_timestamp
from src.backtest.utils.crypto_day_utils import aggregate_24h_periods, define_crypto_day, get_day_boundaries
from src.indicators.atr_breakout_levels import AtrBreakoutLevels, calculate_crypto_atr


class AtrBreakoutStrategy(BaseBacktestStrategy):
    """ATR breakout strategy for 24-hour crypto trading days."""

    @property
    def strategy_id(self) -> str:
        return "atr_breakout"

    def generate_trades(self, minute_df: pd.DataFrame, *, context: BacktestContext, params: Mapping[str, Any]) -> pd.DataFrame:
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
        atr_period = int(params.get("atr_period", 14))
        breakout_multiplier = float(params.get("breakout_multiplier", 0.33))
        stop_multiplier = float(params.get("stop_multiplier", 0.33))
        day_start_hour = int(params.get("day_start_hour", 13))
        filter_allow_map: dict[str, bool] = params.get("filter_allow_map", {})
        debug = bool(params.get("debug", False))

        # Calculate daily bars and breakout levels
        indicator = AtrBreakoutLevels(
            atr_period=atr_period,
            breakout_multiplier=breakout_multiplier,
            stop_multiplier=stop_multiplier,
            day_start_hour=day_start_hour,
        )
        daily_bars = indicator.calculate(minute_df)

        if len(daily_bars) < 2:
            return pd.DataFrame(columns=empty_cols)

        # Prepare fast arrays for execution scanning
        timestamp_ns = minute_df["timestamp"].astype("int64").to_numpy()
        open_ = minute_df["open"].to_numpy(dtype=float, copy=False)
        high = minute_df["high"].to_numpy(dtype=float, copy=False)
        low = minute_df["low"].to_numpy(dtype=float, copy=False)
        close = minute_df["close"].to_numpy(dtype=float, copy=False)

        trades_out: list[dict[str, Any]] = []

        # Process each trading day (skip first day - need previous day's ATR)
        for i in range(1, len(daily_bars)):
            day_row = daily_bars.iloc[i]
            day_key = str(day_row["day"])

            # Check filter
            if filter_allow_map and not filter_allow_map.get(day_key, True):
                if debug:
                    print(f"  Day {day_key}: filtered out")
                continue

            # Skip if missing previous day data
            if pd.isna(day_row.get("prev_close")) or pd.isna(day_row.get("prev_atr")):
                continue

            upper_level = float(day_row["upper_level"])
            lower_level = float(day_row["lower_level"])
            stop_distance = float(day_row["stop_distance"])

            # Get day boundaries (already returns timezone-aware Timestamps)
            day_date = datetime.strptime(day_key, "%Y-%m-%d")
            day_start_ts, day_end_ts = get_day_boundaries(day_date, day_start_hour)

            # Find bars in this day
            day_start_idx = int(np.searchsorted(timestamp_ns, day_start_ts.value, side="left"))
            day_end_idx = int(np.searchsorted(timestamp_ns, day_end_ts.value, side="left"))

            if day_start_idx >= len(timestamp_ns) or day_end_idx <= day_start_idx:
                continue

            day_high = high[day_start_idx:day_end_idx]
            day_low = low[day_start_idx:day_end_idx]
            day_timestamp_ns = timestamp_ns[day_start_idx:day_end_idx]

            # Detect breakout: check for upper (long) or lower (short)
            upper_breakout_idx = np.flatnonzero(day_high >= upper_level)
            lower_breakout_idx = np.flatnonzero(day_low <= lower_level)

            if upper_breakout_idx.size == 0 and lower_breakout_idx.size == 0:
                # No breakout this day
                continue

            # Take first breakout (earliest)
            entry_idx_in_day = None
            direction = None
            entry_price = None

            if upper_breakout_idx.size > 0 and lower_breakout_idx.size > 0:
                # Both breakouts occurred - take the earlier one
                if upper_breakout_idx[0] < lower_breakout_idx[0]:
                    entry_idx_in_day = int(upper_breakout_idx[0])
                    direction = "long"
                    entry_price = upper_level
                else:
                    entry_idx_in_day = int(lower_breakout_idx[0])
                    direction = "short"
                    entry_price = lower_level
            elif upper_breakout_idx.size > 0:
                entry_idx_in_day = int(upper_breakout_idx[0])
                direction = "long"
                entry_price = upper_level
            else:  # lower_breakout_idx.size > 0
                entry_idx_in_day = int(lower_breakout_idx[0])
                direction = "short"
                entry_price = lower_level

            # Calculate stop level
            if direction == "long":
                stop_level = entry_price - stop_distance
            else:  # short
                stop_level = entry_price + stop_distance

            # Entry time
            entry_global_idx = day_start_idx + entry_idx_in_day
            entry_time = pd.to_datetime(timestamp_ns[entry_global_idx], utc=True)

            # --- Simulate exit: stop loss OR end of day ---
            exit_idx = None
            exit_price = None
            exit_reason = None

            # Check for stop loss (scan from entry to end of day)
            start = entry_global_idx + 1
            end = day_end_idx

            if direction == "long":
                stop_hits = np.flatnonzero(low[start:end] <= stop_level)
            else:  # short
                stop_hits = np.flatnonzero(high[start:end] >= stop_level)

            if stop_hits.size > 0:
                # Stop loss hit
                exit_idx = start + int(stop_hits[0])
                exit_price = stop_level
                exit_reason = "stop_loss"
            else:
                # End of day exit
                # Find the first bar at or after day_end
                eod_idx = int(np.searchsorted(timestamp_ns, day_end_ts.value, side="left"))
                if eod_idx < len(timestamp_ns):
                    exit_idx = eod_idx
                    exit_price = float(close[exit_idx])
                    exit_reason = "end_of_day"
                else:
                    # Use last available bar
                    exit_idx = len(timestamp_ns) - 1
                    exit_price = float(close[exit_idx])
                    exit_reason = "end_of_data"

            if exit_idx is None:
                continue

            exit_time = pd.to_datetime(timestamp_ns[exit_idx], utc=True)

            # Calculate PnL
            direction_int: int = 1 if direction == "long" else -1
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
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "stop_level": stop_level,
                "tp_level": None,  # No TP for ATR breakout
                "raw_pnl": raw_pnl,
                "fees": fees,
                "net_pnl": net_pnl,
                "exit_reason": exit_reason,
            }

            trades_out.append(trade)

        if not trades_out:
            return pd.DataFrame(columns=empty_cols)

        trades_df = pd.DataFrame(trades_out)
        validate_trades_df(trades_df)
        return trades_df
