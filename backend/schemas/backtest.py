"""
Pydantic schemas for backtest request/response validation.

Provides comprehensive type-safe schemas for:
- Backtest configuration and execution requests
- Strategy and filter configuration
- Backtest results and summaries
- Trade details with pagination support
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from backend.schemas import BaseSchema


class StrategyConfig(BaseSchema):
    """
    Strategy configuration for backtest execution.

    Defines the strategy type, signal timeframe, and strategy-specific
    parameters for trade generation.
    """

    type: str = Field(
        description="Strategy type identifier (e.g., 'supertrend', 'atr_breakout', 'bb_trendline_rr4')",
        examples=["supertrend", "atr_breakout", "bb_trendline_rr4"],
    )
    enabled: bool = Field(
        default=True,
        description="Whether this strategy is enabled for execution",
    )
    signal_timeframe: str = Field(
        ...,
        description="Timeframe for signal generation (e.g., '1h', '4h', '1d'). Required.",
        examples=["1h", "4h", "15m", "1d"],
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy-specific parameters (e.g., ATR period, multiplier)",
    )

    @field_validator("type")
    @classmethod
    def validate_strategy_type(cls, v: str) -> str:
        """Validate strategy type is non-empty."""
        if not v or not v.strip():
            raise ValueError("Strategy type cannot be empty")
        return v.strip()

    @field_validator("signal_timeframe")
    @classmethod
    def validate_signal_timeframe(cls, v: str) -> str:
        """Validate signal timeframe format."""
        if not v or not v.strip():
            raise ValueError("Signal timeframe cannot be empty")
        # Basic validation - should match patterns like 1m, 5m, 15m, 1h, 4h, 1d
        v = v.strip().lower()
        if not any(v.endswith(suffix) for suffix in ['m', 'h', 'd', 'w']):
            raise ValueError("Signal timeframe must end with m, h, d, or w (e.g., '1h', '4h', '15m')")
        return v


class FilterConfig(BaseSchema):
    """
    Filter configuration for pre-entry trade filtering.

    Filters are applied to reduce trading activity on unfavorable
    market conditions (e.g., low volatility periods).
    """

    type: str = Field(
        description="Filter type identifier (e.g., 'supertrend', 'low_volatility_pct')",
        examples=["supertrend", "low_volatility_pct"],
    )
    enabled: bool = Field(
        default=True,
        description="Whether this filter is enabled",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Filter-specific parameters",
    )

    @field_validator("type")
    @classmethod
    def validate_filter_type(cls, v: str) -> str:
        """Validate filter type is non-empty."""
        if not v or not v.strip():
            raise ValueError("Filter type cannot be empty")
        return v.strip()


class BacktestRequest(BaseSchema):
    """
    Request schema for creating a new backtest.

    Specifies the complete configuration for backtest execution including
    symbols, strategies, filters, risk management, and date range.
    """

    name: Optional[str] = Field(
        default=None,
        description="Optional descriptive name for this backtest",
        max_length=255,
    )
    symbols: list[str] = Field(
        min_length=1,
        description="List of trading symbols to backtest (e.g., ['ETHUSDT', 'BTCUSDT'])",
        examples=[["ETHUSDT", "BTCUSDT"]],
    )
    strategies: list[StrategyConfig] = Field(
        min_length=1,
        description="List of strategies to execute",
    )
    filters: Optional[list[FilterConfig]] = Field(
        default=None,
        description="Optional list of pre-entry filters to apply",
    )
    fee_rate: float = Field(
        ...,
        ge=0.0,
        le=0.1,
        description="Total round-trip fee rate (e.g., 0.0015 = 0.15%). Required.",
        examples=[0.0015, 0.001, 0.002],
    )
    initial_equity: float = Field(
        ...,
        gt=0,
        description="Initial equity for portfolio simulation. Required.",
        examples=[10000.0, 50000.0, 100000.0],
    )
    risk_per_trade: float = Field(
        ...,
        ge=0.001,
        le=1.0,
        description="Risk percentage per trade for position sizing (e.g., 0.02 = 2%). Required.",
        examples=[0.01, 0.02, 0.05],
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Backtest start date in ISO format (YYYY-MM-DD). If not provided, uses available data start.",
        examples=["2024-01-01", "2023-06-15"],
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Backtest end date in ISO format (YYYY-MM-DD). If not provided, uses available data end.",
        examples=["2024-12-31", "2024-06-30"],
    )

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: list[str]) -> list[str]:
        """Validate symbols are non-empty and properly formatted."""
        if not v:
            raise ValueError("At least one symbol is required")
        validated = []
        for symbol in v:
            if not symbol or not symbol.strip():
                raise ValueError("Symbol cannot be empty")
            validated.append(symbol.strip().upper())
        return validated

    @field_validator("strategies")
    @classmethod
    def validate_strategies(cls, v: list[StrategyConfig]) -> list[StrategyConfig]:
        """Validate at least one enabled strategy exists."""
        if not v:
            raise ValueError("At least one strategy is required")
        enabled = [s for s in v if s.enabled]
        if not enabled:
            raise ValueError("At least one strategy must be enabled")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format is ISO-compatible."""
        if v is None:
            return v
        try:
            # Validate it's a proper date format
            datetime.fromisoformat(v.strip())
            return v.strip()
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")


