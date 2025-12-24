"""
Walk-forward optimization configuration and date window calculation.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_wfo_windows(
    data_start: datetime,
    data_end: datetime,
    train_months: int = 6,
    test_months: int = 3,
    step_months: int = 3,
) -> List[Tuple[datetime, datetime, datetime, datetime]]:
    """
    Calculate walk-forward optimization windows.

    Args:
        data_start: Start date of available data
        data_end: End date of available data
        train_months: Number of months for training period (default 6)
        test_months: Number of months for testing period (default 3)
        step_months: Number of months to step forward between cycles (default 3)

    Returns:
        List of tuples: (train_start, train_end, test_start, test_end)
        Each tuple represents one WFO cycle

    Example:
        >>> start = datetime(2023, 6, 1)
        >>> end = datetime(2024, 12, 31)
        >>> windows = calculate_wfo_windows(start, end, 6, 3, 3)
        >>> len(windows) > 0
        True
    """
    logger.debug(
        f"Calculating WFO windows: data_range={data_start.date()} to {data_end.date()}, "
        f"train={train_months}mo, test={test_months}mo, step={step_months}mo"
    )
    windows = []
    current_train_start = data_start

    while True:
        # Calculate training period end
        train_end = current_train_start + pd.DateOffset(months=train_months) - timedelta(days=1)

        # Calculate test period
        test_start = train_end + timedelta(days=1)
        test_end = test_start + pd.DateOffset(months=test_months) - timedelta(days=1)

        # Check if we have enough data
        if train_end > data_end:
            logger.debug(f"Training period extends beyond data end, stopping")
            break

        # Check if test period extends beyond data
        if test_end > data_end:
            # Use available data for test period
            test_end = data_end
            logger.debug(f"Test period truncated to data end: {test_end.date()}")

        # Only add window if we have complete training period
        if train_end <= data_end:
            windows.append((current_train_start, train_end, test_start, test_end))
            logger.debug(
                f"Window {len(windows)}: Train {current_train_start.date()} to {train_end.date()}, " f"Test {test_start.date()} to {test_end.date()}"
            )

        # Step forward
        current_train_start = current_train_start + pd.DateOffset(months=step_months)

        # Stop if next training start would be beyond data
        if current_train_start >= data_end:
            logger.debug(f"Next training start would be beyond data end, stopping")
            break

    logger.info(f"Calculated {len(windows)} walk-forward windows")
    return windows


def get_data_date_range(data_file: str) -> Tuple[datetime, datetime]:
    """
    Get the date range from a data file (CSV with timestamp column).

    Args:
        data_file: Path to CSV file with 'timestamp' column

    Returns:
        Tuple of (start_date, end_date)
    """
    import pandas as pd
    from pathlib import Path

    df = pd.read_csv(data_file, nrows=1)
    if "timestamp" not in df.columns:
        raise ValueError(f"Data file {data_file} does not have 'timestamp' column")

    # Read first and last rows to get date range
    df_start = pd.read_csv(data_file, nrows=1)
    df_end = pd.read_csv(data_file, skiprows=lambda x: x < 1, nrows=1)

    # For large files, read last line more efficiently
    with open(data_file, "r") as f:
        lines = f.readlines()
        if len(lines) > 1:
            last_line = lines[-1].strip()
            if last_line:
                df_end = pd.read_csv(
                    data_file,
                    skiprows=range(1, len(lines) - 1),
                    nrows=1,
                )

    start_date = pd.to_datetime(df_start["timestamp"].iloc[0], utc=True)
    end_date = pd.to_datetime(df_end["timestamp"].iloc[0], utc=True) if len(df_end) > 0 else start_date

    return start_date, end_date
