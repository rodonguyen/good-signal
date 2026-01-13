"""
Order management service for live trading.

Handles order placement, execution tracking, and integration
with positions and trade records.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import TradingError, NotFoundError
from backend.core.logging import get_logger
from backend.infrastructure.database.models import LiveTrade, Position
from backend.infrastructure.database.repositories.position_repo import PositionRepository
from backend.infrastructure.database.repositories.trade_repo import LiveTradeRepository
from backend.infrastructure.exchange.bybit_client import BybitClient

logger = get_logger(__name__)


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()


class OrderService:
    """
    Service for managing live trading orders.

    Coordinates order placement with exchange and database record keeping.
    Handles entry/exit orders and partial fills.

    Example:
        >>> service = OrderService(session, bybit_client)
        >>> order = await service.place_entry_order(
        ...     config_id="abc123",
        ...     symbol="BTCUSDT",
        ...     direction="long",
        ...     quantity=0.1,
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        bybit_client: BybitClient,
    ) -> None:
        """
        Initialize order service.

        Args:
            session: Database session
            bybit_client: Bybit exchange client
        """
        self._session = session
        self._bybit = bybit_client
        self._trade_repo = LiveTradeRepository(session)
        self._position_repo = PositionRepository(session)

    async def place_entry_order(
        self,
        config_id: str,
        symbol: str,
        direction: str,
        quantity: float,
        strategy_id: str,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> tuple[LiveTrade, Optional[str]]:
        """
        Place an entry order to open a new position.

        Creates database records and submits order to exchange.
        If order is immediately filled, creates position record.

        Args:
            config_id: LiveConfig ID
            symbol: Trading symbol (e.g., 'BTCUSDT')
            direction: Position direction ('long' or 'short')
            quantity: Order quantity
            strategy_id: Strategy identifier
            price: Limit price (None for market order)
            stop_loss: Optional stop loss level
            take_profit: Optional take profit level

        Returns:
            tuple of (LiveTrade record, position_id if created)

        Raises:
            TradingError: If order placement fails
        """
        order_type = "limit" if price else "market"
        side = "buy" if direction == "long" else "sell"

        logger.info(
            "Placing entry order",
            symbol=symbol,
            direction=direction,
            quantity=quantity,
            order_type=order_type,
            price=price,
        )

        # Create pending trade record
        trade = LiveTrade(
            config_id=config_id,
            symbol=symbol,
            strategy_id=strategy_id,
            direction=direction,
            trade_type="entry",
            order_type=order_type,
            order_status="pending",
            requested_price=price,
            quantity=quantity,
            requested_at=_utc_now(),
        )

        self._session.add(trade)
        await self._session.flush()

        try:
            # Place order on exchange
            if order_type == "market":
                order = await self._bybit.place_market_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                )
            else:
                if price is None:
                    raise TradingError(
                        message="Price required for limit order",
                        error_code="MISSING_PRICE",
                    )
                order = await self._bybit.place_limit_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )

            # Update trade with order details
            trade.order_id = str(order.get("id"))
            order_status = str(order.get("status", "open"))

            # Map ccxt status to our status
            if order_status in ["closed", "filled"]:
                trade.order_status = "filled"
                trade.executed_price = float(order.get("average") or order.get("price", 0))
                trade.filled_quantity = float(order.get("filled", quantity))
                trade.executed_at = _utc_now()
                trade.fees = float(order.get("fee", {}).get("cost", 0))
            elif order_status in ["open", "pending"]:
                trade.order_status = "pending"
            elif order_status == "canceled":
                trade.order_status = "cancelled"
            else:
                trade.order_status = "pending"

            await self._session.flush()

            position_id: Optional[str] = None

            # If order filled immediately, create position
            if trade.order_status == "filled" and trade.executed_price:
                position_id = await self._create_position_from_fill(
                    trade=trade,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

            logger.info(
                "Entry order placed successfully",
                trade_id=trade.id,
                order_id=trade.order_id,
                status=trade.order_status,
                position_id=position_id,
            )

            return trade, position_id

        except TradingError as e:
            # Update trade with error
            trade.order_status = "rejected"
            trade.error_message = e.message
            await self._session.flush()
            logger.error(
                "Entry order rejected",
                trade_id=trade.id,
                error=e.message,
            )
            raise

        except Exception as e:
            # Update trade with error
            trade.order_status = "rejected"
            trade.error_message = str(e)
            await self._session.flush()
            logger.error(
                "Unexpected error placing entry order",
                trade_id=trade.id,
                error=str(e),
            )
            raise TradingError(
                message=f"Failed to place entry order: {e}",
                error_code="ORDER_PLACEMENT_FAILED",
                details={"error": str(e)},
            )

    async def place_exit_order(
        self,
        position_id: str,
        exit_reason: str,
        price: Optional[float] = None,
    ) -> LiveTrade:
        """
        Place an exit order to close a position.

        Args:
            position_id: Position ID to close
            exit_reason: Reason for exit (e.g., 'manual', 'stop_loss', 'take_profit')
            price: Limit price (None for market order)

        Returns:
            LiveTrade record

        Raises:
            NotFoundError: If position not found
            TradingError: If order placement fails
        """
        # Get position
        position = await self._position_repo.get_by_id_or_raise(position_id)

        if position.status != "open":
            raise TradingError(
                message=f"Cannot close position with status: {position.status}",
                error_code="INVALID_POSITION_STATUS",
                details={"position_id": position_id, "status": position.status},
            )

        order_type = "limit" if price else "market"
        # Opposite side to close position
        side = "sell" if position.direction == "long" else "buy"

        logger.info(
            "Placing exit order",
            position_id=position_id,
            symbol=position.symbol,
            direction=position.direction,
            quantity=position.quantity,
            exit_reason=exit_reason,
            order_type=order_type,
        )

        # Create pending trade record
        trade = LiveTrade(
            position_id=position_id,
            config_id=position.config_id,
            symbol=position.symbol,
            strategy_id=position.strategy_id,
            direction=position.direction,
            trade_type=exit_reason if exit_reason in ["stop_loss", "take_profit"] else "exit",
            order_type=order_type,
            order_status="pending",
            requested_price=price,
            quantity=position.quantity,
            requested_at=_utc_now(),
        )

        self._session.add(trade)
        await self._session.flush()

        try:
            # Place order on exchange
            if order_type == "market":
                order = await self._bybit.place_market_order(
                    symbol=position.symbol,
                    side=side,
                    quantity=position.quantity,
                    reduce_only=True,
                )
            else:
                if price is None:
                    raise TradingError(
                        message="Price required for limit order",
                        error_code="MISSING_PRICE",
                    )
                order = await self._bybit.place_limit_order(
                    symbol=position.symbol,
                    side=side,
                    quantity=position.quantity,
                    price=price,
                    reduce_only=True,
                )

            # Update trade with order details
            trade.order_id = str(order.get("id"))
            order_status = str(order.get("status", "open"))

            # Map ccxt status to our status
            if order_status in ["closed", "filled"]:
                trade.order_status = "filled"
                trade.executed_price = float(order.get("average") or order.get("price", 0))
                trade.filled_quantity = float(order.get("filled", position.quantity))
                trade.executed_at = _utc_now()
                trade.fees = float(order.get("fee", {}).get("cost", 0))

                # Close position
                await self._close_position_from_fill(
                    position=position,
                    trade=trade,
                    exit_reason=exit_reason,
                )
            elif order_status in ["open", "pending"]:
                trade.order_status = "pending"
            elif order_status == "canceled":
                trade.order_status = "cancelled"
            else:
                trade.order_status = "pending"

            await self._session.flush()

            logger.info(
                "Exit order placed successfully",
                trade_id=trade.id,
                order_id=trade.order_id,
                status=trade.order_status,
            )

            return trade

        except TradingError as e:
            # Update trade with error
            trade.order_status = "rejected"
            trade.error_message = e.message
            await self._session.flush()
            logger.error(
                "Exit order rejected",
                trade_id=trade.id,
                error=e.message,
            )
            raise

        except Exception as e:
            # Update trade with error
            trade.order_status = "rejected"
            trade.error_message = str(e)
            await self._session.flush()
            logger.error(
                "Unexpected error placing exit order",
                trade_id=trade.id,
                error=str(e),
            )
            raise TradingError(
                message=f"Failed to place exit order: {e}",
                error_code="ORDER_PLACEMENT_FAILED",
                details={"error": str(e)},
            )

    async def handle_partial_fill(
        self,
        order_id: str,
        filled_quantity: float,
        executed_price: float,
        fees: float = 0.0,
    ) -> None:
        """
        Update position for partial order fills.

        Args:
            order_id: Exchange order ID
            filled_quantity: Quantity filled so far
            executed_price: Average execution price
            fees: Fees paid

        Raises:
            NotFoundError: If trade not found
            TradingError: If update fails
        """
        logger.info(
            "Handling partial fill",
            order_id=order_id,
            filled_quantity=filled_quantity,
            executed_price=executed_price,
        )

        # Find trade by order ID
        trade = await self._trade_repo.get_by_order_id(order_id)

        if not trade:
            raise NotFoundError(
                message=f"Trade not found for order: {order_id}",
                error_code="TRADE_NOT_FOUND",
                details={"order_id": order_id},
            )

        # Update trade record
        trade.order_status = "partial"
        trade.filled_quantity = filled_quantity
        trade.executed_price = executed_price
        trade.fees = fees
        trade.executed_at = _utc_now()

        await self._session.flush()

        logger.info(
            "Partial fill recorded",
            trade_id=trade.id,
            filled_quantity=filled_quantity,
        )

    async def _create_position_from_fill(
        self,
        trade: LiveTrade,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> str:
        """
        Create position record from filled entry order.

        Args:
            trade: Filled entry trade
            stop_loss: Optional stop loss level
            take_profit: Optional take profit level

        Returns:
            Position ID
        """
        if not trade.executed_price or not trade.filled_quantity:
            raise TradingError(
                message="Cannot create position without execution details",
                error_code="MISSING_EXECUTION_DETAILS",
            )

        notional_value = trade.executed_price * trade.filled_quantity

        position = Position(
            config_id=trade.config_id,
            symbol=trade.symbol,
            strategy_id=trade.strategy_id,
            direction=trade.direction,
            status="open",
            entry_time=trade.executed_at or _utc_now(),
            entry_price=trade.executed_price,
            entry_order_id=trade.order_id,
            quantity=trade.filled_quantity,
            notional_value=notional_value,
            stop_loss=stop_loss,
            take_profit=take_profit,
            fees_paid=trade.fees,
        )

        self._session.add(position)
        await self._session.flush()

        # Link trade to position
        trade.position_id = position.id
        await self._session.flush()

        logger.info(
            "Position created from fill",
            position_id=position.id,
            symbol=position.symbol,
            entry_price=position.entry_price,
            quantity=position.quantity,
        )

        return position.id

    async def _close_position_from_fill(
        self,
        position: Position,
        trade: LiveTrade,
        exit_reason: str,
    ) -> None:
        """
        Close position from filled exit order.

        Args:
            position: Position to close
            trade: Filled exit trade
            exit_reason: Reason for closure
        """
        if not trade.executed_price:
            raise TradingError(
                message="Cannot close position without execution price",
                error_code="MISSING_EXECUTION_PRICE",
            )

        # Calculate realized P&L
        if position.direction == "long":
            pnl = (trade.executed_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - trade.executed_price) * position.quantity

        # Subtract fees
        total_fees = position.fees_paid + trade.fees
        realized_pnl = pnl - total_fees

        # Update trade with realized P&L
        trade.realized_pnl = realized_pnl

        # Close position using repository method
        await self._position_repo.close_position(
            id=position.id,
            exit_price=trade.executed_price,
            exit_reason=exit_reason,
            realized_pnl=realized_pnl,
            fees=trade.fees,
            exit_order_id=trade.order_id,
        )

        logger.info(
            "Position closed from fill",
            position_id=position.id,
            exit_price=trade.executed_price,
            realized_pnl=realized_pnl,
            exit_reason=exit_reason,
        )
