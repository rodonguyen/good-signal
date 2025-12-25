"""
Supertrend indicator implementation.
Combines ATR and price to generate trend-following signals.
"""

import pandas as pd
import numpy as np
from .base import BaseIndicator


class Supertrend(BaseIndicator):
    """
    Supertrend technical indicator.

    The Supertrend indicator uses Average True Range (ATR) to plot above or below
    the price, indicating the current trend direction.

    Components:
    - ATR (Average True Range): Measures volatility
    - Basic Upper Band: (High + Low) / 2 + (Multiplier × ATR)
    - Basic Lower Band: (High + Low) / 2 - (Multiplier × ATR)
    - Final Supertrend: Switches between upper and lower bands based on trend

    Signals:
    - When Supertrend is below price → Bullish trend (green)
    - When Supertrend is above price → Bearish trend (red)

    Usage:
        st = Supertrend(atr_period=10, multiplier=3.0)
        df = st.calculate(df)
        # Now df has: supertrend, supertrend_direction, atr columns
    """

    def __init__(self, atr_period: int = 10, multiplier: float = 3.0):
        """
        Initialize Supertrend calculator.

        Args:
            atr_period: Number of periods for ATR calculation (default 10)
            multiplier: ATR multiplier for band calculation (default 3.0)
        """
        self.atr_period = atr_period
        self.multiplier = multiplier

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Supertrend and add to DataFrame.

        Args:
            df: DataFrame with 'high', 'low', 'close' columns

        Returns:
            DataFrame with added columns:
            - atr: Average True Range
            - supertrend: The Supertrend line value
            - supertrend_direction: 1 for bullish (buy), -1 for bearish (sell)

        Note:
            First (atr_period) rows will have NaN for Supertrend values
        """
        # Validate input
        required_cols = ["high", "low", "close"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"DataFrame must have columns: {missing_cols}")

        if len(df) < self.atr_period:
            raise ValueError(
                f"Not enough data: need at least {self.atr_period} rows, got {len(df)}"
            )

        # Calculate True Range
        df["tr"] = self._calculate_true_range(df)

        # Calculate ATR (Average True Range)
        df["atr"] = df["tr"].rolling(window=self.atr_period).mean()

        # Calculate basic bands
        hl_avg = (df["high"] + df["low"]) / 2
        df["basic_upper_band"] = hl_avg + (self.multiplier * df["atr"])
        df["basic_lower_band"] = hl_avg - (self.multiplier * df["atr"])

        # Initialize final bands
        df["final_upper_band"] = 0.0
        df["final_lower_band"] = 0.0
        df["supertrend"] = 0.0
        df["supertrend_direction"] = 1  # 1 for bullish, -1 for bearish

        # Calculate final bands and Supertrend
        for i in range(self.atr_period, len(df)):
            # Final Upper Band
            if (
                df["basic_upper_band"].iloc[i] < df["final_upper_band"].iloc[i - 1]
                or df["close"].iloc[i - 1] > df["final_upper_band"].iloc[i - 1]
            ):
                df.loc[df.index[i], "final_upper_band"] = df["basic_upper_band"].iloc[
                    i
                ]
            else:
                df.loc[df.index[i], "final_upper_band"] = df[
                    "final_upper_band"
                ].iloc[i - 1]

            # Final Lower Band
            if (
                df["basic_lower_band"].iloc[i] > df["final_lower_band"].iloc[i - 1]
                or df["close"].iloc[i - 1] < df["final_lower_band"].iloc[i - 1]
            ):
                df.loc[df.index[i], "final_lower_band"] = df["basic_lower_band"].iloc[
                    i
                ]
            else:
                df.loc[df.index[i], "final_lower_band"] = df[
                    "final_lower_band"
                ].iloc[i - 1]

            # Determine Supertrend value and direction
            if (
                df["supertrend"].iloc[i - 1] == df["final_upper_band"].iloc[i - 1]
                and df["close"].iloc[i] <= df["final_upper_band"].iloc[i]
            ):
                # Continue bearish trend
                df.loc[df.index[i], "supertrend"] = df["final_upper_band"].iloc[i]
                df.loc[df.index[i], "supertrend_direction"] = -1
            elif (
                df["supertrend"].iloc[i - 1] == df["final_upper_band"].iloc[i - 1]
                and df["close"].iloc[i] > df["final_upper_band"].iloc[i]
            ):
                # Switch to bullish trend
                df.loc[df.index[i], "supertrend"] = df["final_lower_band"].iloc[i]
                df.loc[df.index[i], "supertrend_direction"] = 1
            elif (
                df["supertrend"].iloc[i - 1] == df["final_lower_band"].iloc[i - 1]
                and df["close"].iloc[i] >= df["final_lower_band"].iloc[i]
            ):
                # Continue bullish trend
                df.loc[df.index[i], "supertrend"] = df["final_lower_band"].iloc[i]
                df.loc[df.index[i], "supertrend_direction"] = 1
            elif (
                df["supertrend"].iloc[i - 1] == df["final_lower_band"].iloc[i - 1]
                and df["close"].iloc[i] < df["final_lower_band"].iloc[i]
            ):
                # Switch to bearish trend
                df.loc[df.index[i], "supertrend"] = df["final_upper_band"].iloc[i]
                df.loc[df.index[i], "supertrend_direction"] = -1

        # Clean up intermediate columns
        df = df.drop(
            columns=["tr", "basic_upper_band", "basic_lower_band", "final_upper_band", "final_lower_band"]
        )

        return df

    def _calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate True Range for ATR calculation.

        True Range is the maximum of:
        - Current High - Current Low
        - Abs(Current High - Previous Close)
        - Abs(Current Low - Previous Close)

        Args:
            df: DataFrame with high, low, close columns

        Returns:
            Series with True Range values
        """
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift(1))
        low_close = np.abs(df["low"] - df["close"].shift(1))

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr

    def get_current_values(self, df: pd.DataFrame) -> dict:
        """
        Get current (latest) Supertrend values.

        Args:
            df: DataFrame with calculated Supertrend columns

        Returns:
            Dict with current values:
            {
                'supertrend': float,
                'direction': int (1 or -1),
                'atr': float,
                'timestamp': datetime
            }
        """
        if df.empty:
            raise ValueError("DataFrame is empty")

        latest = df.iloc[-1]

        return {
            "supertrend": float(latest["supertrend"]),
            "direction": int(latest["supertrend_direction"]),
            "atr": float(latest["atr"]),
            "timestamp": latest.get("timestamp", None),
        }

    def __repr__(self) -> str:
        return f"Supertrend(atr_period={self.atr_period}, multiplier={self.multiplier})"
