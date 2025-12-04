"""Datetime utility functions."""

from datetime import datetime, timezone

try:
    import pandas as pd

    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False


def to_local_timezone(dt: datetime) -> datetime:
    """
    Convert datetime to local timezone.

    Args:
        dt: Datetime object (naive or timezone-aware) or pandas Timestamp

    Returns:
        Datetime in local timezone (naive)
    """
    # Convert pandas Timestamp to Python datetime if needed
    if _HAS_PANDAS and isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()

    if dt.tzinfo is None:
        # Assume UTC if naive (exchange data is typically UTC)
        dt = dt.replace(tzinfo=timezone.utc)

    # Convert to local timezone
    local_dt = dt.astimezone()

    # Return naive datetime in local timezone
    return local_dt.replace(tzinfo=None)
