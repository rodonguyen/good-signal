"""
Comprehensive test suite for ZScoreIndicator.

Tests cover:
- Normal operation with valid data
- Edge cases (insufficient data, zero volatility)
- Input validation
- Z-score calculation accuracy
- NaN handling
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.indicators.zscore import ZScoreIndicator


class TestZScoreIndicatorInitialization:
    """Test ZScoreIndicator initialization and configuration."""

    def test_default_initialization(self):
        """Test indicator initializes with default window."""
        indicator = ZScoreIndicator()
        assert indicator.window == 20

    def test_custom_window_initialization(self):
        """Test indicator initializes with custom window."""
        indicator = ZScoreIndicator(window=50)
        assert indicator.window == 50

    def test_repr_string(self):
        """Test string representation."""
        indicator = ZScoreIndicator(window=30)
        assert repr(indicator) == "ZScoreIndicator(window=30)"


class TestZScoreIndicatorValidation:
    """Test input validation and error handling."""

    def test_missing_close_column_raises_error(self):
        """Test that missing 'close' column raises ValueError."""
        indicator = ZScoreIndicator(window=5)
        df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"), "volume": [1000] * 10})

        with pytest.raises(ValueError, match="must have 'close' and 'volume' columns"):
            indicator.calculate(df)

    def test_missing_volume_column_raises_error(self):
        """Test that missing 'volume' column raises ValueError."""
        indicator = ZScoreIndicator(window=5)
        df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"), "close": [100] * 10})

        with pytest.raises(ValueError, match="must have 'close' and 'volume' columns"):
            indicator.calculate(df)

    def test_insufficient_data_warning(self, caplog):
        """Test warning logged when data is less than window size."""
        indicator = ZScoreIndicator(window=20)
        df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"), "close": [100] * 10, "volume": [1000] * 10})

        result = indicator.calculate(df)

        # Should log warning but still return DataFrame
        assert "Not enough data" in caplog.text
        assert result is not None
        assert len(result) == 10


class TestZScoreCalculationAccuracy:
    """Test z-score calculation correctness."""

    @pytest.fixture
    def simple_data(self):
        """Create simple test data with known statistics."""
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [
                    100,
                    102,
                    101,
                    103,
                    105,
                    110,
                    108,
                    107,
                    106,
                    120,
                    121,
                    119,
                    118,
                    122,
                    125,
                    123,
                    124,
                    126,
                    130,
                    128,
                    127,
                    129,
                    135,
                    133,
                    132,
                ],
                "volume": [
                    1000,
                    1050,
                    1000,
                    1100,
                    1000,
                    5000,
                    1000,
                    1050,
                    1000,
                    6000,
                    1100,
                    1200,
                    1050,
                    1300,
                    1400,
                    1250,
                    1350,
                    1450,
                    8000,
                    1500,
                    1400,
                    1600,
                    9000,
                    1700,
                    1650,
                ],
            }
        )

    def test_adds_required_columns(self, simple_data):
        """Test that all required columns are added."""
        indicator = ZScoreIndicator(window=5)
        result = indicator.calculate(simple_data)

        assert "price_return" in result.columns
        assert "price_zscore" in result.columns
        assert "volume_zscore" in result.columns

    def test_preserves_original_columns(self, simple_data):
        """Test that original columns are preserved."""
        indicator = ZScoreIndicator(window=5)
        original_cols = set(simple_data.columns)
        result = indicator.calculate(simple_data)

        assert original_cols.issubset(set(result.columns))

    def test_price_return_calculation(self, simple_data):
        """Test price return percentage calculation."""
        indicator = ZScoreIndicator(window=5)
        result = indicator.calculate(simple_data)

        # First return should be NaN
        assert pd.isna(result["price_return"].iloc[0])

        # Second return should be (102-100)/100 = 0.02
        expected_return = (102 - 100) / 100
        assert result["price_return"].iloc[1] == pytest.approx(expected_return, rel=1e-6)

    def test_zscore_with_spike(self):
        """Test z-score correctly identifies spike."""
        # Create data with clear spike at the end
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 23 + [110.0, 115.0],  # 10% then 4.5% increase
                "volume": [1000.0] * 23 + [5000.0, 6000.0],  # 5x then 6x increase
            }
        )

        indicator = ZScoreIndicator(window=5)
        result = indicator.calculate(df)

        # Last two rows should have elevated z-scores (above typical threshold of 1.5-2.0)
        assert result["price_zscore"].iloc[-2] > 1.5
        assert result["volume_zscore"].iloc[-2] > 1.5

    def test_zscore_with_negative_spike(self):
        """Test z-score correctly identifies negative spike."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=25, freq="1h"),
                "close": [100.0] * 23 + [90.0, 85.0],  # -10% then -5.6% drop
                "volume": [1000.0] * 23 + [5000.0, 6000.0],
            }
        )

        indicator = ZScoreIndicator(window=5)
        result = indicator.calculate(df)

        # Last row should have negative price z-score, positive volume z-score
        assert result["price_zscore"].iloc[-2] < -1.5
        assert result["volume_zscore"].iloc[-2] > 1.5


class TestZScoreEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_volatility_handled_gracefully(self):
        """Test that constant prices (zero std dev) are handled."""
        indicator = ZScoreIndicator(window=5)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"),
                "close": [100.0] * 10,  # Constant price
                "volume": [1000.0] * 10,  # Constant volume
            }
        )

        result = indicator.calculate(df)

        # Should not crash, z-scores should be NaN (div by zero)
        assert result is not None
        assert len(result) == 10
        # After window, std dev = 0, so z-score = NaN
        assert pd.isna(result["price_zscore"].iloc[5:]).all()
        assert pd.isna(result["volume_zscore"].iloc[5:]).all()

    def test_single_candle_data(self):
        """Test behavior with minimal data."""
        indicator = ZScoreIndicator(window=5)
        df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=1, freq="1h"), "close": [100.0], "volume": [1000.0]})

        result = indicator.calculate(df)

        # Should return DataFrame with NaN z-scores
        assert len(result) == 1
        assert pd.isna(result["price_return"].iloc[0])
        assert pd.isna(result["price_zscore"].iloc[0])

    def test_exact_window_size_data(self):
        """Test with data exactly equal to window size."""
        indicator = ZScoreIndicator(window=10)
        # Use varied data to avoid zero variance edge case with linear data
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"),
                "close": [100, 101, 99, 102, 98, 103, 97, 104, 96, 105],  # Varied prices
                "volume": [1000, 1100, 900, 1200, 800, 1300, 700, 1400, 600, 1500],  # Varied volume
            }
        )

        result = indicator.calculate(df)

        # Should calculate z-scores for last row
        assert len(result) == 10
        # With window=10 and 10 rows, volume z-score should be calculable
        assert not pd.isna(result["volume_zscore"].iloc[-1])

    def test_very_large_window(self):
        """Test with window larger than typical data."""
        indicator = ZScoreIndicator(window=100)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=50, freq="1h"),
                "close": np.random.uniform(100, 110, 50),
                "volume": np.random.uniform(1000, 2000, 50),
            }
        )

        result = indicator.calculate(df)

        # Should return data but z-scores will be mostly NaN
        assert len(result) == 50
        # No z-scores until we have 100 data points
        assert pd.isna(result["price_zscore"].iloc[-1])

    def test_negative_prices_handled(self):
        """Test that negative price changes are handled correctly."""
        indicator = ZScoreIndicator(window=5)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"),
                "close": [100, 95, 90, 85, 80, 75, 70, 65, 60, 55],  # Declining
                "volume": [1000] * 10,
            }
        )

        result = indicator.calculate(df)

        # Negative returns should be calculated correctly
        assert (result["price_return"].iloc[1:] < 0).all()
        # Z-scores should exist
        assert not pd.isna(result["price_zscore"].iloc[6:]).all()


class TestZScoreWindowParameter:
    """Test different window parameter values."""

    @pytest.mark.parametrize("window", [5, 10, 20, 50, 100])
    def test_various_window_sizes(self, window):
        """Test that different window sizes work correctly."""
        indicator = ZScoreIndicator(window=window)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=window + 10, freq="1h"),
                "close": np.random.uniform(100, 110, window + 10),
                "volume": np.random.uniform(1000, 2000, window + 10),
            }
        )

        result = indicator.calculate(df)

        assert len(result) == window + 10
        # After window period, should have valid z-scores
        assert not pd.isna(result["price_zscore"].iloc[window:]).any()

    def test_window_1_edge_case(self):
        """Test minimum window size of 1."""
        indicator = ZScoreIndicator(window=1)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="1h"),
                "close": [100, 101, 102, 103, 104],
                "volume": [1000, 1100, 1200, 1300, 1400],
            }
        )

        result = indicator.calculate(df)

        # Window of 1 means std dev is 0, so z-scores will be NaN or inf
        assert len(result) == 5


