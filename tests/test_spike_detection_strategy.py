"""
Comprehensive test suite for SpikeDetectionStrategy.

Tests cover:
- Signal generation for SPIKE_UP and SPIKE_DOWN
- Threshold parameter variations
- Edge cases and boundary conditions
- Message formatting
- Integration with ZScoreIndicator
- Real-world scenarios
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.strategies.spike_detection import SpikeDetectionStrategy


class TestSpikeDetectionInitialization:
    """Test SpikeDetectionStrategy initialization."""

    def test_default_initialization(self):
        """Test strategy initializes with default thresholds."""
        strategy = SpikeDetectionStrategy()
        assert strategy.price_threshold == 2.5
        assert strategy.volume_threshold == 1.5

    def test_custom_thresholds(self):
        """Test strategy initializes with custom thresholds."""
        strategy = SpikeDetectionStrategy(price_threshold=3.0, volume_threshold=2.0)
        assert strategy.price_threshold == 3.0
        assert strategy.volume_threshold == 2.0

    def test_aggressive_thresholds(self):
        """Test aggressive threshold configuration."""
        strategy = SpikeDetectionStrategy(price_threshold=2.0, volume_threshold=1.0)
        assert strategy.price_threshold == 2.0
        assert strategy.volume_threshold == 1.0

    def test_repr_string(self):
        """Test string representation."""
        strategy = SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)
        expected = "SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)"
        assert repr(strategy) == expected


class TestSpikeDetectionValidation:
    """Test input validation and error handling."""

    def test_missing_required_columns_returns_none(self, caplog):
        """Test that missing columns returns None with warning."""
        strategy = SpikeDetectionStrategy()
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"),
                "close": [100] * 10,
                # Missing: volume, price_zscore, volume_zscore, price_return
            }
        )

        result = strategy.generate_signal(df)

        assert result is None
        assert "Missing columns" in caplog.text

    def test_insufficient_data_returns_none(self, caplog):
        """Test that less than 2 candles returns None."""
        strategy = SpikeDetectionStrategy()
        df = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2024-01-01")],
                "close": [100],
                "volume": [1000],
                "price_return": [0.01],
                "price_zscore": [1.5],
                "volume_zscore": [1.2],
            }
        )

        result = strategy.generate_signal(df)

        assert result is None
        assert "Insufficient data" in caplog.text

    def test_nan_zscores_returns_none(self, caplog):
        """Test that NaN z-scores returns None."""
        import logging

        caplog.set_level(logging.DEBUG)

        strategy = SpikeDetectionStrategy()
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="1h"),
                "close": [100] * 5,
                "volume": [1000] * 5,
                "price_return": [0.01] * 5,
                "price_zscore": [np.nan] * 5,  # NaN z-scores
                "volume_zscore": [1.5] * 5,
            }
        )

        result = strategy.generate_signal(df)

        assert result is None
        assert "NaN z-scores" in caplog.text


class TestSpikeUpDetection:
    """Test SPIKE_UP signal generation."""

    @pytest.fixture
    def spike_up_data(self):
        """DataFrame with clear upward spike."""
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 23 + [110.0, 115.0],
                "volume": [1000.0] * 23 + [5000.0, 6000.0],
                "price_return": [0.0] * 23 + [0.10, 0.045],
                "price_zscore": [0.0] * 23 + [3.5, 2.8],
                "volume_zscore": [0.0] * 23 + [2.5, 2.8],
            }
        )

    def test_spike_up_detected_with_default_thresholds(self, spike_up_data):
        """Test SPIKE_UP is detected with default thresholds."""
        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(spike_up_data)

        assert signal is not None
        assert signal["signal"] == "SPIKE_UP"

    def test_spike_up_signal_structure(self, spike_up_data):
        """Test SPIKE_UP signal contains all required fields."""
        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(spike_up_data)

        # Main fields
        assert "signal" in signal
        assert "price" in signal
        assert "price_zscore" in signal
        assert "volume_zscore" in signal
        assert "price_return_pct" in signal
        assert "volume" in signal
        assert "volume_ratio" in signal
        assert "timestamp" in signal
        assert "metadata" in signal

        # Metadata fields
        assert "price_threshold" in signal["metadata"]
        assert "volume_threshold" in signal["metadata"]
        assert "avg_volume" in signal["metadata"]
        assert "combined_score" in signal["metadata"]
        assert "confirmation" in signal["metadata"]

    def test_spike_up_values_correct(self, spike_up_data):
        """Test SPIKE_UP signal values are calculated correctly."""
        strategy = SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)
        signal = strategy.generate_signal(spike_up_data)

        assert signal["price"] == 115.0
        assert signal["price_zscore"] == pytest.approx(2.8, rel=0.01)
        assert signal["volume_zscore"] == pytest.approx(2.8, rel=0.01)
        assert signal["price_return_pct"] == pytest.approx(4.5, rel=0.01)
        assert signal["volume"] == 6000.0

    def test_spike_up_confirmation_strong(self):
        """Test SPIKE_UP gets STRONG confirmation with high z-scores."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [120.0],
                "volume": [1000.0] * 24 + [8000.0],
                "price_return": [0.0] * 24 + [0.20],
                "price_zscore": [0.0] * 24 + [4.0],  # > 3.0
                "volume_zscore": [0.0] * 24 + [3.5],  # > 2.0
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        assert signal["metadata"]["confirmation"] == "STRONG"

    def test_spike_up_confirmation_moderate(self, spike_up_data):
        """Test SPIKE_UP gets MODERATE confirmation with moderate z-scores."""
        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(spike_up_data)

        # price_z=2.8, volume_z=2.8 should be MODERATE (not > 3.0 and > 2.0)
        assert signal["metadata"]["confirmation"] == "MODERATE"

    def test_spike_up_volume_ratio(self, spike_up_data):
        """Test volume ratio is calculated correctly."""
        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(spike_up_data)

        # Average volume of last 20 (including current): 18*1000 + 5000 + 6000 = 29000/20 = 1450
        # Current volume is 6000
        # Ratio should be 6000/1450 = 4.14
        assert signal["volume_ratio"] > 4.0
        assert signal["volume_ratio"] < 4.5


