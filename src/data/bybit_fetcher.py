"""
Bybit exchange data fetcher with retry logic.
Handles OHLCV data retrieval for derivatives (perpetual futures).
"""

import ccxt
import pandas as pd
import time
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BybitFetcher:
    """
    Fetches OHLCV data from Bybit derivatives market.

    Features:
    - 3-retry logic with exponential backoff
    - Notifies on complete failure
    - Returns pandas DataFrame
    - Handles Bybit-specific symbol format
    """

    def __init__(self, notifier=None):
        """
        Initialize Bybit fetcher.

        Args:
            notifier: Optional BaseNotifier instance for error notifications
        """
        self.exchange = ccxt.bybit(
            {
                "enableRateLimit": True,  # Respect Bybit rate limits
                "options": {"defaultType": "linear"},  # Perpetual futures (USDT-margined)
            }
        )
        self.notifier = notifier
        self.max_retries = 3
        self.base_retry_delay = 5  # seconds

    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data with retry logic.

        Args:
            symbol: Bybit symbol format 'BTCUSDT' (perpetual)
            timeframe: Candle interval ('1m', '5m', '15m', '1h', '4h', '1d')
            limit: Number of candles to fetch (default 100)

        Returns:
            DataFrame with columns [timestamp, open, high, low, close, volume]
            Returns None if all retries fail

        Example:
            df = fetcher.get_ohlcv('BTCUSDT', '1h', 50)
            # Returns last 50 hourly candles
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Fetching {symbol} {timeframe} data (attempt {attempt}/{self.max_retries})")

                # Fetch OHLCV from Bybit
                ohlcv = self.exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

                if not ohlcv:
                    logger.warning(f"Empty data returned for {symbol}")
                    continue

                # Convert to DataFrame
                df = pd.DataFrame(
                    ohlcv,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )

                # Convert timestamp to datetime
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

                # Sort by timestamp (oldest first)
                df = df.sort_values("timestamp").reset_index(drop=True)

                logger.info(f"Successfully fetched {len(df)} candles for {symbol} " f"(latest: {df['timestamp'].iloc[-1]})")

                return df

            except ccxt.NetworkError as e:
                logger.error(f"Network error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)

            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)

            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)

        # All retries failed - notify and return None
        error_msg = (
            f"⚠️ BYBIT API FAILURE ⚠️\n"
            f"Symbol: {symbol}\n"
            f"Failed after {self.max_retries} attempts\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.error(error_msg)

        if self.notifier:
            self.notifier.send(error_msg)

        return None

    def test_connection(self) -> bool:
        """
        Test Bybit connection by fetching market info.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.exchange.load_markets()
            logger.info("Bybit connection test successful")
            return True
        except Exception as e:
            logger.error(f"Bybit connection test failed: {e}")
            return False
