"""
Unit tests for BBTrendlineStrategy.
"""

import pytest
import pandas as pd
from src.strategies.bb_trendline import BBTrendlineStrategy
from src.indicators.bollinger_bands import BollingerBands


def test_buy_signal_upper_breakout(sample_ohlcv_with_bb):
    """Test BUY signal when price breaks above upper trendline."""
    strategy = BBTrendlineStrategy()

    # Get last 3 rows
    t_minus_2 = sample_ohlcv_with_bb.iloc[-3]
    t_minus_1 = sample_ohlcv_with_bb.iloc[-2]

    # Calculate upper threshold
    upper_slope = float(t_minus_1["bb_upper"] - t_minus_2["bb_upper"])
    upper_threshold = float(t_minus_1["bb_upper"] + upper_slope)

    # Force price above threshold
    df = sample_ohlcv_with_bb.copy()
    df.loc[df.index[-1], "close"] = upper_threshold + 100

    signal = strategy.generate_signal(df)

    assert signal is not None
    assert signal["signal"] == "BUY"
    assert signal["price"] > signal["threshold"]
    assert "metadata" in signal
    assert "slope" in signal["metadata"]


def test_sell_signal_lower_breakout(sample_ohlcv_with_bb):
    """Test SELL signal when price breaks below lower trendline."""
    strategy = BBTrendlineStrategy()

    # Get last 3 rows
    t_minus_2 = sample_ohlcv_with_bb.iloc[-3]
    t_minus_1 = sample_ohlcv_with_bb.iloc[-2]

    # Calculate lower threshold
    lower_slope = float(t_minus_1["bb_lower"] - t_minus_2["bb_lower"])
    lower_threshold = float(t_minus_1["bb_lower"] + lower_slope)

    # Force price below threshold
    df = sample_ohlcv_with_bb.copy()
    df.loc[df.index[-1], "close"] = lower_threshold - 100

    signal = strategy.generate_signal(df)

    assert signal is not None
    assert signal["signal"] == "SELL"
    assert signal["price"] < signal["threshold"]
    assert "metadata" in signal


def test_no_signal_within_bands(sample_ohlcv_with_bb):
    """Test no signal when price is within bands."""
    strategy = BBTrendlineStrategy()

    # Set price to middle band
    df = sample_ohlcv_with_bb.copy()
    df.loc[df.index[-1], "close"] = df.iloc[-1]["bb_middle"]

    signal = strategy.generate_signal(df)

    assert signal is None


def test_insufficient_data():
    """Test strategy handles insufficient data."""
    strategy = BBTrendlineStrategy()

    # Only 2 rows, need 3
    df = pd.DataFrame(
        {
            "close": [45000] * 2,
            "bb_upper": [46000] * 2,
            "bb_lower": [44000] * 2,
            "bb_middle": [45000] * 2,
            "timestamp": pd.date_range("2024-12-01", periods=2, freq="1h"),
        }
    )

    signal = strategy.generate_signal(df)
    assert signal is None


def test_missing_columns():
    """Test strategy handles missing required columns."""
    strategy = BBTrendlineStrategy()

    df = pd.DataFrame(
        {
            "close": [45000] * 5,
            "timestamp": pd.date_range("2024-12-01", periods=5, freq="1h"),
            # Missing bb_upper, bb_lower, bb_middle
        }
    )

    signal = strategy.generate_signal(df)
    assert signal is None
