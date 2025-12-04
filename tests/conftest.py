"""
Pytest configuration and shared fixtures.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV DataFrame for testing with varying prices."""
    dates = pd.date_range("2024-12-01", periods=25, freq="1h")
    base_price = 45000

    # Create varying prices to ensure BB bands are different
    # Add some volatility (random walk around base price)
    np.random.seed(42)  # For reproducible tests
    price_variation = np.random.randn(25) * 500  # ~$500 std dev
    close_prices = base_price + price_variation

    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": close_prices * 0.999,
            "high": close_prices * 1.01,
            "low": close_prices * 0.99,
            "close": close_prices,
            "volume": [1000] * 25,
        }
    )
    return df


@pytest.fixture
def sample_ohlcv_with_bb(sample_ohlcv_data):
    """Create sample OHLCV DataFrame with Bollinger Bands calculated."""
    from src.indicators.bollinger_bands import BollingerBands

    bb = BollingerBands(period=20, std_dev=2.0)
    df = bb.calculate(sample_ohlcv_data.copy())
    return df


@pytest.fixture
def mock_bybit_fetcher(monkeypatch):
    """Mock BybitFetcher to avoid real API calls."""
    from src.data.bybit_fetcher import BybitFetcher
    import pandas as pd

    def mock_get_ohlcv(symbol, timeframe="1h", limit=100):
        dates = pd.date_range("2024-12-01", periods=limit, freq="1h")
        return pd.DataFrame(
            {
                "timestamp": dates,
                "open": [45000] * limit,
                "high": [45500] * limit,
                "low": [44500] * limit,
                "close": [45000] * limit,
                "volume": [1000] * limit,
            }
        )

    def mock_test_connection():
        return True

    fetcher = BybitFetcher()
    monkeypatch.setattr(fetcher, "get_ohlcv", mock_get_ohlcv)
    monkeypatch.setattr(fetcher, "test_connection", mock_test_connection)
    return fetcher


@pytest.fixture
def mock_discord_notifier(monkeypatch):
    """Mock DiscordNotifier to avoid real webhook calls."""
    from src.notifiers.discord_notifier import DiscordNotifier

    def mock_send(message):
        return True

    def mock_test():
        return True

    notifier = DiscordNotifier("https://discord.com/api/webhooks/test/test")
    monkeypatch.setattr(notifier, "send", mock_send)
    monkeypatch.setattr(notifier, "test", mock_test)
    return notifier
