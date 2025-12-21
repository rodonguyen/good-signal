"""Crypto day utilities for 24-hour period aggregation."""

import pandas as pd
from datetime import timedelta


def define_crypto_day(timestamp: pd.Timestamp, day_start_hour: int = 13) -> str:
    """Define which crypto trading day a timestamp belongs to.
    
    Crypto trading days start at day_start_hour UTC and run for 24 hours.
    
    Args:
        timestamp: Timestamp to classify
        day_start_hour: Hour of day when trading day starts (default: 13 for 13:00 UTC)
        
    Returns:
        Day identifier string (YYYY-MM-DD format based on day start)
    """
    # Convert to UTC if not already
    if timestamp.tz is None:
        timestamp = timestamp.tz_localize('UTC')
    else:
        timestamp = timestamp.tz_convert('UTC')
    
    # If timestamp is before day_start_hour, it belongs to previous day
    if timestamp.hour < day_start_hour:
        day_date = (timestamp - timedelta(days=1)).date()
    else:
        day_date = timestamp.date()
    
    return day_date.strftime('%Y-%m-%d')


def aggregate_24h_periods(df: pd.DataFrame, day_start_hour: int = 13) -> pd.DataFrame:
    """Aggregate 1-minute bars into 24-hour periods starting at day_start_hour UTC.
    
    Args:
        df: DataFrame with 1-minute bars (columns: timestamp, open, high, low, close, volume)
        day_start_hour: Hour when trading day starts (default: 13)
        
    Returns:
        DataFrame with daily bars (one row per 24-hour period)
    """
    # Ensure timestamp is datetime and UTC
    if df['timestamp'].dtype == 'object':
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    elif df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    else:
        df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
    
    # Add day identifier
    df = df.copy()
    df['day'] = df['timestamp'].apply(lambda x: define_crypto_day(x, day_start_hour))
    
    # Aggregate by day
    daily = df.groupby('day').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'timestamp': ['first', 'last']  # Start and end of period
    }).reset_index()
    
    # Flatten column names
    daily.columns = ['day', 'open', 'high', 'low', 'close', 'volume', 'period_start', 'period_end']
    
    # Add previous close for True Range calculation
    daily['prev_close'] = daily['close'].shift(1)
    
    return daily

