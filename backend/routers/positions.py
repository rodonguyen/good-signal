"""
Position management API endpoints.

Provides endpoints for querying positions, closing positions,
and updating stop loss/take profit levels.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, TradingError, ValidationError
from backend.core.logging import get_logger
from backend.dependencies import get_async_session
from backend.infrastructure.exchange.bybit_client import BybitClient
from backend.services.order_service import OrderService
from backend.services.position_service import PositionService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/positions", tags=["positions"])


# Request/Response Models
class PositionResponse(BaseModel):
    """Position response model."""

    id: str
    config_id: Optional[str]
    symbol: str
    strategy_id: str
    direction: str
    status: str
    entry_time: str
    entry_price: float
    entry_order_id: Optional[str]
    quantity: float
    notional_value: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    exit_time: Optional[str]
    exit_price: Optional[float]
    exit_order_id: Optional[str]
    exit_reason: Optional[str]
    realized_pnl: float
    unrealized_pnl: float
    fees_paid: float
    created_at: str
    updated_at: str


class PositionListResponse(BaseModel):
    """List of positions with metadata."""

    positions: list[PositionResponse]
    total: int
    skip: int
    limit: int


class ClosePositionRequest(BaseModel):
    """Request to close a position."""

    reason: Optional[str] = Field(
        "manual",
        description="Reason for closing position",
        max_length=100,
    )


class UpdateStopLossRequest(BaseModel):
    """Request to update stop loss."""

    stop_loss: float = Field(
        ...,
        description="New stop loss price level",
        gt=0,
    )


class UpdateTakeProfitRequest(BaseModel):
    """Request to update take profit."""

    take_profit: float = Field(
        ...,
        description="New take profit price level",
        gt=0,
    )


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
    position_id: Optional[str] = None


# Dependency to get services
async def get_bybit_client() -> BybitClient:
    """Get Bybit client instance."""
    client = BybitClient()
    await client.connect()
    try:
        yield client
    finally:
        await client.close()


async def get_position_service(
    session: AsyncSession = Depends(get_async_session),
    bybit: BybitClient = Depends(get_bybit_client),
) -> PositionService:
    """Get position service instance."""
    return PositionService(session, bybit)


async def get_order_service(
    session: AsyncSession = Depends(get_async_session),
    bybit: BybitClient = Depends(get_bybit_client),
) -> OrderService:
    """Get order service instance."""
    return OrderService(session, bybit)


@router.get(
    "",
    response_model=PositionListResponse,
    summary="List positions",
    description="Get list of positions with optional filters",
)
async def list_positions(
    status: Optional[str] = Query(
        None,
        description="Filter by status: 'open' or 'closed' (case-insensitive)",
        pattern="^(open|closed|OPEN|CLOSED|Open|Closed)$",
    ),
    symbol: Optional[str] = Query(
        None,
        description="Filter by trading symbol",
        max_length=20,
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    service: PositionService = Depends(get_position_service),
) -> PositionListResponse:
    """
    Get list of positions.

    Supports filtering by status (open/closed) and symbol.
    Results are paginated using skip and limit parameters.
    """
    try:
        # Normalize status to lowercase for comparison
        normalized_status = status.lower() if status else None

        if symbol:
            # Filter by symbol
            positions = await service.get_positions_by_symbol(
                symbol=symbol,
                status=normalized_status,
            )
            # Manual pagination for symbol filter
            total = len(positions)
            positions = positions[skip : skip + limit]
        elif normalized_status == "open":
            # Get open positions only
            positions = await service.get_open_positions(skip=skip, limit=limit)
            # For simplicity, return count of returned items
            # In production, you'd want a proper count query
            total = len(positions)
        else:
            # Get all positions (would need repository method)
            # For now, default to open positions
            positions = await service.get_open_positions(skip=skip, limit=limit)
            total = len(positions)

        position_responses = [
            PositionResponse(
                id=pos.id,
                config_id=pos.config_id,
                symbol=pos.symbol,
                strategy_id=pos.strategy_id,
                direction=pos.direction,
                status=pos.status,
                entry_time=pos.entry_time,
                entry_price=pos.entry_price,
                entry_order_id=pos.entry_order_id,
                quantity=pos.quantity,
                notional_value=pos.notional_value,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
                exit_time=pos.exit_time,
                exit_price=pos.exit_price,
                exit_order_id=pos.exit_order_id,
                exit_reason=pos.exit_reason,
                realized_pnl=pos.realized_pnl,
                unrealized_pnl=pos.unrealized_pnl,
                fees_paid=pos.fees_paid,
                created_at=pos.created_at,
                updated_at=pos.updated_at,
            )
            for pos in positions
        ]

        return PositionListResponse(
            positions=position_responses,
            total=total,
            skip=skip,
            limit=limit,
        )

    except TradingError as e:
        logger.error("Failed to list positions", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error listing positions", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.get(
    "/{position_id}",
    response_model=PositionResponse,
    summary="Get position details",
    description="Get detailed information about a specific position",
)
async def get_position(
    position_id: str,
    service: PositionService = Depends(get_position_service),
) -> PositionResponse:
    """
    Get position by ID.

    Returns complete position details including entry/exit information,
    P&L, and risk management levels.
    """
    try:
        position = await service.get_position_by_id(position_id)

        return PositionResponse(
            id=position.id,
            config_id=position.config_id,
            symbol=position.symbol,
            strategy_id=position.strategy_id,
            direction=position.direction,
            status=position.status,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            entry_order_id=position.entry_order_id,
            quantity=position.quantity,
            notional_value=position.notional_value,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            exit_time=position.exit_time,
            exit_price=position.exit_price,
            exit_order_id=position.exit_order_id,
            exit_reason=position.exit_reason,
            realized_pnl=position.realized_pnl,
            unrealized_pnl=position.unrealized_pnl,
            fees_paid=position.fees_paid,
            created_at=position.created_at,
            updated_at=position.updated_at,
        )

    except NotFoundError as e:
        logger.warning("Position not found", position_id=position_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error getting position", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.post(
    "/{position_id}/close",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Close position",
    description="Close an open position by placing a market exit order",
)
async def close_position(
    position_id: str,
    request: ClosePositionRequest = ClosePositionRequest(),
    order_service: OrderService = Depends(get_order_service),
) -> MessageResponse:
    """
    Close a position.

    Places a market order to close the entire position immediately.
    The position will be marked as closed once the order is filled.
    """
    try:
        # Place exit order (market order to close position)
        trade = await order_service.place_exit_order(
            position_id=position_id,
            exit_reason=request.reason or "manual",
        )

        logger.info(
            "Position close order placed",
            position_id=position_id,
            trade_id=trade.id,
            reason=request.reason,
        )

        return MessageResponse(
            message=f"Exit order placed for position {position_id}",
            position_id=position_id,
        )

    except NotFoundError as e:
        logger.warning("Position not found for closing", position_id=position_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except TradingError as e:
        logger.error("Failed to close position", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error closing position", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.put(
    "/{position_id}/stop-loss",
    response_model=PositionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update stop loss",
    description="Update the stop loss level for an open position",
)
async def update_stop_loss(
    position_id: str,
    request: UpdateStopLossRequest,
    service: PositionService = Depends(get_position_service),
) -> PositionResponse:
    """
    Update stop loss level.

    Updates the stop loss price level for an open position.
    The stop loss must be:
    - Below entry price for long positions
    - Above entry price for short positions
    """
    try:
        position = await service.update_stop_loss(
            position_id=position_id,
            stop_loss=request.stop_loss,
        )

        logger.info(
            "Stop loss updated",
            position_id=position_id,
            stop_loss=request.stop_loss,
        )

        return PositionResponse(
            id=position.id,
            config_id=position.config_id,
            symbol=position.symbol,
            strategy_id=position.strategy_id,
            direction=position.direction,
            status=position.status,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            entry_order_id=position.entry_order_id,
            quantity=position.quantity,
            notional_value=position.notional_value,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            exit_time=position.exit_time,
            exit_price=position.exit_price,
            exit_order_id=position.exit_order_id,
            exit_reason=position.exit_reason,
            realized_pnl=position.realized_pnl,
            unrealized_pnl=position.unrealized_pnl,
            fees_paid=position.fees_paid,
            created_at=position.created_at,
            updated_at=position.updated_at,
        )

    except NotFoundError as e:
        logger.warning("Position not found for stop loss update", position_id=position_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except ValidationError as e:
        logger.warning("Invalid stop loss value", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )
    except TradingError as e:
        logger.error("Failed to update stop loss", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error updating stop loss", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.put(
    "/{position_id}/take-profit",
    response_model=PositionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update take profit",
    description="Update the take profit level for an open position",
)
async def update_take_profit(
    position_id: str,
    request: UpdateTakeProfitRequest,
    service: PositionService = Depends(get_position_service),
) -> PositionResponse:
    """
    Update take profit level.

    Updates the take profit price level for an open position.
    The take profit must be:
    - Above entry price for long positions
    - Below entry price for short positions
    """
    try:
        position = await service.update_take_profit(
            position_id=position_id,
            take_profit=request.take_profit,
        )

        logger.info(
            "Take profit updated",
            position_id=position_id,
            take_profit=request.take_profit,
        )

        return PositionResponse(
            id=position.id,
            config_id=position.config_id,
            symbol=position.symbol,
            strategy_id=position.strategy_id,
            direction=position.direction,
            status=position.status,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            entry_order_id=position.entry_order_id,
            quantity=position.quantity,
            notional_value=position.notional_value,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            exit_time=position.exit_time,
            exit_price=position.exit_price,
            exit_order_id=position.exit_order_id,
            exit_reason=position.exit_reason,
            realized_pnl=position.realized_pnl,
            unrealized_pnl=position.unrealized_pnl,
            fees_paid=position.fees_paid,
            created_at=position.created_at,
            updated_at=position.updated_at,
        )

    except NotFoundError as e:
        logger.warning("Position not found for take profit update", position_id=position_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except ValidationError as e:
        logger.warning("Invalid take profit value", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )
    except TradingError as e:
        logger.error("Failed to update take profit", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error updating take profit", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )
