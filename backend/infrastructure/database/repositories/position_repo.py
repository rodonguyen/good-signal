"""
Repository for Position entity operations.

Provides specialized query methods for position management
including open position tracking, symbol filtering, and exposure calculations.
"""

from datetime import datetime
from typing import Optional, Type

from sqlalchemy import select, func, desc

from backend.core.exceptions import DatabaseError
from backend.infrastructure.database.models import Position

from .base import BaseRepository


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


class PositionRepository(BaseRepository[Position]):
    """
    Repository for Position entity operations.

    Extends BaseRepository with position-specific query methods
    for tracking open positions, calculating exposure, and managing
    position lifecycle.

    Example:
        >>> repo = PositionRepository(session)
        >>> open_positions = await repo.get_open_positions()
        >>> exposure = await repo.get_total_exposure()
    """

    @property
    def _model(self) -> Type[Position]:
        return Position

    async def get_open_positions(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Position]:
        """
        Get all open positions.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[Position]: Open positions ordered by entry time desc.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(Position)
                .where(Position.status == "open")
                .order_by(desc(Position.entry_time))
                .offset(skip)
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get open positions: {e}",
                error_code="POSITION_OPEN_QUERY_FAILED",
                details={"error": str(e)},
            )

    async def get_by_symbol(
        self,
        symbol: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Position]:
        """
        Get positions for a specific symbol.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT").
            status: Optional status filter ("open" or "closed").
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[Position]: Positions for the symbol ordered by entry time desc.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(Position).where(Position.symbol == symbol)

            if status is not None:
                stmt = stmt.where(Position.status == status)

            stmt = (
                stmt.order_by(desc(Position.entry_time))
                .offset(skip)
                .limit(limit)
            )

            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get positions by symbol: {e}",
                error_code="POSITION_SYMBOL_QUERY_FAILED",
                details={"symbol": symbol, "status": status, "error": str(e)},
            )

    async def get_open_by_symbol(self, symbol: str) -> Optional[Position]:
        """
        Get the open position for a specific symbol.

        Assumes at most one open position per symbol.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT").

        Returns:
            Optional[Position]: Open position for the symbol if exists.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(Position)
                .where(
                    Position.symbol == symbol,
                    Position.status == "open",
                )
                .limit(1)
            )
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get open position by symbol: {e}",
                error_code="POSITION_OPEN_SYMBOL_QUERY_FAILED",
                details={"symbol": symbol, "error": str(e)},
            )

    async def get_by_config(
        self,
        config_id: str,
        status: Optional[str] = None,
    ) -> list[Position]:
        """
        Get positions for a specific live config.

        Args:
            config_id: LiveConfig ID.
            status: Optional status filter ("open" or "closed").

        Returns:
            list[Position]: Positions for the config.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(Position).where(Position.config_id == config_id)

            if status is not None:
                stmt = stmt.where(Position.status == status)

            stmt = stmt.order_by(desc(Position.entry_time))

            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get positions by config: {e}",
                error_code="POSITION_CONFIG_QUERY_FAILED",
                details={"config_id": config_id, "status": status, "error": str(e)},
            )

    async def count_open(self) -> int:
        """
        Count total open positions.

        Returns:
            int: Number of open positions.

        Raises:
            DatabaseError: If count query fails.
        """
        try:
            stmt = (
                select(func.count())
                .select_from(Position)
                .where(Position.status == "open")
            )
            result = await self._session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to count open positions: {e}",
                error_code="POSITION_COUNT_FAILED",
                details={"error": str(e)},
            )

    async def count_by_symbol(self, symbol: str, status: Optional[str] = None) -> int:
        """
        Count positions for a specific symbol.

        Args:
            symbol: Trading symbol.
            status: Optional status filter.

        Returns:
            int: Number of positions.

        Raises:
            DatabaseError: If count query fails.
        """
        try:
            stmt = (
                select(func.count())
                .select_from(Position)
                .where(Position.symbol == symbol)
            )

            if status is not None:
                stmt = stmt.where(Position.status == status)

            result = await self._session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to count positions by symbol: {e}",
                error_code="POSITION_COUNT_SYMBOL_FAILED",
                details={"symbol": symbol, "error": str(e)},
            )

    async def get_total_exposure(self) -> float:
        """
        Calculate total notional exposure across all open positions.

        Returns:
            float: Sum of notional_value for all open positions.

        Raises:
            DatabaseError: If calculation fails.
        """
        try:
            stmt = (
                select(func.coalesce(func.sum(Position.notional_value), 0.0))
                .select_from(Position)
                .where(Position.status == "open")
            )
            result = await self._session.execute(stmt)
            return float(result.scalar() or 0.0)
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to calculate total exposure: {e}",
                error_code="POSITION_EXPOSURE_FAILED",
                details={"error": str(e)},
            )

    async def get_total_unrealized_pnl(self) -> float:
        """
        Calculate total unrealized P&L across all open positions.

        Returns:
            float: Sum of unrealized_pnl for all open positions.

        Raises:
            DatabaseError: If calculation fails.
        """
        try:
            stmt = (
                select(func.coalesce(func.sum(Position.unrealized_pnl), 0.0))
                .select_from(Position)
                .where(Position.status == "open")
            )
            result = await self._session.execute(stmt)
            return float(result.scalar() or 0.0)
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to calculate total unrealized PnL: {e}",
                error_code="POSITION_UNREALIZED_PNL_FAILED",
                details={"error": str(e)},
            )

    async def get_exposure_by_symbol(self) -> dict[str, float]:
        """
        Calculate exposure per symbol for all open positions.

        Returns:
            dict[str, float]: Mapping of symbol to notional exposure.

        Raises:
            DatabaseError: If calculation fails.
        """
        try:
            stmt = (
                select(
                    Position.symbol,
                    func.sum(Position.notional_value).label("exposure"),
                )
                .where(Position.status == "open")
                .group_by(Position.symbol)
            )
            result = await self._session.execute(stmt)
            rows = result.all()
            return {row.symbol: float(row.exposure) for row in rows}
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to calculate exposure by symbol: {e}",
                error_code="POSITION_EXPOSURE_BY_SYMBOL_FAILED",
                details={"error": str(e)},
            )

    async def close_position(
        self,
        id: str,
        exit_price: float,
        exit_reason: str,
        realized_pnl: float,
        fees: float = 0.0,
        exit_order_id: Optional[str] = None,
    ) -> Position:
        """
        Close an open position.

        Args:
            id: Position ID.
            exit_price: Price at which position was closed.
            exit_reason: Reason for closing (e.g., "take_profit", "stop_loss").
            realized_pnl: Realized profit/loss.
            fees: Exit fees paid.
            exit_order_id: Optional order ID for the exit.

        Returns:
            Position: Updated closed position.

        Raises:
            NotFoundError: If position is not found.
            DatabaseError: If update fails.
        """
        position = await self.get_by_id_or_raise(id)

        position.status = "closed"
        position.exit_time = _utc_now()
        position.exit_price = exit_price
        position.exit_reason = exit_reason
        position.realized_pnl = realized_pnl
        position.unrealized_pnl = 0.0
        position.fees_paid += fees
        position.updated_at = _utc_now()

        if exit_order_id:
            position.exit_order_id = exit_order_id

        return await self.update(position)

    async def update_unrealized_pnl(
        self,
        id: str,
        unrealized_pnl: float,
    ) -> None:
        """
        Update unrealized P&L for a position.

        Args:
            id: Position ID.
            unrealized_pnl: New unrealized P&L value.

        Raises:
            NotFoundError: If position is not found.
            DatabaseError: If update fails.
        """
        from sqlalchemy import update

        try:
            stmt = (
                update(Position)
                .where(Position.id == id)
                .values(
                    unrealized_pnl=unrealized_pnl,
                    updated_at=_utc_now(),
                )
                .returning(Position.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                from backend.core.exceptions import NotFoundError
                raise NotFoundError(
                    message=f"Position not found: {id}",
                    error_code="POSITION_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except Exception as e:
            if "NotFoundError" in type(e).__name__:
                raise
            raise DatabaseError(
                message=f"Failed to update unrealized PnL: {e}",
                error_code="POSITION_UPDATE_PNL_FAILED",
                details={"id": id, "error": str(e)},
            )

    async def get_closed_positions(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        symbol: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Position]:
        """
        Get closed positions with optional filters.

        Args:
            start_date: Optional start date filter (ISO format).
            end_date: Optional end date filter (ISO format).
            symbol: Optional symbol filter.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[Position]: Closed positions matching filters.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(Position).where(Position.status == "closed")

            if start_date:
                stmt = stmt.where(Position.exit_time >= start_date)
            if end_date:
                stmt = stmt.where(Position.exit_time <= end_date)
            if symbol:
                stmt = stmt.where(Position.symbol == symbol)

            stmt = (
                stmt.order_by(desc(Position.exit_time))
                .offset(skip)
                .limit(limit)
            )

            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get closed positions: {e}",
                error_code="POSITION_CLOSED_QUERY_FAILED",
                details={"error": str(e)},
            )
