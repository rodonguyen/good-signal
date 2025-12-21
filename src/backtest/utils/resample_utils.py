"""
Resampling utilities for backtesting.

Conventions:
- Input OHLCV bars use `timestamp` as the candle OPEN time.
- All timestamps are treated as UTC (timezone-aware).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

SupportedTimeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]


def ensure_utc_timestamp(df: pd.DataFrame, column: str = "timestamp") -> pd.DataFrame:
    """
    Ensure df[column] is tz-aware UTC pandas datetime.
    """
    out = df.copy()
    if column not in out.columns:
        raise ValueError(f"DataFrame missing required column: {column}")

    out[column] = pd.to_datetime(out[column], utc=True)
    return out


def resample_ohlcv(
    df: pd.DataFrame,
    *,
    timeframe: SupportedTimeframe,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Resample OHLCV bars to a higher timeframe.

    Notes:
    - Uses left-closed, left-labeled buckets (timestamp = bucket open).
    - Drops incomplete buckets where open/close is missing.
    """
    if timeframe == "1m":
        return ensure_utc_timestamp(df, timestamp_col).sort_values(timestamp_col).reset_index(drop=True)

    rule_map = {
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }
    if timeframe not in rule_map:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    required = {"open", "high", "low", "close", "volume", timestamp_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"OHLCV DataFrame missing columns: {missing}")

    out = ensure_utc_timestamp(df, timestamp_col).sort_values(timestamp_col).copy()
    out = out.set_index(timestamp_col)

    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    resampled = (
        out.resample(rule_map[timeframe], label="left", closed="left")
        .agg(agg)
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )

    return resampled


def find_next_bar_open(df_1m: pd.DataFrame, *, t: pd.Timestamp, timestamp_col: str = "timestamp") -> pd.Series | None:
    """
    Return the first 1m bar with timestamp >= t.

    Used for execution fills like: enter at next 1m candle open after a signal time.
    """
    if df_1m.empty:
        return None
    df = ensure_utc_timestamp(df_1m, timestamp_col).sort_values(timestamp_col)
    t_utc = pd.to_datetime(t, utc=True)
    idx = df[timestamp_col].searchsorted(t_utc, side="left")
    if idx >= len(df):
        return None
    return df.iloc[int(idx)]


