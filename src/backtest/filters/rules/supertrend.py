"""Supertrend trend confirmation filter rule."""

import pandas as pd
from typing import Any

from ..base import BaseFilterRule
from src.indicators.supertrend import Supertrend


class SupertrendFilter(BaseFilterRule):
    """Filter that uses Supertrend for trend confirmation.

    Adds 'filter_supertrend' column with values:
    - 1: Bullish trend (buy/long allowed)
    - -1: Bearish trend (sell/short allowed)
    """

    def _get_column_name(self) -> str:
        return "filter_supertrend"

    def apply(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Supertrend direction and add as column to DataFrame.

        Args:
            price_df: DataFrame with OHLCV data (same timeframe as strategy signal)

        Returns:
            DataFrame with added 'filter_supertrend' column (1 or -1)
        """
        df = price_df.copy()

        # Ensure timestamp is datetime
        if "timestamp" not in df.columns:
            raise ValueError("DataFrame must have 'timestamp' column")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Get parameters (required, no defaults)
        atr_period = int(self.params["atr_period"])
        multiplier = float(self.params["multiplier"])

        # Validate required columns
        required_cols = ["high", "low", "close"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"DataFrame must have columns: {missing_cols}")

        if len(df) < atr_period:
            # Not enough data - fill with NaN (will be filtered out)
            df[self.column_name] = pd.NA
            return df

        # Calculate Supertrend indicator
        indicator = Supertrend(atr_period=atr_period, multiplier=multiplier)
        df = indicator.calculate(df)

        # Add filter column with direction values
        df[self.column_name] = df["supertrend_direction"].astype("Int64")  # Nullable integer

        return df

    def is_allowed(self, filter_value: Any, trade_direction: str) -> bool:
        """Check if trade direction matches supertrend direction.

        Args:
            filter_value: Filter value (1 for bullish, -1 for bearish, or NaN)
            trade_direction: "long" or "short"

        Returns:
            True if directions match, False otherwise
        """
        # Handle NaN/missing values
        if pd.isna(filter_value):
            return False

        # Convert filter value to int
        filter_dir = int(filter_value)

        # Map trade direction to integer
        if trade_direction == "long":
            trade_dir = 1
        elif trade_direction == "short":
            trade_dir = -1
        else:
            return False

        # Allow trade only if directions match
        return filter_dir == trade_dir
