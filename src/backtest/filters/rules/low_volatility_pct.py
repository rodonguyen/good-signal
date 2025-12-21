"""Low volatility percentage filter rule.

Allows entry when ATR (on hourly timeframe) at day start < threshold × price.
"""

import pandas as pd
import numpy as np
from typing import Any

from ..base import BaseFilterRule


class LowVolatilityPctFilter(BaseFilterRule):
    """Filter that allows entry when hourly ATR is below a percentage threshold."""

    def prepare(
        self,
        minute_df: pd.DataFrame,
        hourly_df: pd.DataFrame | None,
        daily_df: pd.DataFrame | None,
    ) -> dict[str, bool]:
        """Calculate low volatility flags for each day.
        
        Args:
            minute_df: 1-minute OHLCV data
            hourly_df: 1-hour OHLCV data (required for this filter)
            daily_df: Daily (24h) OHLCV data (optional, used for day mapping)
            
        Returns:
            Dictionary mapping day_key -> bool (True = low vol, allowed)
        """
        if hourly_df is None:
            raise ValueError("LowVolatilityPctFilter requires hourly_df")

        hourly_df = hourly_df.copy()
        
        # Ensure timestamp is datetime
        if "timestamp" in hourly_df.columns:
            hourly_df["timestamp"] = pd.to_datetime(hourly_df["timestamp"], utc=True)
        elif hourly_df.index.name == "timestamp":
            hourly_df = hourly_df.reset_index()
            hourly_df["timestamp"] = pd.to_datetime(hourly_df["timestamp"], utc=True)

        # Get parameters
        atr_period = int(self.params.get("atr_period", 12))
        threshold = float(self.params.get("threshold", 0.01))
        day_start_hour = int(self.params.get("day_start_hour", 13))

        # Calculate True Range on hourly bars
        hourly_df["prev_close"] = hourly_df["close"].shift(1)
        hourly_df["tr"] = np.maximum(
            hourly_df["high"] - hourly_df["low"],
            np.maximum(
                np.abs(hourly_df["high"] - hourly_df["prev_close"]),
                np.abs(hourly_df["low"] - hourly_df["prev_close"]),
            ),
        )

        # Calculate ATR (EMA of TR)
        hourly_df["atr"] = hourly_df["tr"].ewm(span=atr_period, adjust=False).mean()

        # Get ATR at day start (first hour of each day)
        hourly_df["hour"] = hourly_df["timestamp"].dt.hour
        day_start_bars = hourly_df[hourly_df["hour"] == day_start_hour].copy()

        # Assign day label (YYYY-MM-DD format)
        day_start_bars["day"] = day_start_bars["timestamp"].dt.strftime("%Y-%m-%d")

        # Calculate ATR as percentage of price
        day_start_bars["atr_pct"] = day_start_bars["atr"] / day_start_bars["close"]

        # Low volatility: ATR < threshold × price (i.e., atr_pct <= threshold)
        day_start_bars["low_vol"] = day_start_bars["atr_pct"] <= threshold

        # Build result map: day -> bool
        result_map = day_start_bars.set_index("day")["low_vol"].to_dict()

        return result_map

    def allow_entry(self, day_key: str, prepared: Any) -> bool:
        """Check if entry is allowed for the given day.
        
        Args:
            day_key: Day identifier (YYYY-MM-DD)
            prepared: Dictionary from prepare() mapping day -> bool
            
        Returns:
            True if low volatility (allowed), False otherwise
        """
        if not isinstance(prepared, dict):
            return False
        return prepared.get(day_key, False)

