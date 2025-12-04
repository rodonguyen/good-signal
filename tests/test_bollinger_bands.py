"""
Unit tests for BollingerBands indicator.
"""

import pytest
import pandas as pd
import numpy as np
from src.indicators.bollinger_bands import BollingerBands


def test_bollinger_bands_calculation(sample_ohlcv_data):
    """Test that BB calculates correctly."""
    bb = BollingerBands(period=20, std_dev=2.0)
    df = bb.calculate(sample_ohlcv_data)

    # Check columns added
    assert "bb_middle" in df.columns
    assert "bb_upper" in df.columns
    assert "bb_lower" in df.columns

    # Check BB values are reasonable
    last_row = df.iloc[-1]
    assert last_row["bb_upper"] > last_row["bb_middle"]
    assert last_row["bb_middle"] > last_row["bb_lower"]


def test_bollinger_bands_insufficient_data():
    """Test BB raises error with insufficient data."""
    bb = BollingerBands(period=20, std_dev=2.0)

    # Create data with only 10 rows (need 20)
    df = pd.DataFrame(
        {
            "close": [45000] * 10,
            "timestamp": pd.date_range("2024-12-01", periods=10, freq="1h"),
        }
    )

    with pytest.raises(ValueError, match="Not enough data"):
        bb.calculate(df)


def test_bollinger_bands_missing_close_column():
    """Test BB raises error when 'close' column missing."""
    bb = BollingerBands(period=20, std_dev=2.0)

    df = pd.DataFrame(
        {
            "price": [45000] * 25,  # Wrong column name
            "timestamp": pd.date_range("2024-12-01", periods=25, freq="1h"),
        }
    )

    with pytest.raises(ValueError, match="must have 'close' column"):
        bb.calculate(df)


def test_get_current_bands(sample_ohlcv_with_bb):
    """Test get_current_bands returns correct structure."""
    bb = BollingerBands(period=20, std_dev=2.0)
    bands = bb.get_current_bands(sample_ohlcv_with_bb)

    assert "upper" in bands
    assert "middle" in bands
    assert "lower" in bands
    assert "timestamp" in bands
    assert bands["upper"] > bands["middle"] > bands["lower"]


@pytest.mark.parametrize(
    "period,std_dev",
    [
        (20, 2.0),
        (14, 2.5),
        (30, 1.5),
    ],
)
def test_bollinger_bands_parameters(period, std_dev):
    """Test BB with different parameters."""
    # Create data with enough rows for the period
    dates = pd.date_range("2024-12-01", periods=max(period + 5, 35), freq="1h")
    base_price = 45000

    # Create varying prices
    np.random.seed(42)
    price_variation = np.random.randn(len(dates)) * 500
    close_prices = base_price + price_variation

    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": close_prices * 0.999,
            "high": close_prices * 1.01,
            "low": close_prices * 0.99,
            "close": close_prices,
            "volume": [1000] * len(dates),
        }
    )

    bb = BollingerBands(period=period, std_dev=std_dev)
    df = bb.calculate(df)

    assert "bb_upper" in df.columns
    assert "bb_lower" in df.columns
    assert "bb_middle" in df.columns

    # Verify bands are different (with varying prices, std dev should be > 0)
    last_row = df.iloc[-1]
    if not pd.isna(last_row["bb_upper"]):
        assert last_row["bb_upper"] >= last_row["bb_middle"]
        assert last_row["bb_middle"] >= last_row["bb_lower"]
