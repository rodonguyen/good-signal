"""
Position management service for live trading.

Handles position lifecycle, P&L calculations, and exchange synchronization.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import TradingError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.infrastructure.database.models import Position
from backend.infrastructure.database.repositories.position_repo import PositionRepository
from backend.infrastructure.exchange.bybit_client import BybitClient

logger = get_logger(__name__)


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


class PositionService:
    """
    Service for managing trading positions.

    Provides position lifecycle management, P&L tracking,
    and synchronization with exchange.

    Example:
        >>> service = PositionService(session, bybit_client)
        >>> position = await service.create_position(
        ...     config_id="abc",
        ...     symbol="BTCUSDT",
        ...     strategy_id="supertrend",
        ...     direction="long",
        ...     entry_price=50000.0,
        ...     quantity=0.1,
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        bybit_client: BybitClient,
    ) -> None:
        """
        Initialize position service.

        Args:
            session: Database session
            bybit_client: Bybit exchange client
        """
        self._session = session
        self._bybit = bybit_client
        self._repo = PositionRepository(session)

    async def create_position(
        self,
        config_id: str,
        symbol: str,
        strategy_id: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_order_id: Optional[str] = None,
    ) -> Position:
        """
        Create a new open position.

        Args:
            config_id: LiveConfig ID
            symbol: Trading symbol
            strategy_id: Strategy identifier
            direction: Position direction ('long' or 'short')
            entry_price: Entry price
            quantity: Position quantity
            stop_loss: Optional stop loss level
            take_profit: Optional take profit level
            entry_order_id: Optional entry order ID

        Returns:
            Created Position

        Raises:
            ValidationError: If parameters are invalid
        """
        # Validate direction
        if direction not in ["long", "short"]:
            raise ValidationError(
                message=f"Invalid direction: {direction}. Must be 'long' or 'short'.",
                error_code="INVALID_DIRECTION",
                details={"direction": direction},
            )

        # Validate quantities
        if quantity <= 0:
            raise ValidationError(
                message=f"Quantity must be positive: {quantity}",
                error_code="INVALID_QUANTITY",
                details={"quantity": quantity},
            )

        if entry_price <= 0:
            raise ValidationError(
                message=f"Entry price must be positive: {entry_price}",
                error_code="INVALID_PRICE",
                details={"entry_price": entry_price},
            )

        notional_value = entry_price * quantity

        logger.info(
            "Creating position",
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            notional_value=notional_value,
        )

        position = Position(
            config_id=config_id,
            symbol=symbol,
            strategy_id=strategy_id,
            direction=direction,
            status="open",
            entry_time=_utc_now(),
            entry_price=entry_price,
            entry_order_id=entry_order_id,
            quantity=quantity,
            notional_value=notional_value,
            stop_loss=stop_loss,
            take_profit=take_profit,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            fees_paid=0.0,
        )

        self._session.add(position)
        await self._session.flush()

        logger.info(
            "Position created",
            position_id=position.id,
            symbol=symbol,
            direction=direction,
        )

        return position

    async def update_position(
        self,
        position_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        unrealized_pnl: Optional[float] = None,
    ) -> Position:
        """
        Update position parameters.

        Args:
            position_id: Position ID
            stop_loss: Optional new stop loss level
            take_profit: Optional new take profit level
            unrealized_pnl: Optional unrealized P&L update

        Returns:
            Updated Position

        Raises:
            NotFoundError: If position not found
        """
        position = await self._repo.get_by_id_or_raise(position_id)

        logger.info(
            "Updating position",
            position_id=position_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
            unrealized_pnl=unrealized_pnl,
        )

        if stop_loss is not None:
            position.stop_loss = stop_loss

        if take_profit is not None:
            position.take_profit = take_profit

        if unrealized_pnl is not None:
            position.unrealized_pnl = unrealized_pnl

        position.updated_at = _utc_now()

        await self._session.flush()

        logger.debug(
            "Position updated",
            position_id=position_id,
        )

        return position

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: str,
        exit_order_id: Optional[str] = None,
        fees: float = 0.0,
    ) -> Position:
        """
        Close an open position.

        Args:
            position_id: Position ID
            exit_price: Exit price
            exit_reason: Reason for closure
            exit_order_id: Optional exit order ID
            fees: Exit fees

        Returns:
            Closed Position

        Raises:
            NotFoundError: If position not found
            TradingError: If position already closed
        """
        position = await self._repo.get_by_id_or_raise(position_id)

        if position.status != "open":
            raise TradingError(
                message=f"Cannot close position with status: {position.status}",
                error_code="INVALID_POSITION_STATUS",
                details={"position_id": position_id, "status": position.status},
            )

        logger.info(
            "Closing position",
            position_id=position_id,
            symbol=position.symbol,
            exit_price=exit_price,
            exit_reason=exit_reason,
        )

        # Calculate realized P&L
        if position.direction == "long":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        # Subtract fees
        total_fees = position.fees_paid + fees
        realized_pnl = pnl - total_fees

        # Close using repository method
        closed_position = await self._repo.close_position(
            id=position_id,
            exit_price=exit_price,
            exit_reason=exit_reason,
            realized_pnl=realized_pnl,
            fees=fees,
            exit_order_id=exit_order_id,
        )

        logger.info(
            "Position closed",
            position_id=position_id,
            realized_pnl=realized_pnl,
            exit_reason=exit_reason,
        )

        return closed_position

    async def get_open_positions(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Position]:
        """
        Get all open positions.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            list of open Positions
        """
        return await self._repo.get_open_positions(skip=skip, limit=limit)

    async def get_position_by_id(self, position_id: str) -> Position:
        """
        Get position by ID.

        Args:
            position_id: Position ID

        Returns:
            Position

        Raises:
            NotFoundError: If position not found
        """
        return await self._repo.get_by_id_or_raise(position_id)

    async def get_positions_by_symbol(
        self,
        symbol: str,
        status: Optional[str] = None,
    ) -> list[Position]:
        """
        Get positions for a symbol.

        Args:
            symbol: Trading symbol
            status: Optional status filter

        Returns:
            list of Positions
        """
        return await self._repo.get_by_symbol(symbol=symbol, status=status)

    async def update_unrealized_pnl(
        self,
        position_id: str,
        current_price: float,
    ) -> Position:
        """
        Update unrealized P&L for a position based on current price.

        Args:
            position_id: Position ID
            current_price: Current market price

        Returns:
            Updated Position

        Raises:
            NotFoundError: If position not found
        """
        position = await self._repo.get_by_id_or_raise(position_id)

        if position.status != "open":
            logger.debug(
                "Skipping unrealized PnL update for closed position",
                position_id=position_id,
            )
            return position

        # Calculate unrealized P&L
        if position.direction == "long":
            unrealized_pnl = (current_price - position.entry_price) * position.quantity
        else:
            unrealized_pnl = (position.entry_price - current_price) * position.quantity

        # Update in database
        await self._repo.update_unrealized_pnl(
            id=position_id,
            unrealized_pnl=unrealized_pnl,
        )

        # Refresh position
        await self._session.refresh(position)

        logger.debug(
            "Updated unrealized PnL",
            position_id=position_id,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
        )

        return position

    async def update_stop_loss(
        self,
        position_id: str,
        stop_loss: float,
    ) -> Position:
        """
        Update stop loss level for a position.

        Args:
            position_id: Position ID
            stop_loss: New stop loss level

        Returns:
            Updated Position

        Raises:
            NotFoundError: If position not found
            ValidationError: If stop loss invalid
        """
        position = await self._repo.get_by_id_or_raise(position_id)

        if position.status != "open":
            raise TradingError(
                message=f"Cannot update stop loss for closed position",
                error_code="INVALID_POSITION_STATUS",
                details={"position_id": position_id, "status": position.status},
            )

        # Validate stop loss direction
        if position.direction == "long" and stop_loss >= position.entry_price:
            raise ValidationError(
                message="Stop loss must be below entry price for long positions",
                error_code="INVALID_STOP_LOSS",
                details={
                    "stop_loss": stop_loss,
                    "entry_price": position.entry_price,
                    "direction": position.direction,
                },
            )
        elif position.direction == "short" and stop_loss <= position.entry_price:
            raise ValidationError(
                message="Stop loss must be above entry price for short positions",
                error_code="INVALID_STOP_LOSS",
                details={
                    "stop_loss": stop_loss,
                    "entry_price": position.entry_price,
                    "direction": position.direction,
                },
            )

        logger.info(
            "Updating stop loss",
            position_id=position_id,
            old_stop_loss=position.stop_loss,
            new_stop_loss=stop_loss,
        )

        position.stop_loss = stop_loss
        position.updated_at = _utc_now()
        await self._session.flush()

        return position

    async def update_take_profit(
        self,
        position_id: str,
        take_profit: float,
    ) -> Position:
        """
        Update take profit level for a position.

        Args:
            position_id: Position ID
            take_profit: New take profit level

        Returns:
            Updated Position

        Raises:
            NotFoundError: If position not found
            ValidationError: If take profit invalid
        """
        position = await self._repo.get_by_id_or_raise(position_id)

        if position.status != "open":
            raise TradingError(
                message=f"Cannot update take profit for closed position",
                error_code="INVALID_POSITION_STATUS",
                details={"position_id": position_id, "status": position.status},
            )

        # Validate take profit direction
        if position.direction == "long" and take_profit <= position.entry_price:
            raise ValidationError(
                message="Take profit must be above entry price for long positions",
                error_code="INVALID_TAKE_PROFIT",
                details={
                    "take_profit": take_profit,
                    "entry_price": position.entry_price,
                    "direction": position.direction,
                },
            )
        elif position.direction == "short" and take_profit >= position.entry_price:
            raise ValidationError(
                message="Take profit must be below entry price for short positions",
                error_code="INVALID_TAKE_PROFIT",
                details={
                    "take_profit": take_profit,
                    "entry_price": position.entry_price,
                    "direction": position.direction,
                },
            )

        logger.info(
            "Updating take profit",
            position_id=position_id,
            old_take_profit=position.take_profit,
            new_take_profit=take_profit,
        )

        position.take_profit = take_profit
        position.updated_at = _utc_now()
        await self._session.flush()

        return position

    async def sync_with_exchange(self) -> dict[str, int]:
        """
        Synchronize positions with exchange on startup.

        Compares database positions with exchange positions
        and reconciles any discrepancies.

        Returns:
            dict with sync statistics: matched, missing_in_db, missing_in_exchange

        Raises:
            TradingError: If synchronization fails
        """
        logger.info("Starting position synchronization with exchange")

        try:
            # Get positions from exchange
            exchange_positions = await self._bybit.get_positions()

            # Get open positions from database
            db_positions = await self._repo.get_open_positions(limit=1000)

            # Create lookup dict by symbol
            db_by_symbol = {pos.symbol: pos for pos in db_positions}
            exchange_by_symbol = {pos["symbol"]: pos for pos in exchange_positions}

            matched = 0
            missing_in_db = 0
            missing_in_exchange = 0

            # Check exchange positions against database
            for symbol, exchange_pos in exchange_by_symbol.items():
                if symbol in db_by_symbol:
                    matched += 1
                    # Update unrealized P&L
                    current_price = float(exchange_pos.get("markPrice", 0))
                    if current_price > 0:
                        await self.update_unrealized_pnl(
                            position_id=db_by_symbol[symbol].id,
                            current_price=current_price,
                        )
                else:
                    missing_in_db += 1
                    logger.warning(
                        "Position exists on exchange but not in database",
                        symbol=symbol,
                        exchange_position=exchange_pos,
                    )

            # Check database positions against exchange
            for symbol, db_pos in db_by_symbol.items():
                if symbol not in exchange_by_symbol:
                    missing_in_exchange += 1
                    logger.warning(
                        "Position exists in database but not on exchange - closing",
                        position_id=db_pos.id,
                        symbol=symbol,
                    )
                    # Close position in database as it doesn't exist on exchange
                    await self.close_position(
                        position_id=db_pos.id,
                        exit_price=db_pos.entry_price,  # Use entry price as fallback
                        exit_reason="sync_not_found_on_exchange",
                    )

            stats = {
                "matched": matched,
                "missing_in_db": missing_in_db,
                "missing_in_exchange": missing_in_exchange,
            }

            logger.info(
                "Position synchronization completed",
                stats=stats,
            )

            return stats

        except Exception as e:
            logger.error("Position synchronization failed", error=str(e))
            raise TradingError(
                message=f"Failed to sync positions with exchange: {e}",
                error_code="POSITION_SYNC_FAILED",
                details={"error": str(e)},
            )
