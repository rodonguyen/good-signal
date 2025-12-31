"""Filter pipeline that applies multiple filter rules to DataFrame."""

from typing import Any, Mapping
import pandas as pd

from .base import BaseFilterRule


class FilterPipeline:
    """Pipeline that applies multiple filter rules to price DataFrame."""

    def __init__(
        self,
        rules: list[BaseFilterRule],
        logic_mode: str = "AND",
    ):
        """Initialize filter pipeline.

        Args:
            rules: List of filter rule instances
            logic_mode: "AND" (all must pass) or "OR" (any passes)
        """
        self.rules = rules
        self.logic_mode = logic_mode.upper()
        if self.logic_mode not in ("AND", "OR"):
            raise ValueError(f"logic_mode must be 'AND' or 'OR', got: {logic_mode}")

    def apply(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """Apply all filters to price DataFrame, adding filter columns.

        Args:
            price_df: DataFrame with OHLCV data

        Returns:
            DataFrame with filter columns added (one column per filter)
        """
        df = price_df.copy()

        # Apply each filter sequentially
        for rule in self.rules:
            try:
                df = rule.apply(df)
            except Exception as e:
                print(f"Warning: Filter {rule.__class__.__name__} failed: {e}")
                # On error, add column with NaN (will filter out all trades)
                df[rule.column_name] = pd.NA

        return df

    def is_allowed(self, df: pd.DataFrame, row_idx: int, trade_direction: str) -> bool:
        """Check if trade is allowed at given row index.

        Args:
            df: DataFrame with filter columns (after apply())
            row_idx: Row index to check
            trade_direction: "long" or "short"

        Returns:
            True if trade is allowed, False if filtered out
        """
        if not self.rules:
            return True  # No filters = allow all

        if row_idx < 0 or row_idx >= len(df):
            return False

        results = []
        for rule in self.rules:
            try:
                # Get filter value at this row
                if rule.column_name not in df.columns:
                    results.append(False)
                    continue

                filter_value = df.iloc[row_idx][rule.column_name]
                allowed = rule.is_allowed(filter_value, trade_direction)
                results.append(allowed)
            except Exception as e:
                print(f"Warning: Filter {rule.__class__.__name__} check failed: {e}")
                results.append(False)

        # Combine results based on logic mode
        if self.logic_mode == "AND":
            return all(results)
        else:  # OR
            return any(results)
