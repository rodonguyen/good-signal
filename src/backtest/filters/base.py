"""Base filter rule interface for pre-entry filtering."""

from abc import ABC, abstractmethod
from typing import Any, Mapping
import pandas as pd


class BaseFilterRule(ABC):
    """Abstract base class for pre-entry filter rules.

    Filter rules evaluate market conditions and return True/False
    for whether a trading day/period should be allowed.
    """

    def __init__(self, params: Mapping[str, Any]):
        """Initialize filter rule with parameters.

        Args:
            params: Rule-specific parameters from config
        """
        self.params = params

    @abstractmethod
    def prepare(
        self,
        minute_df: pd.DataFrame,
        hourly_df: pd.DataFrame | None,
        daily_df: pd.DataFrame | None,
    ) -> Any:
        """Prepare filter data structures (e.g., calculate indicators).

        This is called once before evaluating multiple days.
        Use this to cache expensive calculations.

        Args:
            minute_df: 1-minute OHLCV data
            hourly_df: 1-hour OHLCV data (if available)
            daily_df: Daily (24h) OHLCV data (if available)

        Returns:
            Prepared data structure (can be anything, passed to allow_entry)
        """
        pass

    @abstractmethod
    def allow_entry(self, day_key: str, prepared: Any) -> bool:
        """Check if entry is allowed for a given day.

        Args:
            day_key: Day identifier (e.g., "2024-01-15")
            prepared: Prepared data from prepare() method

        Returns:
            True if entry is allowed, False if filtered out
        """
        pass
