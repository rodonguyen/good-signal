"""
Core module containing shared utilities, exceptions, and constants.
"""

from backend.core.constants import OrderStatus, PositionStatus, TaskStatus
from backend.core.exceptions import (
    BacktestError,
    GoodSignalError,
    RiskLimitError,
    TradingError,
)
from backend.core.logging import get_logger, setup_logging

__all__ = [
    # Exceptions
    "GoodSignalError",
    "BacktestError",
    "TradingError",
    "RiskLimitError",
    # Constants
    "TaskStatus",
    "PositionStatus",
    "OrderStatus",
    # Logging
    "setup_logging",
    "get_logger",
]
