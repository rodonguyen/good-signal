"""Crypto-specific utility functions for 24-hour day definitions and ATR calculations."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Tuple, Optional


def define_crypto_day(timestamp: pd.Timestamp, day_start_hour: int = 13) -> str:
    """Define which crypto trading day a timestamp belongs to.
    
    Crypto trading days start at 13:00 UTC and run for 24 hours.
    
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


def get_day_boundaries(date: datetime, day_start_hour: int = 13) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Get start and end times for a crypto trading day.
    
    Args:
        date: Date to get boundaries for
        day_start_hour: Hour when day starts (default: 13 for 13:00 UTC)
        
    Returns:
        Tuple of (start_time, end_time) as timezone-aware Timestamps
    """
    # Convert to UTC timezone-aware
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d')
    
    # Create UTC timezone-aware datetime
    start_time = pd.Timestamp(
        year=date.year if hasattr(date, 'year') else date.year,
        month=date.month if hasattr(date, 'month') else date.month,
        day=date.day if hasattr(date, 'day') else date.day,
        hour=day_start_hour,
        minute=0,
        second=0,
        tz='UTC'
    )
    
    # End of day: next day at day_start_hour:00:00
    end_time = start_time + timedelta(days=1)
    
    return start_time, end_time


def get_previous_day_close(df: pd.DataFrame, current_day: str, day_start_hour: int = 13) -> Optional[float]:
    """Get the close price at the start of the current trading day (previous day's close).
    
    Args:
        df: DataFrame with timestamp and close columns
        current_day: Current day identifier (YYYY-MM-DD)
        day_start_hour: Hour when day starts (default: 13)
        
    Returns:
        Close price at 13:00 UTC of previous day, or None if not found
    """
    # Parse current day to get the 13:00 UTC timestamp
    day_date = datetime.strptime(current_day, '%Y-%m-%d')
    day_start = day_date.replace(hour=day_start_hour, minute=0, second=0, microsecond=0)
    
    # Ensure UTC
    if df['timestamp'].dtype == 'object':
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    elif df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    
    # Find the exact timestamp or closest before
    day_start_ts = pd.Timestamp(day_start, tz='UTC')
    
    # Get price at or just before day start
    mask = df['timestamp'] <= day_start_ts
    if mask.any():
        close_price = df.loc[mask, 'close'].iloc[-1]
        return float(close_price)
    
    return None


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


def calculate_crypto_atr(daily_bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR (Average True Range) for crypto 24-hour periods.
    
    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = rolling average of True Range over specified period.
    
    Args:
        daily_bars: DataFrame with daily bars (from aggregate_24h_periods)
        period: Number of periods for ATR calculation (default: 14)
        
    Returns:
        Series with ATR values
    """
    # Calculate True Range
    tr1 = daily_bars['high'] - daily_bars['low']
    tr2 = abs(daily_bars['high'] - daily_bars['prev_close'])
    tr3 = abs(daily_bars['low'] - daily_bars['prev_close'])
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate ATR as rolling average
    atr = true_range.rolling(window=period, min_periods=1).mean()
    
    return atr


def get_previous_day_atr(atr_series: pd.Series, current_day: str, daily_bars: pd.DataFrame) -> Optional[float]:
    """Get ATR value from the previous 24-hour period.
    
    Args:
        atr_series: Series with ATR values (indexed by day)
        current_day: Current day identifier (YYYY-MM-DD)
        daily_bars: DataFrame with daily bars (for day matching)
        
    Returns:
        ATR value from previous day, or None if not found
    """
    # Find current day index
    if 'day' in daily_bars.columns:
        day_idx = daily_bars[daily_bars['day'] == current_day].index
        if len(day_idx) > 0:
            current_idx = day_idx[0]
            # Get previous day's ATR
            if current_idx > 0:
                prev_idx = current_idx - 1
                return float(atr_series.iloc[prev_idx])
    
    return None

