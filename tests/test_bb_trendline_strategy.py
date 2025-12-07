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

    # Strategy uses last 4 rows: t-3, t-2, t-1 (signal check), t (current)
    # Test needs to set up data so t-1's close breaks above threshold
    t_minus_3 = sample_ohlcv_with_bb.iloc[-4]
    t_minus_2 = sample_ohlcv_with_bb.iloc[-3]

    # Calculate upper threshold (extrapolated from t-3 to t-2, projected to t-1)
    upper_slope = float(t_minus_2["bb_upper"] - t_minus_3["bb_upper"])
    upper_threshold = float(t_minus_2["bb_upper"] + upper_slope)

    # Force t-1's close price above threshold (iloc[-2] is t-1)
    df = sample_ohlcv_with_bb.copy()
    df.loc[df.index[-2], "close"] = upper_threshold + 100

    signal = strategy.generate_signal(df)

    assert signal is not None
    assert signal["signal"] == "BUY"
    assert signal["price"] > signal["threshold"]
    assert "metadata" in signal
    assert "slope" in signal["metadata"]


def test_sell_signal_lower_breakout(sample_ohlcv_with_bb):
    """Test SELL signal when price breaks below lower trendline."""
    strategy = BBTrendlineStrategy()

    # Strategy uses last 4 rows: t-3, t-2, t-1 (signal check), t (current)
    t_minus_3 = sample_ohlcv_with_bb.iloc[-4]
    t_minus_2 = sample_ohlcv_with_bb.iloc[-3]

    # Calculate lower threshold (extrapolated from t-3 to t-2, projected to t-1)
    lower_slope = float(t_minus_2["bb_lower"] - t_minus_3["bb_lower"])
    lower_threshold = float(t_minus_2["bb_lower"] + lower_slope)

    # Force t-1's close price below threshold (iloc[-2] is t-1)
    df = sample_ohlcv_with_bb.copy()
    df.loc[df.index[-2], "close"] = lower_threshold - 100

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
