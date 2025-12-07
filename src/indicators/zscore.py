"""
Z-Score indicator for spike detection.
Calculates z-scores for price returns and volume to identify unusual market activity.
"""

import pandas as pd
import numpy as np
from .base import BaseIndicator
import logging

logger = logging.getLogger(__name__)


class ZScoreIndicator(BaseIndicator):
    """
    Calculates z-scores for price returns and volume.

    Z-score formula: (value - rolling_mean) / rolling_std

    Usage:
        zscore = ZScoreIndicator(window=20)
        df = zscore.calculate(df)
        # Now df has: price_return, price_zscore, volume_zscore columns
    """

    def __init__(self, window: int = 20):
        """
        Initialize Z-Score indicator.

        Args:
            window: Lookback period for rolling statistics (default 20)
        """
        self.window = window

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate z-scores and add to DataFrame.

        Args:
            df: DataFrame with columns [close, volume]

        Returns:
            DataFrame with added columns:
            - price_return: % price change from previous candle
            - price_zscore: Z-score of price return
            - volume_zscore: Z-score of volume

        Note:
            First (window-1) rows will have NaN for z-score values
        """
        # Validate input
        if "close" not in df.columns or "volume" not in df.columns:
            raise ValueError("DataFrame must have 'close' and 'volume' columns")

        if len(df) < self.window:
            logger.warning(f"Not enough data: need at least {self.window} rows, got {len(df)}")

        # Calculate price returns (percentage change)
        df["price_return"] = df["close"].pct_change()

        # Rolling statistics for price returns
        price_mean = df["price_return"].rolling(window=self.window).mean()
        price_std = df["price_return"].rolling(window=self.window).std()

        # Rolling statistics for volume
        volume_mean = df["volume"].rolling(window=self.window).mean()
        volume_std = df["volume"].rolling(window=self.window).std()

        # Calculate z-scores (handle division by zero with replace)
        df["price_zscore"] = (df["price_return"] - price_mean) / price_std.replace(0, np.nan)
        df["volume_zscore"] = (df["volume"] - volume_mean) / volume_std.replace(0, np.nan)

        return df

    def __repr__(self) -> str:
        return f"ZScoreIndicator(window={self.window})"
