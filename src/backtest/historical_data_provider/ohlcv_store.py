"""
Historical OHLCV storage layer for backtesting.

Responsibilities:
- Load raw 1-minute CSVs from disk
- Provide cached resampled OHLCV (e.g., 1h) as Parquet
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from src.backtest.data.cache import CacheKey, FileDependency, ParquetDataFrameCache
from src.backtest.utils.resample_utils import ensure_utc_timestamp, resample_ohlcv


@dataclass(frozen=True)
class OhlcvStoreConfig:
    raw_1m_dir: str = "data/raw/crypto"
    cache_dir: str = "data/cache/backtest"
    cache_enabled: bool = True
    cache_version: str = "v1"


class OhlcvStore:
    def __init__(self, config: OhlcvStoreConfig):
        self.config = config
        self.raw_1m_dir = Path(config.raw_1m_dir)
        self.cache = ParquetDataFrameCache(config.cache_dir)

    def _raw_1m_path(self, symbol: str) -> Path:
        return self.raw_1m_dir / symbol / f"{symbol}_1min.csv"

    def load_1m(self, symbol: str) -> pd.DataFrame:
        path = self._raw_1m_path(symbol)
        if not path.exists():
            symbol_dir = self.raw_1m_dir / symbol
            candidates = []
            if symbol_dir.exists():
                candidates = sorted([p.name for p in symbol_dir.glob(f"{symbol}_1min*.csv")])

            hint = f"Expected: {path}"
            if candidates:
                hint += f". Found in {symbol_dir}: {candidates}"
            else:
                hint += f". Directory not found or no matching CSVs in: {symbol_dir}"

            raise FileNotFoundError(hint)
        df = pd.read_csv(path)
        df = ensure_utc_timestamp(df, "timestamp").sort_values("timestamp").reset_index(drop=True)
        return df

    def load_resampled(
        self,
        symbol: str,
        *,
        timeframe: str,
    ) -> pd.DataFrame:
        """
        Load resampled bars from cache if present; otherwise compute from raw 1m and cache.
        """
        if timeframe == "1m":
            return self.load_1m(symbol)

        if not self.config.cache_enabled:
            return resample_ohlcv(self.load_1m(symbol), timeframe=timeframe)

        raw_path = self._raw_1m_path(symbol)
        if not raw_path.exists():
            # Delegate to load_1m for consistent error message + suggestions
            _ = self.load_1m(symbol)  # will raise
        deps = [FileDependency.from_path(raw_path)]
        key = CacheKey(
            namespace="resample",
            symbol=symbol,
            artifact=f"1m_to_{timeframe}",
            params={"timeframe": timeframe},
            version=self.config.cache_version,
        )

        return self.cache.get_or_compute(
            key,
            dependencies=deps,
            compute=lambda: resample_ohlcv(self.load_1m(symbol), timeframe=timeframe),
        )

    def slice_by_time(
        self,
        df: pd.DataFrame,
        *,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        timestamp_col: str = "timestamp",
    ) -> pd.DataFrame:
        """
        Utility: slice a bars DataFrame (any timeframe) by [start, end).
        """
        if df.empty:
            return df
        out = ensure_utc_timestamp(df, timestamp_col)
        if start is not None:
            start_utc = pd.to_datetime(start, utc=True)
            out = out[out[timestamp_col] >= start_utc]
        if end is not None:
            end_utc = pd.to_datetime(end, utc=True)
            out = out[out[timestamp_col] < end_utc]
        return out.reset_index(drop=True)