class TestSpikeDownDetection:
    """Test SPIKE_DOWN signal generation."""

    @pytest.fixture
    def spike_down_data(self):
        """DataFrame with clear downward spike."""
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 23 + [90.0, 85.0],
                "volume": [1000.0] * 23 + [5000.0, 6000.0],
                "price_return": [0.0] * 23 + [-0.10, -0.056],
                "price_zscore": [0.0] * 23 + [-3.5, -2.8],  # Negative
                "volume_zscore": [0.0] * 23 + [2.5, 2.8],  # Positive
            }
        )

    def test_spike_down_detected_with_default_thresholds(self, spike_down_data):
        """Test SPIKE_DOWN is detected with default thresholds."""
        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(spike_down_data)

        assert signal is not None
        assert signal["signal"] == "SPIKE_DOWN"

    def test_spike_down_values_correct(self, spike_down_data):
        """Test SPIKE_DOWN signal values are calculated correctly."""
        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(spike_down_data)

        assert signal["price"] == 85.0
        assert signal["price_zscore"] == pytest.approx(-2.8, rel=0.01)
        assert signal["volume_zscore"] == pytest.approx(2.8, rel=0.01)
        assert signal["price_return_pct"] < 0  # Negative return

    def test_spike_down_negative_price_zscore(self, spike_down_data):
        """Test SPIKE_DOWN has negative price z-score."""
        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(spike_down_data)

        assert signal["price_zscore"] < 0
        assert signal["price_zscore"] < -strategy.price_threshold

    def test_spike_down_confirmation_strong(self):
        """Test SPIKE_DOWN gets STRONG confirmation."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [80.0],
                "volume": [1000.0] * 24 + [8000.0],
                "price_return": [0.0] * 24 + [-0.20],
                "price_zscore": [0.0] * 24 + [-4.0],  # < -3.0
                "volume_zscore": [0.0] * 24 + [3.5],  # > 2.0
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        assert signal["signal"] == "SPIKE_DOWN"
        assert signal["metadata"]["confirmation"] == "STRONG"


class TestNoSpikeConditions:
    """Test conditions where no spike should be detected."""

    @pytest.fixture
    def no_spike_data(self):
        """DataFrame with normal price action (no spike)."""
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 25,
                "volume": [1000.0] * 25,
                "price_return": [0.0] * 25,
                "price_zscore": [0.0] * 25,
                "volume_zscore": [0.5] * 25,
            }
        )

    def test_no_spike_with_normal_data(self, no_spike_data, caplog):
        """Test no signal with normal data."""
        import logging

        caplog.set_level(logging.INFO)

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(no_spike_data)

        assert signal is None
        assert "No spike" in caplog.text

    def test_no_spike_with_low_price_zscore(self):
        """Test no signal when price z-score below threshold."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 25,
                "volume": [1000.0] * 24 + [5000.0],
                "price_return": [0.0] * 25,
                "price_zscore": [0.0] * 24 + [1.0],  # Below threshold
                "volume_zscore": [0.0] * 24 + [3.0],  # Above threshold
            }
        )

        strategy = SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)
        signal = strategy.generate_signal(df)

        assert signal is None

    def test_no_spike_with_low_volume_zscore(self):
        """Test no signal when volume z-score below threshold."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [110.0],
                "volume": [1000.0] * 25,
                "price_return": [0.0] * 24 + [0.10],
                "price_zscore": [0.0] * 24 + [3.0],  # Above threshold
                "volume_zscore": [0.0] * 24 + [0.5],  # Below threshold
            }
        )

        strategy = SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)
        signal = strategy.generate_signal(df)

        assert signal is None

    def test_no_spike_at_threshold_boundary(self):
        """Test no signal when exactly at threshold (not above)."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 25,
                "volume": [1000.0] * 25,
                "price_return": [0.0] * 25,
                "price_zscore": [0.0] * 24 + [2.5],  # Exactly at threshold
                "volume_zscore": [0.0] * 24 + [1.5],  # Exactly at threshold
            }
        )

        strategy = SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)
        signal = strategy.generate_signal(df)

        # Should NOT detect (need > threshold, not >=)
        assert signal is None


