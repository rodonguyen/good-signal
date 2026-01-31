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
        Calculate rolling NW envelope on the DataFrame's close prices.

        For each bar i >= window-1, computes kernel regression over the
        preceding `window` bars. Bars before that are NaN.
        """
        df = df.copy()
        n = len(df)
        w = min(self.window, n)

        close = df["close"].values.astype(np.float64)

        # Pre-compute Gaussian kernel weights matrix (w x w)
        idx = np.arange(w)
        diff = idx[:, None] - idx[None, :]
        weights = np.exp(-(diff ** 2) / (2 * self.bandwidth ** 2))
        row_sums = weights.sum(axis=1)  # (w,)

        # Build sliding windows: shape (n - w + 1, w)
        from numpy.lib.stride_tricks import sliding_window_view
        windows = sliding_window_view(close, w)  # (n - w + 1, w)

        # Batched kernel regression: Y[i, j] = regression value at position j
        # for window i.  Shape: (n - w + 1, w)
        Y = (weights @ windows.T).T / row_sums

        # smooth = endpoint of each rolling window's regression
        smooth_vals = Y[:, -1]  # (n - w + 1,)

        # MAE per window
        mae_vals = np.mean(np.abs(windows - Y), axis=1) * self.mult

        # Fill into DataFrame (first w-1 bars are NaN)
        nw_smooth = np.full(n, np.nan)
        nw_upper = np.full(n, np.nan)
        nw_lower = np.full(n, np.nan)

        start = w - 1
        nw_smooth[start:] = smooth_vals
        nw_upper[start:] = smooth_vals + mae_vals
        nw_lower[start:] = smooth_vals - mae_vals

        df["nw_smooth"] = nw_smooth
        df["nw_upper"] = nw_upper
        df["nw_lower"] = nw_lower

        return df
