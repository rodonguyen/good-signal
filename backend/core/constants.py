"""
Application-wide constants and enumerations.

These constants provide type-safe status codes and configuration
values used throughout the Good Signal trading application.
"""

from enum import Enum, auto


class TaskStatus(str, Enum):
    """
    Status of asynchronous tasks (e.g., backtests, optimizations).

    Lifecycle: PENDING -> RUNNING -> (COMPLETED | FAILED | CANCELLED)
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal_states(cls) -> set["TaskStatus"]:
        """Return states that indicate task completion."""
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED}

    @property
    def is_terminal(self) -> bool:
        """Check if this status represents a completed task."""
        return self in self.terminal_states()

    @property
    def is_active(self) -> bool:
        """Check if this status represents an active task."""
        return self in {self.PENDING, self.RUNNING}


class PositionStatus(str, Enum):
    """
    Status of trading positions.

    Lifecycle: PENDING -> OPEN -> CLOSED
    """

    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"

    @property
    def is_active(self) -> bool:
        """Check if position is currently active in the market."""
        return self == self.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if position has been closed."""
        return self in {self.CLOSED, self.LIQUIDATED}


class OrderStatus(str, Enum):
    """
    Status of trading orders.

    Lifecycle: PENDING -> SUBMITTED -> (FILLED | PARTIALLY_FILLED | CANCELLED | REJECTED)
    """

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"

    @classmethod
    def terminal_states(cls) -> set["OrderStatus"]:
        """Return states that indicate order completion."""
        return {cls.FILLED, cls.CANCELLED, cls.REJECTED, cls.EXPIRED}

    @property
    def is_terminal(self) -> bool:
        """Check if this status represents a completed order."""
        return self in self.terminal_states()

    @property
    def is_active(self) -> bool:
        """Check if this status represents an active order."""
        return self in {self.PENDING, self.SUBMITTED, self.PARTIALLY_FILLED}

    @property
    def is_successful(self) -> bool:
        """Check if order was successfully filled."""
        return self in {self.FILLED, self.PARTIALLY_FILLED}


class OrderSide(str, Enum):
    """Trading order side (direction)."""

    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "OrderSide":
        """Get the opposite side."""
        return OrderSide.SELL if self == OrderSide.BUY else OrderSide.BUY


class OrderType(str, Enum):
    """Trading order type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(str, Enum):
    """Order time-in-force settings."""

    GTC = "gtc"  # Good Till Cancelled
    IOC = "ioc"  # Immediate Or Cancel
    FOK = "fok"  # Fill Or Kill
    DAY = "day"  # Day Order


class Timeframe(str, Enum):
    """
    Supported candlestick timeframes.

    Values represent the duration in a standard format
    compatible with most exchange APIs.
    """

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"
    D1 = "1d"
    D3 = "3d"
    W1 = "1w"
    MO1 = "1M"

    @property
    def minutes(self) -> int:
        """Convert timeframe to minutes."""
        mapping = {
            self.M1: 1,
            self.M3: 3,
            self.M5: 5,
            self.M15: 15,
            self.M30: 30,
            self.H1: 60,
            self.H2: 120,
            self.H4: 240,
            self.H6: 360,
            self.H8: 480,
            self.H12: 720,
            self.D1: 1440,
            self.D3: 4320,
            self.W1: 10080,
            self.MO1: 43200,  # Approximate
        }
        return mapping[self]


# API Constants
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"

# Pagination defaults
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000

# Task execution limits
MAX_TASK_RETRIES = 3
TASK_TIMEOUT_SECONDS = 3600  # 1 hour

# Trading constants
MIN_POSITION_SIZE = 0.0001
MAX_LEVERAGE = 125
DEFAULT_SLIPPAGE_PERCENT = 0.1
