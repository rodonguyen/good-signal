"""Filter pipeline that composes multiple filter rules."""

from typing import Any, Mapping
import pandas as pd
from pathlib import Path

from .base import BaseFilterRule
from ..data.ohlcv_store import OhlcvStore


class FilterPipeline:
    """Pipeline that applies multiple filter rules with AND/OR logic."""

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

    def build_allow_map(
        self,
        minute_df: pd.DataFrame,
        hourly_df: pd.DataFrame | None,
        daily_df: pd.DataFrame | None,
    ) -> dict[str, bool]:
        """Build a day -> allow/deny map by applying all rules.

        Args:
            minute_df: 1-minute OHLCV data
            hourly_df: 1-hour OHLCV data (optional)
            daily_df: Daily (24h) OHLCV data (optional)

        Returns:
            Dictionary mapping day_key -> bool (True = allowed, False = filtered)
        """
        if not self.rules:
            # No rules = allow all days
            return {}

        # Prepare all rules
        prepared_data = {}
        for rule in self.rules:
            prepared_data[rule] = rule.prepare(minute_df, hourly_df, daily_df)

        # Get unique days from daily_df (if available) or derive from minute_df
        if daily_df is not None and "day" in daily_df.columns:
            unique_days = set(daily_df["day"].unique())
        else:
            # Fallback: derive days from minute_df timestamps
            # This is a simple approach - strategies using days should provide daily_df
            minute_df = minute_df.copy()
            if "timestamp" in minute_df.columns:
                minute_df["timestamp"] = pd.to_datetime(minute_df["timestamp"], utc=True)
                # Use date as day key (simple fallback)
                unique_days = set(minute_df["timestamp"].dt.date.astype(str))
            else:
                unique_days = set()

        # Evaluate each day
        allow_map: dict[str, bool] = {}
        for day_key in unique_days:
            results = []
            for rule in self.rules:
                try:
                    result = rule.allow_entry(day_key, prepared_data[rule])
                    results.append(result)
                except Exception as e:
                    # If rule fails, default to False (filter out)
                    print(f"Warning: Filter rule {rule.__class__.__name__} failed for day {day_key}: {e}")
                    results.append(False)

            # Combine results based on logic mode
            if self.logic_mode == "AND":
                allow_map[day_key] = all(results)
            else:  # OR
                allow_map[day_key] = any(results)

        return allow_map

    def is_allowed(self, day_key: str, allow_map: dict[str, bool]) -> bool:
        """Check if a day is allowed using the pre-built allow map.

        Args:
            day_key: Day identifier
            allow_map: Pre-built allow map from build_allow_map()

        Returns:
            True if allowed, False if filtered (or not in map)
        """
        return allow_map.get(day_key, True)  # Default to allowed if not in map
