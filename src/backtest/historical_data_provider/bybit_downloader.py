"""Bybit historical data downloader for crypto futures.

Downloads 1-minute kline data from Bybit API and saves as CSV files.
Supports multiple symbols and handles rate limiting.
"""

import pandas as pd
import time
from datetime import datetime, timedelta
from pathlib import Path

from pybit.unified_trading import HTTP

NUMBER_OF_ENTRIES = 1000


class BybitDownloader:
    """Downloader for Bybit historical kline data."""

    def __init__(
        self,
        symbol_configs: dict,
        api_config: dict,
        raw_data_dir: str,
    ):
        self.symbol_configs = symbol_configs
        self.client = HTTP(testnet=False, api_key=None, api_secret=None)

        self.rate_limit = api_config.get("rate_limit_per_minute", 500)
        self.request_delay = api_config.get("request_delay_seconds", 0.3)
        self.last_request_time = 0

        self.data_dir = Path(raw_data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit_wait(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        min_interval = 60.0 / self.rate_limit

        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last + self.request_delay
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _get_kline_data(self, symbol: str, category: str, start_time: int, end_time: int, interval: str = "1") -> pd.DataFrame:
        """Fetch kline data from Bybit API.

        Args:
            symbol: Trading symbol (e.g., 'ETHUSDT')
            category: Category ('linear' for perpetual futures)
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            interval: Kline interval ('1' for 1 minute)

        Returns:
            DataFrame with kline data
        """
        self._rate_limit_wait()

        try:
            response = self.client.get_kline(
                category=category,
                symbol=symbol,
                interval=interval,
                start=start_time,
                end=end_time,
                limit=NUMBER_OF_ENTRIES,  # Max 500 candles per request
            )

            if response["retCode"] != 0:
                raise Exception(f"Bybit API error: {response['retMsg']}")

            data = response["result"]["list"]

            if not data:
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(data, columns=["start_time", "open", "high", "low", "close", "volume", "turnover"])

            # Convert data types
            df["start_time"] = pd.to_datetime(df["start_time"].astype(int), unit="ms", utc=True)
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = df[col].astype(float)

            # Sort by time (oldest first)
            df = df.sort_values("start_time").reset_index(drop=True)

            return df

        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            raise

    def _datetime_to_timestamp_ms(self, dt: datetime) -> int:
        """Convert datetime to milliseconds timestamp.

        Args:
            dt: Datetime object

        Returns:
            Timestamp in milliseconds
        """
        return int(dt.timestamp() * 1000)

    def download_symbol_data(self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1") -> pd.DataFrame:
        """Download all kline data for a symbol within date range.

        Args:
            symbol: Symbol name (e.g., 'ETHUSDT')
            start_date: Start date (datetime)
            end_date: End date (datetime)
            interval: Kline interval ('1' for 1 minute)

        Returns:
            Combined DataFrame with all kline data
        """
        if symbol not in self.symbol_configs:
            raise ValueError(f"Symbol '{symbol}' not in universe. Available: {list(self.symbol_configs.keys())}")
        category = self.symbol_configs[symbol]["category"]

        print(f"Downloading {symbol} data from {start_date.date()} to {end_date.date()}")

        # Convert dates to timestamps
        start_ts = self._datetime_to_timestamp_ms(start_date)
        end_ts = self._datetime_to_timestamp_ms(end_date)

        all_data = []
        current_start = start_ts

        # Bybit returns max 500 candles per request
        # 1-minute candles = 500 minutes per request
        # Calculate request window (500 minutes in ms)

        request_window_ms = NUMBER_OF_ENTRIES * 60 * 1000

        while current_start < end_ts:
            current_end = min(current_start + request_window_ms, end_ts)

            print(f"  Fetching: {datetime.fromtimestamp(current_start/1000, tz=None)} " f"to {datetime.fromtimestamp(current_end/1000, tz=None)}")

            df = self._get_kline_data(symbol=symbol, category=category, start_time=current_start, end_time=current_end, interval=interval)

            if not df.empty:
                all_data.append(df)
                # Move to next window (use last timestamp + 1 minute)
                if len(df) > 0:
                    last_time = df["start_time"].iloc[-1]
                    current_start = self._datetime_to_timestamp_ms(last_time.to_pydatetime() + timedelta(minutes=1))
                else:
                    current_start = current_end
            else:
                # No data in this window, move forward
                current_start = current_end

        if not all_data:
            print(f"  No data found for {symbol}")
            return pd.DataFrame()

        # Combine all dataframes
        combined_df = pd.concat(all_data, ignore_index=True)

        # Remove duplicates and sort
        combined_df = combined_df.drop_duplicates(subset=["start_time"]).sort_values("start_time").reset_index(drop=True)

        print(f"  Downloaded {len(combined_df)} candles")

        return combined_df

    def save_to_csv(self, df: pd.DataFrame, symbol: str) -> Path:
        """Save DataFrame to CSV file.

        Args:
            df: DataFrame to save
            symbol: Symbol name for filename

        Returns:
            Path to saved file
        """
        # Create symbol directory
        symbol_dir = self.data_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)

        # Save as single CSV file
        filepath = symbol_dir / f"{symbol}_1min.csv"

        # Standardize column names
        df_output = df.copy()
        df_output.columns = ["timestamp", "open", "high", "low", "close", "volume", "turnover"]

        # Save to CSV
        df_output.to_csv(filepath, index=False)

        print(f"  Saved to: {filepath}")

        return filepath

    def download_and_save(
        self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1"
    ) -> Path:
        df = self.download_symbol_data(symbol, start_date, end_date, interval)

        if df.empty:
            raise ValueError(f"No data downloaded for {symbol}")

        return self.save_to_csv(df, symbol)