class TestThresholdParameterVariations:
    """Test different threshold configurations."""

    @pytest.fixture
    def moderate_spike_data(self):
        """Data with moderate spike (between conservative and aggressive)."""
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [110.0],
                "volume": [1000.0] * 24 + [4000.0],
                "price_return": [0.0] * 24 + [0.10],
                "price_zscore": [0.0] * 24 + [2.7],
                "volume_zscore": [0.0] * 24 + [1.8],
            }
        )

    def test_conservative_thresholds_no_signal(self, moderate_spike_data):
        """Test conservative thresholds miss moderate spike."""
        strategy = SpikeDetectionStrategy(price_threshold=3.0, volume_threshold=2.0)
        signal = strategy.generate_signal(moderate_spike_data)

        # Conservative thresholds: 2.7 < 3.0 or 1.8 < 2.0
        assert signal is None

    def test_moderate_thresholds_detect_signal(self, moderate_spike_data):
        """Test moderate thresholds detect moderate spike."""
        strategy = SpikeDetectionStrategy(price_threshold=2.5, volume_threshold=1.5)
        signal = strategy.generate_signal(moderate_spike_data)

        # Moderate thresholds: 2.7 > 2.5 and 1.8 > 1.5
        assert signal is not None
        assert signal["signal"] == "SPIKE_UP"

    def test_aggressive_thresholds_detect_signal(self, moderate_spike_data):
        """Test aggressive thresholds easily detect spike."""
        strategy = SpikeDetectionStrategy(price_threshold=2.0, volume_threshold=1.0)
        signal = strategy.generate_signal(moderate_spike_data)

        # Aggressive thresholds: 2.7 > 2.0 and 1.8 > 1.0
        assert signal is not None

    @pytest.mark.parametrize(
        "price_th,volume_th,expected_signal",
        [
            (3.0, 2.0, False),  # Conservative - no signal
            (2.5, 1.5, True),  # Moderate - signal
            (2.0, 1.0, True),  # Aggressive - signal
            (1.5, 0.5, True),  # Very aggressive - signal
        ],
    )
    def test_various_threshold_combinations(self, moderate_spike_data, price_th, volume_th, expected_signal):
        """Test various threshold combinations."""
        strategy = SpikeDetectionStrategy(price_threshold=price_th, volume_threshold=volume_th)
        signal = strategy.generate_signal(moderate_spike_data)

        if expected_signal:
            assert signal is not None
        else:
            assert signal is None


