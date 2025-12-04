"""
Unit tests for BybitFetcher.
"""
import pytest
from unittest.mock import Mock, patch
from src.data.bybit_fetcher import BybitFetcher


def test_bybit_fetcher_initialization():
    """Test BybitFetcher initializes correctly."""
    fetcher = BybitFetcher()
    
    assert fetcher.max_retries == 3
    assert fetcher.base_retry_delay == 5
    assert fetcher.exchange is not None


@patch('src.data.bybit_fetcher.ccxt.bybit')
def test_get_ohlcv_success(mock_bybit_class):
    """Test successful OHLCV fetch."""
    import pandas as pd
    
    # Mock exchange
    mock_exchange = Mock()
    mock_exchange.fetch_ohlcv.return_value = [
        [1701388800000, 45000, 45500, 44500, 45000, 1000],
        [1701392400000, 45100, 45600, 44600, 45100, 1100],
    ]
    mock_bybit_class.return_value = mock_exchange
    
    fetcher = BybitFetcher()
    df = fetcher.get_ohlcv('BTCUSDT', '1h', limit=2)
    
    assert df is not None
    assert len(df) == 2
    assert 'timestamp' in df.columns
    assert 'close' in df.columns


@patch('src.data.bybit_fetcher.ccxt.bybit')
def test_get_ohlcv_network_error_retry(mock_bybit_class):
    """Test retry logic on network errors."""
    import ccxt
    
    # Mock exchange that fails twice then succeeds
    mock_exchange = Mock()
    mock_exchange.fetch_ohlcv.side_effect = [
        ccxt.NetworkError("Network error"),
        ccxt.NetworkError("Network error"),
        [[1701388800000, 45000, 45500, 44500, 45000, 1000]],
    ]
    mock_bybit_class.return_value = mock_exchange
    
    fetcher = BybitFetcher()
    df = fetcher.get_ohlcv('BTCUSDT', '1h', limit=1)
    
    # Should succeed on third attempt
    assert df is not None
    assert mock_exchange.fetch_ohlcv.call_count == 3


def test_test_connection_success():
    """Test connection test succeeds."""
    with patch('src.data.bybit_fetcher.ccxt.bybit') as mock_bybit_class:
        mock_exchange = Mock()
        mock_exchange.load_markets.return_value = {}
        mock_bybit_class.return_value = mock_exchange
        
        fetcher = BybitFetcher()
        result = fetcher.test_connection()
        
        assert result is True

