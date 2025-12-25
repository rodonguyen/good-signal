"""Crypto day utilities for 24-hour period aggregation."""

import pandas as pd
from datetime import timedelta, datetime


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
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    # If timestamp is before day_start_hour, it belongs to previous day
    if timestamp.hour < day_start_hour:
        day_date = (timestamp - timedelta(days=1)).date()
    else:
        day_date = timestamp.date()

    return day_date.strftime("%Y-%m-%d")


def aggregate_24h_periods(df: pd.DataFrame, day_start_hour: int = 13) -> pd.DataFrame:
    """Aggregate 1-minute bars into 24-hour periods starting at day_start_hour UTC.

    Args:
        df: DataFrame with 1-minute bars (columns: timestamp, open, high, low, close, volume)
        day_start_hour: Hour when trading day starts (default: 13)

    Returns:
        DataFrame with daily bars (one row per 24-hour period)
    """
    # Ensure timestamp is datetime and UTC
    if df["timestamp"].dtype == "object":
        timestamps = pd.to_datetime(df["timestamp"], utc=True)
    elif df["timestamp"].dt.tz is None:
        timestamps = df["timestamp"].dt.tz_localize("UTC")
    else:
        timestamps = df["timestamp"].dt.tz_convert("UTC")

    # OPTIMIZED: Vectorized crypto day calculation (replaces .apply() bottleneck)
    # Create day identifier using pure vectorized operations
    # If hour < day_start_hour, belongs to previous day
    hour_values = timestamps.dt.hour
    date_values = timestamps.dt.date

    # Calculate day offset: -1 day if hour < day_start_hour, else 0
    day_offset = pd.to_timedelta((hour_values < day_start_hour).astype(int) * -1, unit='D')

    # Apply offset and format as string
    day_series = (pd.to_datetime(date_values) + day_offset).dt.strftime("%Y-%m-%d")

    # Create working DataFrame without full copy (use view where possible)
    # Only create necessary columns
    work_df = pd.DataFrame({
        'timestamp': timestamps,
        'day': day_series,
        'open': df['open'].values,
        'high': df['high'].values,
        'low': df['low'].values,
        'close': df['close'].values,
        'volume': df['volume'].values
    })

    # Aggregate by day
    daily = (
        work_df.groupby("day", sort=True)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "timestamp": ["first", "last"],  # Start and end of period
            }
        )
        .reset_index()
    )

    # Flatten column names
    daily.columns = ["day", "open", "high", "low", "close", "volume", "period_start", "period_end"]

    # Add previous close for True Range calculation
    daily["prev_close"] = daily["close"].shift(1)

    return daily


def get_day_boundaries(date: datetime, day_start_hour: int = 13) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Get start and end times for a crypto trading day.

    Args:
        date: Date to get boundaries for
        day_start_hour: Hour when day starts (default: 13 for 13:00 UTC)

    Returns:
        Tuple of (start_time, end_time) as timezone-aware Timestamps
    """
    # Convert to UTC timezone-aware
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d")

    # Create UTC timezone-aware datetime
    start_time = pd.Timestamp(
        year=date.year if hasattr(date, "year") else date.year,
        month=date.month if hasattr(date, "month") else date.month,
        day=date.day if hasattr(date, "day") else date.day,
        hour=day_start_hour,
        minute=0,
        second=0,
        tz="UTC",
    )

    # End of day: next day at day_start_hour:00:00
    end_time = start_time + timedelta(days=1)

    return start_time, end_time
