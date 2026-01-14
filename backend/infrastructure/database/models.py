"""SQLAlchemy ORM models for the good-signal trading application."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Float,
    Boolean,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())


def utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


class Backtest(Base):
    """Backtest execution record."""

    __tablename__ = "backtests"

    # Primary key
    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=generate_uuid
    )

    # Basic info
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
        index=True
    )  # pending, running, completed, failed, cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)

    # Configuration
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    symbols: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    strategies: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    filters: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fee_rate: Mapped[float] = mapped_column(Float, nullable=False)
    initial_equity: Mapped[float] = mapped_column(Float, nullable=False)
    risk_per_trade: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Date range
    start_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Results
    total_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    results_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=utc_now,
        index=True
    )
    started_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    trades: Mapped[list["BacktestTrade"]] = relationship(
        "BacktestTrade",
        back_populates="backtest",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_backtest_status_created", "status", "created_at"),
    )


class BacktestTrade(Base):
    """Individual trade from a backtest."""

    __tablename__ = "backtest_trades"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    backtest_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("backtests.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Trade info
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # long, short

    # Entry/exit
    entry_time: Mapped[str] = mapped_column(String, nullable=False)
    exit_time: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # P&L
    raw_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, nullable=False)
    net_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    portfolio_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Position sizing
    position_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Equity tracking
    equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    drawdown: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Metadata
    exit_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)

    # Relationships
    backtest: Mapped["Backtest"] = relationship("Backtest", back_populates="trades")

    __table_args__ = (
        Index("idx_backtest_trade_backtest_symbol", "backtest_id", "symbol"),
        Index("idx_backtest_trade_entry_time", "entry_time"),
    )


class LiveConfig(Base):
    """Live trading configuration."""

    __tablename__ = "live_configs"

    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)

    # Basic info
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    # Trading parameters
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy_type: Mapped[str] = mapped_column(String, nullable=False)
    strategy_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filter_configs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Risk management
    initial_equity: Mapped[float] = mapped_column(Float, nullable=False)
    risk_per_trade: Mapped[float] = mapped_column(Float, nullable=False)
    max_position_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_daily_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_open_positions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Trading settings
    timeframe: Mapped[str] = mapped_column(String, nullable=False)
    fee_rate: Mapped[float] = mapped_column(Float, nullable=False)

    # Timestamps
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)

    # Relationships
    positions: Mapped[list["Position"]] = relationship(
        "Position",
        back_populates="config",
        cascade="all, delete-orphan"
    )
    live_trades: Mapped[list["LiveTrade"]] = relationship(
        "LiveTrade",
        back_populates="config",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_live_config_active_symbol", "is_active", "symbol"),
    )


class Position(Base):
    """Open or closed trading position."""

    __tablename__ = "positions"

    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)

    # Foreign key
    config_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("live_configs.id"),
        nullable=True,
        index=True
    )

    # Position info
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # long, short
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)  # open, closed

    # Entry
    entry_time: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_order_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    notional_value: Mapped[float] = mapped_column(Float, nullable=False)

    # Risk management
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Exit
    exit_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_order_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # P&L
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    fees_paid: Mapped[float] = mapped_column(Float, default=0.0)

    # Metadata
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)

    # Relationships
    config: Mapped[Optional["LiveConfig"]] = relationship("LiveConfig", back_populates="positions")
    live_trades: Mapped[list["LiveTrade"]] = relationship(
        "LiveTrade",
        back_populates="position",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_position_status_symbol", "status", "symbol"),
        Index("idx_position_entry_time", "entry_time"),
    )


class LiveTrade(Base):
    """Individual live trade execution."""

    __tablename__ = "live_trades"

    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)

    # Foreign keys
    position_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("positions.id"),
        nullable=True,
        index=True
    )
    config_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("live_configs.id"),
        nullable=True,
        index=True
    )

    # Trade info
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # long, short
    trade_type: Mapped[str] = mapped_column(String, nullable=False)  # entry, exit, stop_loss, take_profit

    # Order details
    order_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    order_type: Mapped[str] = mapped_column(String, nullable=False)  # market, limit, stop, stop_limit
    order_status: Mapped[str] = mapped_column(String, nullable=False, index=True)  # pending, filled, partial, cancelled, rejected

    # Pricing
    requested_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    executed_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    filled_quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # P&L
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timing
    requested_at: Mapped[str] = mapped_column(String, nullable=False)
    executed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)

    # Relationships
    position: Mapped[Optional["Position"]] = relationship("Position", back_populates="live_trades")
    config: Mapped[Optional["LiveConfig"]] = relationship("LiveConfig", back_populates="live_trades")

    __table_args__ = (
        Index("idx_live_trade_order_status", "order_status", "created_at"),
        Index("idx_live_trade_symbol_time", "symbol", "requested_at"),
    )


class RiskState(Base):
    """Global risk management state (singleton table)."""

    __tablename__ = "risk_state"

    # Primary key - constrained to single row
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        autoincrement=False
    )

    # Kill switch
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kill_switch_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kill_switch_activated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Daily tracking
    daily_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    daily_trades: Mapped[int] = mapped_column(Integer, default=0)
    daily_reset_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Exposure tracking
    total_open_positions: Mapped[int] = mapped_column(Integer, default=0)
    total_exposure: Mapped[float] = mapped_column(Float, default=0.0)

    # Timestamp
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_check"),
    )


class TaskQueue(Base):
    """Background task queue."""

    __tablename__ = "task_queue"

    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)

    # Task info
    task_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
        index=True
    )  # pending, running, completed, failed
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # Payload and results
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Worker tracking
    worker_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Retry logic
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=utc_now,
        index=True
    )
    started_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    scheduled_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_task_status_priority_scheduled", "status", "priority", "scheduled_at"),
        Index("idx_task_type_status", "task_type", "status"),
    )


class SavedConfig(Base):
    """Saved configuration templates."""

    __tablename__ = "saved_configs"

    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)

    # Config info
    name: Mapped[str] = mapped_column(String, nullable=False)
    config_type: Mapped[str] = mapped_column(String, nullable=False, index=True)  # backtest, live, strategy
    config_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=utc_now,
        index=True
    )
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_saved_config_type_created", "config_type", "created_at"),
    )