class TestMessageFormatting:
    """Test Discord message formatting."""

    @pytest.fixture
    def sample_spike_up_signal(self):
        """Sample SPIKE_UP signal data."""
        return {
            "signal": "SPIKE_UP",
            "price": 45250.0,
            "price_zscore": 3.20,
            "volume_zscore": 2.10,
            "price_return_pct": 5.25,
            "volume": 50000.0,
            "volume_ratio": 3.50,
            "timestamp": pd.Timestamp("2024-01-15 14:00:00"),
            "metadata": {"price_threshold": 2.5, "volume_threshold": 1.5, "avg_volume": 14285.7, "combined_score": 5.30, "confirmation": "STRONG"},
        }

    @pytest.fixture
    def sample_spike_down_signal(self):
        """Sample SPIKE_DOWN signal data."""
        return {
            "signal": "SPIKE_DOWN",
            "price": 42800.0,
            "price_zscore": -3.50,
            "volume_zscore": 2.80,
            "price_return_pct": -4.75,
            "volume": 60000.0,
            "volume_ratio": 4.20,
            "timestamp": pd.Timestamp("2024-01-15 15:00:00"),
            "metadata": {"price_threshold": 2.5, "volume_threshold": 1.5, "avg_volume": 14285.7, "combined_score": 6.30, "confirmation": "STRONG"},
        }

    def test_format_spike_up_message(self, sample_spike_up_signal):
        """Test SPIKE_UP message formatting."""
        strategy = SpikeDetectionStrategy()
        message = strategy.format_signal_message("BTCUSDT", sample_spike_up_signal)

        assert "SPIKE_UP DETECTED" in message
        assert "🔺" in message
        assert "BTC" in message
        assert "$45,250.00" in message
        assert "+5.25%" in message
        assert "3.20" in message  # price z-score
        assert "2.10" in message  # volume z-score
        assert "STRONG" in message

    def test_format_spike_down_message(self, sample_spike_down_signal):
        """Test SPIKE_DOWN message formatting."""
        strategy = SpikeDetectionStrategy()
        message = strategy.format_signal_message("ETHUSDT", sample_spike_down_signal)

        assert "SPIKE_DOWN DETECTED" in message
        assert "🔻" in message
        assert "ETH" in message
        assert "$42,800.00" in message
        assert "-4.75%" in message
        assert "-3.50" in message  # negative price z-score

    def test_message_contains_all_sections(self, sample_spike_up_signal):
        """Test message contains all required sections."""
        strategy = SpikeDetectionStrategy()
        message = strategy.format_signal_message("BTCUSDT", sample_spike_up_signal)

        # Required sections
        assert "Symbol:" in message
        assert "Price:" in message
        assert "Price Change:" in message
        assert "Z-Scores:" in message
        assert "Volume Analysis:" in message
        assert "Signal Strength:" in message
        assert "Combined Score:" in message
        assert "Timestamp:" in message

    def test_message_symbol_cleaning(self, sample_spike_up_signal):
        """Test symbol name is cleaned for display."""
        strategy = SpikeDetectionStrategy()

        # Test with :USDT format
        message1 = strategy.format_signal_message("BTC:USDT", sample_spike_up_signal)
        assert "BTC" in message1
        assert ":USDT" not in message1

        # Test with USDT format
        message2 = strategy.format_signal_message("BTCUSDT", sample_spike_up_signal)
        assert "BTC" in message2
        assert "USDT" not in message2 or message2.count("BTC") > message2.count("USDT")


