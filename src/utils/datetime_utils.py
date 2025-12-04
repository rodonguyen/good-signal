"""Datetime utility functions."""
from datetime import datetime, timezone


def to_local_timezone(dt: datetime) -> datetime:
    """
    Convert datetime to local timezone.

    Args:
        dt: Datetime object (naive or timezone-aware)

    Returns:
        Datetime in local timezone (naive)
    """
    if dt.tzinfo is None:
        # Assume UTC if naive (exchange data is typically UTC)
        dt = dt.replace(tzinfo=timezone.utc)

    # Convert to local timezone
    local_dt = dt.astimezone()

    # Return naive datetime in local timezone
    return local_dt.replace(tzinfo=None)
