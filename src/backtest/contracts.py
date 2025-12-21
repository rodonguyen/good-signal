"""
Backtest contracts and shared types.

Key idea:
- Live trading strategies in Good Signal implement `src/strategies/base.py` (signal generation).
- Backtest strategies implement `BaseBacktestStrategy` below (trade generation).

This separation keeps each interface small and SOLID.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping

import pandas as pd

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class BacktestContext:
    """
    Context shared across backtest steps and strategies.

    Keep this minimal and stable. Add to it deliberately because it becomes a dependency
    of every strategy implementation.
    """

    symbol: str
    fee_rate: float  # total round-trip fee rate on (entry_notional + exit_notional)
    raw_1m_dir: str
    outputs: Mapping[str, str]  # trades_dir, portfolio_dir, reports_dir
    extra: Mapping[str, Any] | None = None


REQUIRED_TRADE_COLUMNS: tuple[str, ...] = (
    "symbol",
    "strategy_id",
    "entry_time",
    "exit_time",
    "direction",
    "entry_price",
    "exit_price",
    "stop_level",
    "tp_level",
    "raw_pnl",
    "fees",
    "net_pnl",
    "exit_reason",
)


def validate_trades_df(trades: pd.DataFrame, *, required_columns: Iterable[str] = REQUIRED_TRADE_COLUMNS) -> None:
    """
    Validate a trades DataFrame produced by a backtest strategy.

    Raises:
        ValueError: if required columns are missing or direction values are invalid.
    """

    missing = [c for c in required_columns if c not in trades.columns]
    if missing:
        raise ValueError(f"Trades DataFrame missing required columns: {missing}")

    if not trades.empty:
        invalid_dir = set(trades["direction"].dropna().unique()) - {"long", "short"}
        if invalid_dir:
            raise ValueError(f"Trades DataFrame has invalid direction values: {sorted(invalid_dir)}")


class BaseBacktestStrategy(ABC):
    """
    Trade-generation contract for backtesting.

    Implementations must:
    - Take historical data (usually 1m) and return a DataFrame of trades.
    - Use `validate_trades_df()` to ensure schema compatibility.
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Stable identifier used in outputs and portfolio aggregation."""

    @abstractmethod
    def generate_trades(self, minute_df: pd.DataFrame, *, context: BacktestContext, params: Mapping[str, Any]) -> pd.DataFrame:
        """
        Generate trades for a single symbol.

        Args:
            minute_df: 1-minute OHLCV DataFrame (UTC timestamps) for the symbol.
            context: backtest execution context (fees, paths, etc.).
            params: strategy-specific parameters from config.

        Returns:
            DataFrame with REQUIRED_TRADE_COLUMNS.
        """