class BacktestSummary(BaseSchema):
    """
    Summary schema for backtest list responses.

    Provides lightweight backtest information for list views
    without including full results or configuration.
    """

    id: str = Field(description="Unique backtest identifier")
    name: Optional[str] = Field(description="Backtest name if provided")
    status: str = Field(
        description="Current execution status",
        examples=["pending", "running", "completed", "failed", "cancelled"],
    )
    progress: float = Field(
        ge=0.0,
        le=1.0,
        description="Execution progress (0.0 to 1.0)",
    )
    symbols: list[str] = Field(description="List of symbols being backtested")
    created_at: str = Field(description="Creation timestamp in ISO format")
    completed_at: Optional[str] = Field(
        default=None,
        description="Completion timestamp in ISO format if finished",
    )

    # Summary metrics (only available when completed)
    total_return: Optional[float] = Field(
        default=None,
        description="Total return percentage if completed",
    )
    total_trades: Optional[int] = Field(
        default=None,
        description="Total number of trades if completed",
    )


class BacktestMetrics(BaseSchema):
    """
    Performance metrics for a completed backtest.
    """

    total_return: float = Field(description="Total return in currency")
    total_return_pct: float = Field(description="Total return percentage")
    sharpe_ratio: Optional[float] = Field(default=None, description="Sharpe ratio")
    sortino_ratio: Optional[float] = Field(default=None, description="Sortino ratio")
    max_drawdown: float = Field(description="Maximum drawdown percentage")
    win_rate: float = Field(ge=0.0, le=1.0, description="Win rate (0.0 to 1.0)")
    profit_factor: Optional[float] = Field(default=None, description="Profit factor")
    total_trades: int = Field(ge=0, description="Total number of trades")
    winning_trades: int = Field(ge=0, description="Number of winning trades")
    losing_trades: int = Field(ge=0, description="Number of losing trades")
    avg_win: Optional[float] = Field(default=None, description="Average winning trade")
    avg_loss: Optional[float] = Field(default=None, description="Average losing trade")
    largest_win: Optional[float] = Field(default=None, description="Largest winning trade")
    largest_loss: Optional[float] = Field(default=None, description="Largest losing trade")


class BacktestResult(BaseSchema):
    """
    Detailed backtest result schema.

    Provides complete backtest information including configuration,
    performance metrics, and execution metadata.
    """

    id: str = Field(description="Unique backtest identifier")
    name: Optional[str] = Field(description="Backtest name if provided")
    status: str = Field(
        description="Current execution status",
        examples=["pending", "running", "completed", "failed", "cancelled"],
    )
    progress: float = Field(
        ge=0.0,
        le=1.0,
        description="Execution progress (0.0 to 1.0)",
    )

    # Configuration
    config: dict[str, Any] = Field(description="Full backtest configuration")
    symbols: list[str] = Field(description="List of symbols being backtested")
    strategies: list[dict[str, Any]] = Field(description="Strategy configurations")
    filters: Optional[list[dict[str, Any]]] = Field(default=None, description="Filter configurations")
    timeframe: Optional[str] = Field(default=None, description="Signal timeframe")
    fee_rate: Optional[float] = Field(default=None, description="Fee rate used")

    # Portfolio info
    initial_equity: Optional[float] = Field(default=None, description="Initial equity")
    final_equity: Optional[float] = Field(default=None, description="Final equity")

    # Performance metrics (nested object, available after completion)
    metrics: Optional[BacktestMetrics] = Field(
        default=None,
        description="Performance metrics (available when completed)",
    )

    # Timestamps
    created_at: str = Field(description="Creation timestamp in ISO format")
    completed_at: Optional[str] = Field(
        default=None,
        description="Completion timestamp in ISO format",
    )

    # Error handling
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if backtest failed",
    )


class BacktestTradeResponse(BaseSchema):
    """
    Individual trade result from a backtest.

    Represents a single trade execution with entry/exit details,
    P&L calculation, and strategy metadata.
    """

    id: int = Field(description="Unique trade identifier")
    symbol: str = Field(description="Trading symbol")
    strategy_id: str = Field(description="Strategy identifier that generated this trade")
    direction: str = Field(
        description="Trade direction",
        examples=["long", "short"],
    )

    # Entry details
    entry_time: str = Field(description="Entry timestamp in ISO format")
    entry_price: float = Field(gt=0, description="Entry price")

    # Exit details
    exit_time: str = Field(description="Exit timestamp in ISO format")
    exit_price: float = Field(gt=0, description="Exit price")
    exit_reason: Optional[str] = Field(
        default=None,
        description="Reason for exit (e.g., 'stop_loss', 'take_profit', 'end_of_day')",
    )

    # Risk management levels
    stop_level: Optional[float] = Field(
        default=None,
        description="Stop loss price level",
    )
    tp_level: Optional[float] = Field(
        default=None,
        description="Take profit price level",
    )

    # P&L details
    raw_pnl: float = Field(description="Raw P&L before fees")
    fees: float = Field(ge=0, description="Total fees paid")
    net_pnl: float = Field(description="Net P&L after fees")

    # Portfolio-level details
    portfolio_pnl: Optional[float] = Field(
        default=None,
        description="P&L in portfolio equity terms (after position sizing)",
    )
    position_size: Optional[float] = Field(
        default=None,
        description="Position size used for this trade",
    )

    # Equity tracking
    equity: Optional[float] = Field(
        default=None,
        description="Portfolio equity after this trade",
    )
    drawdown: Optional[float] = Field(
        default=None,
        description="Drawdown percentage at this trade",
    )


class BacktestCancelResponse(BaseSchema):
    """Response schema for backtest cancellation."""

    success: bool = Field(description="Whether cancellation was successful")
    message: str = Field(description="Cancellation result message")
    backtest_id: str = Field(description="ID of the cancelled backtest")
