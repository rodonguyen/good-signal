"""
Repositories for trade entities.

Provides repository classes for BacktestTrade and LiveTrade entities
with specialized query methods for trade analysis and reporting.
"""

from datetime import datetime
from typing import Optional, Type

from sqlalchemy import select, func, desc, and_

from backend.core.exceptions import DatabaseError
from backend.infrastructure.database.models import BacktestTrade, LiveTrade

from .base import BaseRepository


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()


class BacktestTradeRepository(BaseRepository[BacktestTrade]):
    """
    Repository for BacktestTrade entity operations.

    Provides methods for managing and analyzing backtest trades
    including filtering by backtest, symbol, and performance metrics.

    Example:
        >>> repo = BacktestTradeRepository(session)
        >>> trades = await repo.get_by_backtest(backtest_id)
        >>> stats = await repo.get_statistics(backtest_id)
    """

    @property
    def _model(self) -> Type[BacktestTrade]:
        return BacktestTrade

    @property
    def _id_column_name(self) -> str:
        """BacktestTrade uses integer id."""
        return "id"

    async def get_by_backtest(
        self,
        backtest_id: str,
        skip: int = 0,
        limit: int = 1000,
    ) -> list[BacktestTrade]:
        """
        Get all trades for a specific backtest.

        Args:
            backtest_id: Backtest ID.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[BacktestTrade]: Trades for the backtest ordered by entry time.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(BacktestTrade)
                .where(BacktestTrade.backtest_id == backtest_id)
                .order_by(BacktestTrade.entry_time)
                .offset(skip)
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get backtest trades: {e}",
                error_code="BACKTEST_TRADE_QUERY_FAILED",
                details={"backtest_id": backtest_id, "error": str(e)},
            )

    async def get_by_backtest_and_symbol(
        self,
        backtest_id: str,
        symbol: str,
    ) -> list[BacktestTrade]:
        """
        Get trades for a specific backtest and symbol.

        Args:
            backtest_id: Backtest ID.
            symbol: Trading symbol.

        Returns:
            list[BacktestTrade]: Trades matching filters.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(BacktestTrade)
                .where(
                    and_(
                        BacktestTrade.backtest_id == backtest_id,
                        BacktestTrade.symbol == symbol,
                    )
                )
                .order_by(BacktestTrade.entry_time)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get backtest trades by symbol: {e}",
                error_code="BACKTEST_TRADE_SYMBOL_QUERY_FAILED",
                details={"backtest_id": backtest_id, "symbol": symbol, "error": str(e)},
            )

    async def count_by_backtest(self, backtest_id: str) -> int:
        """
        Count trades for a specific backtest.

        Args:
            backtest_id: Backtest ID.

        Returns:
            int: Number of trades.

        Raises:
            DatabaseError: If count query fails.
        """
        try:
            stmt = (
                select(func.count())
                .select_from(BacktestTrade)
                .where(BacktestTrade.backtest_id == backtest_id)
            )
            result = await self._session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to count backtest trades: {e}",
                error_code="BACKTEST_TRADE_COUNT_FAILED",
                details={"backtest_id": backtest_id, "error": str(e)},
            )

    async def get_statistics(self, backtest_id: str) -> dict:
        """
        Calculate trade statistics for a backtest.

        Args:
            backtest_id: Backtest ID.

        Returns:
            dict: Statistics including total_trades, winners, losers, total_pnl, etc.

        Raises:
            DatabaseError: If calculation fails.
        """
        try:
            # Get all trades
            trades = await self.get_by_backtest(backtest_id, limit=100000)

            if not trades:
                return {
                    "total_trades": 0,
                    "winners": 0,
                    "losers": 0,
                    "win_rate": 0.0,
                    "total_pnl": 0.0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "profit_factor": 0.0,
                    "avg_win": 0.0,
                    "avg_loss": 0.0,
                    "largest_win": 0.0,
                    "largest_loss": 0.0,
                }

            winners = [t for t in trades if t.net_pnl > 0]
            losers = [t for t in trades if t.net_pnl < 0]

            gross_profit = sum(t.net_pnl for t in winners)
            gross_loss = abs(sum(t.net_pnl for t in losers))
            total_pnl = sum(t.net_pnl for t in trades)

            return {
                "total_trades": len(trades),
                "winners": len(winners),
                "losers": len(losers),
                "win_rate": len(winners) / len(trades) if trades else 0.0,
                "total_pnl": total_pnl,
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
                "avg_win": gross_profit / len(winners) if winners else 0.0,
                "avg_loss": gross_loss / len(losers) if losers else 0.0,
                "largest_win": max((t.net_pnl for t in winners), default=0.0),
                "largest_loss": abs(min((t.net_pnl for t in losers), default=0.0)),
            }
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to calculate trade statistics: {e}",
                error_code="BACKTEST_TRADE_STATS_FAILED",
                details={"backtest_id": backtest_id, "error": str(e)},
            )

    async def delete_by_backtest(self, backtest_id: str) -> int:
        """
        Delete all trades for a backtest.

        Args:
            backtest_id: Backtest ID.

        Returns:
            int: Number of trades deleted.

        Raises:
            DatabaseError: If deletion fails.
        """
        try:
            from sqlalchemy import delete

            stmt = delete(BacktestTrade).where(
                BacktestTrade.backtest_id == backtest_id
            )
            result = await self._session.execute(stmt)
            await self._session.flush()
            return result.rowcount or 0  # type: ignore
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to delete backtest trades: {e}",
                error_code="BACKTEST_TRADE_DELETE_FAILED",
                details={"backtest_id": backtest_id, "error": str(e)},
            )


