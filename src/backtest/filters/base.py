"""Base filter rule interface for pre-entry filtering."""

from abc import ABC, abstractmethod
from typing import Any, Mapping
import pandas as pd


class BaseFilterRule(ABC):
    """Abstract base class for filter rules.

    Filters add a column to the price DataFrame with their filter values,
    then use is_allowed() to check if a trade is allowed.
    """

    def __init__(self, params: Mapping[str, Any]):
        """Initialize filter rule with parameters.

        Args:
            params: Rule-specific parameters from config
        """
        self.params = params
        self.column_name = self._get_column_name()

    @abstractmethod
    def _get_column_name(self) -> str:
        """Return the column name this filter will add to DataFrame.

        Returns:
            Column name (e.g., 'filter_supertrend', 'filter_low_volatility_pct')
        """
        pass

    @abstractmethod
    def apply(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """Apply filter to price DataFrame and add filter value column.

        Args:
            price_df: DataFrame with OHLCV data (timestamp, open, high, low, close, volume)

        Returns:
            DataFrame with added column containing filter values
            Values can be: bool (True/False), int (1/-1 for direction), etc.
        """
        pass

    @abstractmethod
    def is_allowed(self, filter_value: Any, trade_direction: str) -> bool:
        """Check if trade is allowed based on filter value and trade direction.

        Args:
            filter_value: The filter value at the entry timestamp (from the column)
            trade_direction: Trade direction - "long" or "short"

        Returns:
            True if trade is allowed, False if filtered out
        """
        pass