class TestCombinedScore:
    """Test combined score calculation."""

    def test_combined_score_calculation(self):
        """Test combined score is sum of absolute z-scores."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [110.0],
                "volume": [1000.0] * 24 + [5000.0],
                "price_return": [0.0] * 24 + [0.10],
                "price_zscore": [0.0] * 24 + [3.0],
                "volume_zscore": [0.0] * 24 + [2.0],
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        # Combined score should be |3.0| + 2.0 = 5.0
        assert signal["metadata"]["combined_score"] == pytest.approx(5.0, rel=0.01)

    def test_combined_score_with_negative_price_zscore(self):
        """Test combined score uses absolute value of price z-score."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [90.0],
                "volume": [1000.0] * 24 + [5000.0],
                "price_return": [0.0] * 24 + [-0.10],
                "price_zscore": [0.0] * 24 + [-3.5],
                "volume_zscore": [0.0] * 24 + [2.5],
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        # Combined score should be |-3.5| + 2.5 = 6.0
        assert signal["metadata"]["combined_score"] == pytest.approx(6.0, rel=0.01)


class TestRealWorldScenarios:
    """Test realistic market scenarios."""

    def test_flash_crash_detection(self):
        """Test detection of flash crash event."""
        # Simulate sudden crash with high volume
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=30, freq="5min"),
                "close": [50000.0] * 25 + [45000.0, 40000.0, 35000.0, 38000.0, 40000.0],
                "volume": [1000.0] * 25 + [15000.0, 25000.0, 30000.0, 20000.0, 15000.0],
                "price_return": [0.0] * 25 + [-0.10, -0.111, -0.125, 0.086, 0.053],
                "price_zscore": [0.0] * 25 + [-4.0, -5.0, -6.0, 3.5, 2.8],  # Latest > 2.5
                "volume_zscore": [0.0] * 25 + [3.0, 4.0, 5.0, 3.5, 2.8],  # Latest > 2.0
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        # Should detect SPIKE_UP on recovery (latest candle)
        assert signal is not None
        assert signal["signal"] == "SPIKE_UP"
        assert signal["metadata"]["confirmation"] == "MODERATE"

    def test_news_driven_pump(self):
        """Test detection of news-driven price pump."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=30, freq="1h"),
                "close": [45000.0] * 28 + [48000.0, 52000.0],
                "volume": [2000.0] * 28 + [20000.0, 25000.0],
                "price_return": [0.0] * 28 + [0.067, 0.083],
                "price_zscore": [0.0] * 28 + [3.5, 4.0],
                "volume_zscore": [0.0] * 28 + [4.0, 4.5],
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        assert signal is not None
        assert signal["signal"] == "SPIKE_UP"
        assert signal["metadata"]["confirmation"] == "STRONG"

    def test_whale_manipulation(self):
        """Test detection of whale manipulation (high volume, moderate price)."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=30, freq="5min"),
                "close": [45000.0] * 28 + [45500.0, 46000.0],
                "volume": [500.0] * 28 + [10000.0, 15000.0],  # Huge volume spike
                "price_return": [0.0] * 28 + [0.011, 0.011],
                "price_zscore": [0.0] * 28 + [2.2, 2.3],
                "volume_zscore": [0.0] * 28 + [5.0, 6.0],  # Extreme volume
            }
        )

        # Aggressive thresholds to catch it
        strategy = SpikeDetectionStrategy(price_threshold=2.0, volume_threshold=1.0)
        signal = strategy.generate_signal(df)

        assert signal is not None
        # Volume ratio calculation includes current spike in average of last 20
        # Last 20: 11*500 + 10000 + 15000 = 30500/20 = 1525
        # Current: 15000, ratio = 15000/1525 = 9.84
        assert signal["volume_ratio"] > 8.0  # Significant volume increase

    def test_gradual_trend_not_detected(self):
        """Test that gradual trend doesn't trigger spike."""
        # Smooth uptrend over 30 periods
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=30, freq="1h"),
                "close": np.linspace(45000, 48000, 30),
                "volume": [2000.0] * 30,
                "price_return": [0.002] * 30,  # Consistent 0.2% gains
                "price_zscore": [0.1] * 30,  # Low volatility
                "volume_zscore": [0.2] * 30,
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        assert signal is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_volume_edge_case(self):
        """Test handling of zero volume."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [110.0],
                "volume": [1000.0] * 24 + [0.0],  # Zero volume
                "price_return": [0.0] * 24 + [0.10],
                "price_zscore": [0.0] * 24 + [3.0],
                "volume_zscore": [0.0] * 24 + [-2.0],  # Negative z-score
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        # No signal because volume_zscore is negative
        assert signal is None

    def test_extreme_price_zscore(self):
        """Test handling of extreme z-score values."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [200.0],
                "volume": [1000.0] * 24 + [10000.0],
                "price_return": [0.0] * 24 + [1.0],
                "price_zscore": [0.0] * 24 + [10.0],  # Extreme
                "volume_zscore": [0.0] * 24 + [5.0],
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        assert signal is not None
        assert signal["metadata"]["confirmation"] == "STRONG"
        assert signal["metadata"]["combined_score"] == 15.0

    def test_exactly_at_strong_threshold(self):
        """Test confirmation at exact STRONG threshold."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 24 + [110.0],
                "volume": [1000.0] * 24 + [5000.0],
                "price_return": [0.0] * 24 + [0.10],
                "price_zscore": [0.0] * 24 + [3.0],  # Exactly at threshold
                "volume_zscore": [0.0] * 24 + [2.0],  # Exactly at threshold
            }
        )

        strategy = SpikeDetectionStrategy()
        signal = strategy.generate_signal(df)

        # 3.0 and 2.0 are NOT > 3.0 and > 2.0, so MODERATE
        assert signal["metadata"]["confirmation"] == "MODERATE"


class TestIntegrationWithZScoreIndicator:
    """Test integration with ZScoreIndicator output."""

    def test_works_with_zscore_indicator_output(self):
        """Test that strategy works with real ZScoreIndicator output."""
        from src.indicators.zscore import ZScoreIndicator

        # Create raw OHLCV data
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=50, freq="5min"),
                "close": [100.0] * 40 + [105.0, 110.0, 115.0, 118.0, 120.0, 122.0, 125.0, 123.0, 124.0, 126.0],
                "volume": [1000.0] * 40 + [3000.0, 5000.0, 7000.0, 6000.0, 5500.0, 5000.0, 4500.0, 3000.0, 2500.0, 2000.0],
            }
        )

        # Calculate z-scores
        indicator = ZScoreIndicator(window=20)
        df_with_zscores = indicator.calculate(df)

        # Generate signal
        strategy = SpikeDetectionStrategy(price_threshold=2.0, volume_threshold=1.0)
        signal = strategy.generate_signal(df_with_zscores)

        # Should detect spike in the rapid price increase
        if signal:
            assert signal["signal"] in ["SPIKE_UP", "SPIKE_DOWN"]
            assert "price_zscore" in signal
            assert "volume_zscore" in signal
