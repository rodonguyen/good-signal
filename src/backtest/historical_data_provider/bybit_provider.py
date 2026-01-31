"""Bybit implementation of HistoricalDataProvider."""

from datetime import datetime
from pathlib import Path
from typing import Union

import pandas as pd

from src.backtest.historical_data_provider.base import HistoricalDataProvider
from src.backtest.historical_data_provider.bybit_downloader import BybitDownloader


class BybitDataProvider(HistoricalDataProvider):
    """Bybit data provider that downloads and loads historical market data."""

    def __init__(
        self,
        symbol_configs: dict,
        api_config: dict,
        raw_data_dir: str,
    ):
        self.downloader = BybitDownloader(
            symbol_configs=symbol_configs,
            api_config=api_config,
            raw_data_dir=raw_data_dir,
        )
        self.raw_data_dir = Path(raw_data_dir)

    def _get_csv_path(self, symbol: str) -> Path:
        """Get expected CSV file path for a symbol."""
        return self.raw_data_dir / symbol / f"{symbol}_1min.csv"

    def ensure_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> Union[Path, pd.DataFrame]:
        """
        Ensure data exists for the given symbol and date range.

        Downloads data if needed, otherwise returns existing data path.

        Args:
            symbol: Trading symbol (e.g., 'ETHUSDT')
            start: Start datetime
            end: End datetime
            timeframe: Timeframe string (currently only '1m' is supported)

        Returns:
            Path to CSV file with OHLCV data.
            Columns: timestamp, open, high, low, close, volume, turnover
        """
        if timeframe != "1m":
            raise ValueError(f"Only '1m' timeframe is currently supported, got: {timeframe}")

        csv_path = self._get_csv_path(symbol)

        # Check if file exists and has data in the requested range
        if csv_path.exists():
            try:
                df = self.load_1m(symbol)
                if not df.empty:
                    # Check if data covers the requested range
                    df_start = df["timestamp"].min()
                    df_end = df["timestamp"].max()
                    if df_start <= start and df_end >= end:
                        # Data exists and covers the range
                        return csv_path
            except Exception:
                # If loading fails, re-download
                pass

        # Download data
        self.downloader.download_and_save(symbol=symbol, start_date=start, end_date=end, interval="1")
        return csv_path

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
        csv_path = self._get_csv_path(symbol)

        if not csv_path.exists():
            symbol_dir = self.raw_data_dir / symbol
            candidates = []
            if symbol_dir.exists():
                candidates = sorted([p.name for p in symbol_dir.glob(f"{symbol}_1min*.csv")])

            hint = f"Expected: {csv_path}"
            if candidates:
                hint += f". Found in {symbol_dir}: {candidates}"
            else:
                hint += f". Directory not found or no matching CSVs in: {symbol_dir}"

            raise FileNotFoundError(hint)

        df = pd.read_csv(csv_path)

        # Ensure timestamp is timezone-aware (UTC)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Sort by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)

        return df
