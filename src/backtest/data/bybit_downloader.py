"""Bybit historical data downloader for crypto futures.

Downloads 1-minute kline data from Bybit API and saves as CSV files.
Supports multiple symbols and handles rate limiting.
"""

import pandas as pd
import time
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from pybit.unified_trading import HTTP

NUMBER_OF_ENTRIES = 1000


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Dictionary containing configuration
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    return config


def get_symbol_config(symbol: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Get configuration for a specific symbol.

    Args:
        symbol: Symbol name (e.g., 'ETHUSDT')
        config: Pre-loaded config dict

    Returns:
        Symbol configuration dictionary
    """
    if symbol not in config["symbols"]:
        raise ValueError(f"Symbol '{symbol}' not found in configuration. " f"Available symbols: {list(config['symbols'].keys())}")

    return config["symbols"][symbol]


def get_default_symbol(config: Dict[str, Any]) -> str:
    """Get default symbol from configuration.

    Args:
        config: Pre-loaded config dict

    Returns:
        Default symbol name
    """
    return config.get("default_symbol", "ETHUSDT")


class BybitDownloader:
    """Downloader for Bybit historical kline data."""

    def __init__(self, config_path: str = "breakout/src/config/crypto_symbols.yaml"):
        """Initialize downloader with configuration.

        Args:
            config_path: Path to configuration file
        """
        self.config = load_config(config_path)
        self.api_config = self.config["api"]
        self.data_config = self.config["data"]

        # Initialize Bybit HTTP client
        self.client = HTTP(testnet=False, api_key=None, api_secret=None)  # Not needed for public historical data

        # Rate limiting
        self.rate_limit = self.api_config["rate_limit_per_minute"]
        self.request_delay = self.api_config["request_delay_seconds"]
        self.last_request_time = 0

        # Create data directory
        self.data_dir = Path(self.data_config["data_directory"])
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
        symbol_config = get_symbol_config(symbol, self.config)
        category = symbol_config["category"]

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
        self, symbol: Optional[str] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, interval: str = "1"
    ) -> Path:
        """Download and save data for a symbol.

        Args:
            symbol: Symbol name (defaults to config default)
            start_date: Start date (overrides config, defaults to config or 1 year ago)
            end_date: End date (overrides config, defaults to config or now)
            interval: Kline interval

        Returns:
            Path to saved CSV file
        """
        # Use defaults if not provided
        if symbol is None:
            symbol = get_default_symbol(self.config)

        # Get dates from config if not provided
        if end_date is None:
            config_end_date = self.data_config.get("end_date")
            if config_end_date is None or config_end_date == "null" or config_end_date == "":
                end_date = datetime.now()
            else:
                end_date = datetime.strptime(str(config_end_date), "%Y-%m-%d")

        if start_date is None:
            config_start_date = self.data_config.get("start_date")
            if config_start_date is None or config_start_date == "null" or config_start_date == "":
                start_date = end_date - timedelta(days=365)
            else:
                start_date = datetime.strptime(str(config_start_date), "%Y-%m-%d")

        # Download data
        df = self.download_symbol_data(symbol, start_date, end_date, interval)

        if df.empty:
            raise ValueError(f"No data downloaded for {symbol}")

        # Save to CSV
        filepath = self.save_to_csv(df, symbol)

        return filepath


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Download Bybit crypto futures data")
    parser.add_argument("--symbol", type=str, default=None, help="Symbol to download (e.g., ETHUSDT). Defaults to config default.")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD). Defaults to 1 year ago.")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD). Defaults to now.")
    parser.add_argument("--config", type=str, default="breakout/src/config/crypto_symbols.yaml", help="Path to config file")

    args = parser.parse_args()

    # Parse dates
    start_date = None
    end_date = None

    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    # Download
    downloader = BybitDownloader(config_path=args.config)
    filepath = downloader.download_and_save(symbol=args.symbol, start_date=start_date, end_date=end_date)

    print(f"\n✓ Download complete: {filepath}")


if __name__ == "__main__":
    main()
