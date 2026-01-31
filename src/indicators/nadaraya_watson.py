"""
Nadaraya-Watson Kernel Regression Envelope indicator.

Based on the Nadaraya-Watson Envelope by LuxAlgo (Pine Script).

Computes a kernel-smoothed regression line using a Gaussian kernel,
then adds/subtracts a scaled MAE to form upper and lower envelopes.

Columns added:
- nw_smooth: kernel regression line
- nw_upper: upper envelope (nw_smooth + mult * MAE)
- nw_lower: lower envelope (nw_smooth - mult * MAE)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators.base import BaseIndicator


class NadarayaWatsonEnvelope(BaseIndicator):
    """Nadaraya-Watson Gaussian kernel regression envelope."""

    def __init__(self, window: int = 500, bandwidth: float = 8.0, mult: float = 3.0):
        self.window = window
        self.bandwidth = bandwidth
        self.mult = mult

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate NW envelope on the DataFrame's close prices.

        Only the last `window` bars get indicator values; earlier bars are NaN.
        """
        df = df.copy()
        n = len(df)
        w = min(self.window, n)

        close = df["close"].values
        prices = close[-w:]  # last `window` bars

        # Pre-compute Gaussian kernel weights matrix
        idx = np.arange(w)
        # weights[i, j] = exp(-((i-j)^2) / (2 * h^2))
        diff = idx[:, None] - idx[None, :]
        weights = np.exp(-(diff ** 2) / (2 * self.bandwidth ** 2))

        # Kernel regression: y[i] = sum(prices * weights[i]) / sum(weights[i])
        y = (weights @ prices) / weights.sum(axis=1)

        # Mean absolute error
        mae = np.mean(np.abs(prices - y)) * self.mult

        # Fill into DataFrame (only last w rows)
        nw_smooth = np.full(n, np.nan)
        nw_upper = np.full(n, np.nan)
        nw_lower = np.full(n, np.nan)

        nw_smooth[-w:] = y
        nw_upper[-w:] = y + mae
        nw_lower[-w:] = y - mae

        df["nw_smooth"] = nw_smooth
        df["nw_upper"] = nw_upper
        df["nw_lower"] = nw_lower

        return df