class LiveTradeRepository(BaseRepository[LiveTrade]):
    """
    Repository for LiveTrade entity operations.

    Provides methods for managing and analyzing live trades
    including order tracking, position linking, and execution reporting.

    Example:
        >>> repo = LiveTradeRepository(session)
        >>> trades = await repo.get_by_position(position_id)
        >>> pending = await repo.get_pending_orders()
    """

    @property
    def _model(self) -> Type[LiveTrade]:
        return LiveTrade

    async def get_by_position(
        self,
        position_id: str,
    ) -> list[LiveTrade]:
        """
        Get all trades for a specific position.

        Args:
            position_id: Position ID.

        Returns:
            list[LiveTrade]: Trades for the position ordered by requested time.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveTrade)
                .where(LiveTrade.position_id == position_id)
                .order_by(LiveTrade.requested_at)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get trades by position: {e}",
                error_code="LIVE_TRADE_POSITION_QUERY_FAILED",
                details={"position_id": position_id, "error": str(e)},
            )

    async def get_by_config(
        self,
        config_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[LiveTrade]:
        """
        Get trades for a specific live config.

        Args:
            config_id: LiveConfig ID.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[LiveTrade]: Trades for the config ordered by requested time desc.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveTrade)
                .where(LiveTrade.config_id == config_id)
                .order_by(desc(LiveTrade.requested_at))
                .offset(skip)
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get trades by config: {e}",
                error_code="LIVE_TRADE_CONFIG_QUERY_FAILED",
                details={"config_id": config_id, "error": str(e)},
            )

    async def get_by_symbol(
        self,
        symbol: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[LiveTrade]:
        """
        Get trades for a specific symbol.

        Args:
            symbol: Trading symbol.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[LiveTrade]: Trades for the symbol ordered by requested time desc.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveTrade)
                .where(LiveTrade.symbol == symbol)
                .order_by(desc(LiveTrade.requested_at))
                .offset(skip)
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get trades by symbol: {e}",
                error_code="LIVE_TRADE_SYMBOL_QUERY_FAILED",
                details={"symbol": symbol, "error": str(e)},
            )

    async def get_by_order_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[LiveTrade]:
        """
        Get trades by order status.

        Args:
            status: Order status (pending, filled, partial, cancelled, rejected).
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[LiveTrade]: Trades with the status ordered by requested time desc.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveTrade)
                .where(LiveTrade.order_status == status)
                .order_by(desc(LiveTrade.requested_at))
                .offset(skip)
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get trades by order status: {e}",
                error_code="LIVE_TRADE_STATUS_QUERY_FAILED",
                details={"status": status, "error": str(e)},
            )

    async def get_pending_orders(self) -> list[LiveTrade]:
        """
        Get all pending order trades.

        Returns:
            list[LiveTrade]: Trades with pending order status.

        Raises:
            DatabaseError: If query execution fails.
        """
        return await self.get_by_order_status("pending", limit=1000)

    async def get_by_order_id(self, order_id: str) -> Optional[LiveTrade]:
        """
        Get trade by exchange order ID.

        Args:
            order_id: Exchange order ID.

        Returns:
            Optional[LiveTrade]: Trade if found.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveTrade)
                .where(LiveTrade.order_id == order_id)
                .limit(1)
            )
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get trade by order ID: {e}",
                error_code="LIVE_TRADE_ORDER_ID_QUERY_FAILED",
                details={"order_id": order_id, "error": str(e)},
            )

    async def get_recent(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
    ) -> list[LiveTrade]:
        """
        Get most recent live trades.

        Args:
            limit: Maximum number of records to return.
            symbol: Optional symbol filter.

        Returns:
            list[LiveTrade]: Most recent trades.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(LiveTrade)

            if symbol:
                stmt = stmt.where(LiveTrade.symbol == symbol)

            stmt = stmt.order_by(desc(LiveTrade.created_at)).limit(limit)

            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get recent live trades: {e}",
                error_code="LIVE_TRADE_RECENT_QUERY_FAILED",
                details={"error": str(e)},
            )

    async def update_order_status(
        self,
        id: str,
        order_status: str,
        executed_price: Optional[float] = None,
        filled_quantity: Optional[float] = None,
        fees: Optional[float] = None,
        executed_at: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update order execution status.

        Args:
            id: Trade ID.
            order_status: New order status.
            executed_price: Execution price if filled.
            filled_quantity: Filled quantity if partial/filled.
            fees: Fees paid.
            executed_at: Execution timestamp.
            error_message: Error message if rejected/failed.

        Raises:
            NotFoundError: If trade is not found.
            DatabaseError: If update fails.
        """
        from sqlalchemy import update
        from backend.core.exceptions import NotFoundError

        try:
            values: dict = {"order_status": order_status}

            if executed_price is not None:
                values["executed_price"] = executed_price
            if filled_quantity is not None:
                values["filled_quantity"] = filled_quantity
            if fees is not None:
                values["fees"] = fees
            if executed_at is not None:
                values["executed_at"] = executed_at
            if error_message is not None:
                values["error_message"] = error_message

            stmt = (
                update(LiveTrade)
                .where(LiveTrade.id == id)
                .values(**values)
                .returning(LiveTrade.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise NotFoundError(
                    message=f"Live trade not found: {id}",
                    error_code="LIVE_TRADE_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update order status: {e}",
                error_code="LIVE_TRADE_UPDATE_FAILED",
                details={"id": id, "error": str(e)},
            )

    async def get_daily_statistics(
        self,
        date: str,
        config_id: Optional[str] = None,
    ) -> dict:
        """
        Calculate daily trade statistics.

        Args:
            date: Date in YYYY-MM-DD format.
            config_id: Optional config filter.

        Returns:
            dict: Daily statistics including trades, filled, pnl, fees.

        Raises:
            DatabaseError: If calculation fails.
        """
        try:
            stmt = select(LiveTrade).where(
                LiveTrade.created_at.like(f"{date}%")
            )

            if config_id:
                stmt = stmt.where(LiveTrade.config_id == config_id)

            result = await self._session.execute(stmt)
            trades = list(result.scalars().all())

            filled_trades = [t for t in trades if t.order_status == "filled"]
            total_pnl = sum(t.realized_pnl or 0.0 for t in filled_trades)
            total_fees = sum(t.fees or 0.0 for t in trades)

            return {
                "date": date,
                "total_trades": len(trades),
                "filled_trades": len(filled_trades),
                "pending_trades": len([t for t in trades if t.order_status == "pending"]),
                "rejected_trades": len([t for t in trades if t.order_status == "rejected"]),
                "total_pnl": total_pnl,
                "total_fees": total_fees,
            }
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to calculate daily statistics: {e}",
                error_code="LIVE_TRADE_DAILY_STATS_FAILED",
                details={"date": date, "error": str(e)},
            )
