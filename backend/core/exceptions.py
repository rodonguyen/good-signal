"""
Custom exception classes for the Good Signal trading application.

These exceptions provide structured error handling with error codes
and detailed messages for debugging and API responses.
"""

from typing import Any


class GoodSignalError(Exception):
    """
    Base exception for all Good Signal application errors.

    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code for client handling
        details: Additional error context and debugging information
    """

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.error_code}, message={self.message})"


class BacktestError(GoodSignalError):
    """
    Exception raised for backtest-related errors.

    Raised when:
    - Backtest configuration is invalid
    - Historical data is unavailable or corrupted
    - Backtest execution fails
    - Results processing encounters errors
    """

    def __init__(
        self,
        message: str,
        error_code: str = "BACKTEST_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code, details)


class TradingError(GoodSignalError):
    """
    Exception raised for trading operation errors.

    Raised when:
    - Order submission fails
    - Position management encounters issues
    - Exchange communication errors occur
    - Invalid trading parameters are provided
    """

    def __init__(
        self,
        message: str,
        error_code: str = "TRADING_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code, details)


class RiskLimitError(GoodSignalError):
    """
    Exception raised when risk limits are violated.

    Raised when:
    - Position size exceeds maximum allowed
    - Daily loss limit is reached
    - Drawdown threshold is breached
    - Exposure limits are exceeded
    """

    def __init__(
        self,
        message: str,
        error_code: str = "RISK_LIMIT_EXCEEDED",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code, details)


class ValidationError(GoodSignalError):
    """
    Exception raised for input validation errors.

    Raised when:
    - Request parameters are invalid
    - Data format is incorrect
    - Required fields are missing
    """

    def __init__(
        self,
        message: str,
        error_code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code, details)


class NotFoundError(GoodSignalError):
    """
    Exception raised when a requested resource is not found.

    Raised when:
    - Database record does not exist
    - File or resource is missing
    - Referenced entity is unavailable
    """

    def __init__(
        self,
        message: str,
        error_code: str = "NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code, details)


class DatabaseError(GoodSignalError):
    """
    Exception raised for database operation errors.

    Raised when:
    - Database connection fails
    - Query execution errors occur
    - Transaction rollback is needed
    """

    def __init__(
        self,
        message: str,
        error_code: str = "DATABASE_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code, details)