class TestZScoreRealWorldScenarios:
    """Test realistic market scenarios."""

    def test_high_volatility_period(self):
        """Test during high volatility (crypto flash crash)."""
        # Simulate flash crash scenario
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=30, freq="5min"),
                "close": [50000] * 10 + [45000, 40000, 35000, 30000, 32000] + [50000] * 15,
                "volume": [1000] * 10 + [10000, 15000, 20000, 25000, 20000] + [1000] * 15,
            }
        )

        indicator = ZScoreIndicator(window=10)
        result = indicator.calculate(df)

        # During crash, should detect extreme z-scores
        crash_period = result.iloc[11:15]
        assert (crash_period["price_zscore"].abs() > 1.5).any()
        assert (crash_period["volume_zscore"] > 1.5).any()

    def test_gradual_trend_no_spike(self):
        """Test gradual trend doesn't trigger spike detection."""
        # Gradual uptrend
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=50, freq="1h"),
                "close": np.linspace(100, 120, 50),  # Smooth 20% increase
                "volume": [1000] * 50,
            }
        )

        indicator = ZScoreIndicator(window=20)
        result = indicator.calculate(df)

        # Should not have extreme z-scores (drop NaN values first)
        price_zscores = result["price_zscore"].dropna()
        assert (price_zscores.abs() < 2.5).all()

    def test_weekend_low_volume(self):
        """Test low volume periods (weekend trading)."""
        # Simulate weekend low volume
        volumes = [5000] * 10 + [500] * 10 + [5000] * 10  # Weekend dip
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=30, freq="1h"),
                "close": [100 + i * 0.5 for i in range(30)],  # Slight uptrend
                "volume": volumes,
            }
        )

        indicator = ZScoreIndicator(window=10)
        result = indicator.calculate(df)

        # Low volume should show negative volume z-score
        weekend_period = result.iloc[10:20]
        assert (weekend_period["volume_zscore"] < 0).any()


class TestZScoreIntegration:
    """Integration tests with realistic data structures."""

    def test_works_with_bybit_ohlcv_format(self):
        """Test with DataFrame format returned by BybitFetcher."""
        # Simulate Bybit OHLCV format
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=100, freq="1h"),
                "open": np.random.uniform(99, 101, 100),
                "high": np.random.uniform(100, 102, 100),
                "low": np.random.uniform(98, 100, 100),
                "close": np.random.uniform(99, 101, 100),
                "volume": np.random.uniform(1000, 2000, 100),
            }
        )

        indicator = ZScoreIndicator(window=20)
        result = indicator.calculate(df)

        # Should preserve all OHLCV columns
        assert all(col in result.columns for col in ["open", "high", "low", "close", "volume"])
        # Should add z-score columns
        assert "price_zscore" in result.columns
        assert "volume_zscore" in result.columns

    def test_chaining_with_other_indicators(self):
        """Test that indicator can be chained with others."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=50, freq="1h"),
                "close": np.random.uniform(100, 110, 50),
                "volume": np.random.uniform(1000, 2000, 50),
            }
        )

        # Add some other indicator column first
        df["sma_20"] = df["close"].rolling(window=20).mean()

        indicator = ZScoreIndicator(window=20)
        result = indicator.calculate(df)

        # Should preserve previous indicator columns
        assert "sma_20" in result.columns
        # Should add new columns
        assert "price_zscore" in result.columns


class TestZScorePerformance:
    """Test performance characteristics."""

    def test_handles_large_dataset(self):
        """Test with large dataset (1000+ candles)."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=1000, freq="1h"),
                "close": np.random.uniform(100, 110, 1000),
                "volume": np.random.uniform(1000, 2000, 1000),
            }
        )

        indicator = ZScoreIndicator(window=20)
        result = indicator.calculate(df)

        assert len(result) == 1000
        # Should have valid z-scores after window
        assert not pd.isna(result["price_zscore"].iloc[21:]).any()

    def test_repeated_calculations_identical(self):
        """Test that repeated calculations give identical results."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=50, freq="1h"),
                "close": np.random.uniform(100, 110, 50),
                "volume": np.random.uniform(1000, 2000, 50),
            }
        )

        indicator = ZScoreIndicator(window=20)
        result1 = indicator.calculate(df.copy())
        result2 = indicator.calculate(df.copy())

        pd.testing.assert_frame_equal(result1, result2)
