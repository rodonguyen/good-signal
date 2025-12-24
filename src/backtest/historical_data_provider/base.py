"""Base interface for historical data providers."""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Union

import pandas as pd


class HistoricalDataProvider(ABC):
    """Interface for providers that can download and load historical market data."""

    @abstractmethod
    def ensure_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> Union[Path, pd.DataFrame]:
        """
        Ensure data exists for the given symbol and date range.

        Downloads data if needed, otherwise returns existing data.

        Args:
            symbol: Trading symbol (e.g., 'ETHUSDT')
            start: Start datetime
            end: End datetime
            timeframe: Timeframe string (e.g., '1m', '1h'). For now only '1m' is supported.

        Returns:
            Path to CSV file or DataFrame with OHLCV data.
            Columns: timestamp, open, high, low, close, volume, turnover
        """
        pass

    @abstractmethod
    def load_1m(self, symbol: str) -> pd.DataFrame:
        """
        Load existing 1-minute CSV data for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'ETHUSDT')

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, turnover
            Timestamp column is timezone-aware (UTC).

        Raises:
            FileNotFoundError: If data file does not exist
        """
        pass
