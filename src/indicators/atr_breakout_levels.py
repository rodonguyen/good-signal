"""ATR Breakout Levels indicator.

Computes daily breakout levels based on previous day's close and ATR.
Used for 24-hour crypto trading day breakout strategies.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Any

from .base import BaseIndicator
from src.backtest.utils.crypto_day_utils import aggregate_24h_periods


def calculate_crypto_atr(daily_bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR (Average True Range) for crypto 24-hour periods.

    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = rolling average of True Range over specified period.

    Args:
        daily_bars: DataFrame with daily bars (from aggregate_24h_periods)
        period: Number of periods for ATR calculation (default: 14)

    Returns:
        Series with ATR values
    """
    # Calculate True Range
    tr1 = daily_bars["high"] - daily_bars["low"]
    tr2 = abs(daily_bars["high"] - daily_bars["prev_close"])
    tr3 = abs(daily_bars["low"] - daily_bars["prev_close"])

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate ATR as rolling average
    atr = true_range.rolling(window=period, min_periods=1).mean()

    return atr


class AtrBreakoutLevels(BaseIndicator):
    """Indicator that computes daily breakout levels from ATR.

    For each 24-hour trading day, calculates:
    - upper_level = prev_close + (breakout_multiplier × prev_atr)
    - lower_level = prev_close - (breakout_multiplier × prev_atr)
    - stop_level (calculated after entry direction is known)
    """

    def __init__(
        self,
        atr_period: int = 14,
        breakout_multiplier: float = 0.33,
        stop_multiplier: float = 0.33,
        day_start_hour: int = 13,
    ):
        """Initialize ATR breakout levels indicator.

        Args:
            atr_period: Number of 24-hour periods for ATR calculation
            breakout_multiplier: Multiplier for breakout distance (k × ATR)
            stop_multiplier: Multiplier for stop loss distance (k × ATR)
            day_start_hour: Hour when trading day starts (default: 13 = 13:00 UTC)
        """
        self.atr_period = atr_period
        self.breakout_multiplier = breakout_multiplier
        self.stop_multiplier = stop_multiplier
        self.day_start_hour = day_start_hour

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate breakout levels for each day.

        Args:
            df: DataFrame with 1-minute OHLCV data (must have timestamp column)

        Returns:
            DataFrame with daily bars and breakout level columns:
            - day: Day identifier (YYYY-MM-DD)
            - prev_close: Previous day's close
            - prev_atr: Previous day's ATR
            - upper_level: Upper breakout level
            - lower_level: Lower breakout level
        """
        df = df.copy()

        # Ensure timestamp is datetime
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Aggregate into 24-hour periods
        daily_bars = aggregate_24h_periods(df, day_start_hour=self.day_start_hour)

        # Calculate ATR
        atr_series = calculate_crypto_atr(daily_bars, period=self.atr_period)
        daily_bars["atr"] = atr_series

        # Calculate breakout levels (using previous day's values)
        daily_bars["prev_close"] = daily_bars["close"].shift(1)
        daily_bars["prev_atr"] = daily_bars["atr"].shift(1)

        # Breakout distance
        daily_bars["breakout_distance"] = daily_bars["prev_atr"] * self.breakout_multiplier

        # Upper and lower levels
        daily_bars["upper_level"] = daily_bars["prev_close"] + daily_bars["breakout_distance"]
        daily_bars["lower_level"] = daily_bars["prev_close"] - daily_bars["breakout_distance"]

        # Stop distance (will be applied after entry direction is known)
        daily_bars["stop_distance"] = daily_bars["prev_atr"] * self.stop_multiplier

        return daily_bars
