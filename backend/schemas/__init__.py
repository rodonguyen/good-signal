"""
Pydantic schemas for request/response validation.

This module contains base schemas and common schema utilities
used throughout the application.
"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Type variable for generic pagination
T = TypeVar("T")


class BaseSchema(BaseModel):
    """
    Base schema with common configuration.

    All application schemas should inherit from this class
    to ensure consistent serialization behavior.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
        },
    )


class TimestampMixin(BaseModel):
    """Mixin for schemas with timestamp fields."""

    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class PaginationParams(BaseModel):
    """Parameters for paginated requests."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Items per page",
    )

    @property
    def offset(self) -> int:
        """Calculate offset for database queries."""
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseSchema, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T] = Field(description="List of items")
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    pages: int = Field(description="Total number of pages")

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        """Create a paginated response from items and pagination info."""
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


class ErrorResponse(BaseSchema):
    """Standard error response format."""

    error: str = Field(description="Error code")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional error details",
    )


class SuccessResponse(BaseSchema):
    """Standard success response for operations without specific return data."""

    success: bool = Field(default=True, description="Operation success status")
    message: str = Field(description="Success message")


__all__ = [
    "BaseSchema",
    "TimestampMixin",
    "PaginationParams",
    "PaginatedResponse",
    "ErrorResponse",
    "SuccessResponse",
]
