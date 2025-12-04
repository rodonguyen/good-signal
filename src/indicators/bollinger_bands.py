"""
Bollinger Bands indicator implementation.
Calculates upper/lower bands based on SMA and standard deviation.
"""
import pandas as pd
import numpy as np
from .base import BaseIndicator


class BollingerBands(BaseIndicator):
    """
    Bollinger Bands technical indicator.

    Components:
    - Middle Band: Simple Moving Average (SMA)
    - Upper Band: SMA + (std_dev * standard deviation)
    - Lower Band: SMA - (std_dev * standard deviation)

    Usage:
        bb = BollingerBands(period=20, std_dev=2.0)
        df = bb.calculate(df)
        # Now df has: bb_middle, bb_upper, bb_lower columns
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        """
        Initialize Bollinger Bands calculator.

        Args:
            period: Number of periods for SMA calculation (default 20)
            std_dev: Standard deviation multiplier (default 2.0)
        """
        self.period = period
        self.std_dev = std_dev

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Bollinger Bands and add to DataFrame.

        Args:
            df: DataFrame with 'close' column

        Returns:
            DataFrame with added columns:
            - bb_middle: SMA of close prices
            - bb_upper: Upper band (SMA + std_dev * std)
            - bb_lower: Lower band (SMA - std_dev * std)

        Note:
            First (period-1) rows will have NaN for BB values
        """
        # Validate input
        if "close" not in df.columns:
            raise ValueError("DataFrame must have 'close' column")

        if len(df) < self.period:
            raise ValueError(
                f"Not enough data: need at least {self.period} rows, got {len(df)}"
            )

        # Calculate middle band (SMA)
        df["bb_middle"] = df["close"].rolling(window=self.period).mean()

        # Calculate rolling standard deviation
        rolling_std = df["close"].rolling(window=self.period).std()

        # Calculate upper and lower bands
        df["bb_upper"] = df["bb_middle"] + (self.std_dev * rolling_std)
        df["bb_lower"] = df["bb_middle"] - (self.std_dev * rolling_std)

        return df

    def get_current_bands(self, df: pd.DataFrame) -> dict:
        """
        Get current (latest) Bollinger Band values.

        Args:
            df: DataFrame with calculated BB columns

        Returns:
            Dict with current band values:
            {
                'upper': float,
                'middle': float,
                'lower': float,
                'timestamp': datetime
            }
        """
        if df.empty:
            raise ValueError("DataFrame is empty")

        latest = df.iloc[-1]

        return {
            "upper": float(latest["bb_upper"]),
            "middle": float(latest["bb_middle"]),
            "lower": float(latest["bb_lower"]),
            "timestamp": latest["timestamp"],
        }

    def __repr__(self) -> str:
        return f"BollingerBands(period={self.period}, std_dev={self.std_dev})"

