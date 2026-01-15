"""
Backtest API endpoints for creating, managing, and analyzing backtests.

Provides RESTful endpoints for:
- Creating and queuing new backtests
- Listing and filtering backtests
- Retrieving backtest results and details
- Accessing backtest trades with pagination
- Cancelling pending/running backtests
- Deleting completed backtests
"""

import json
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, DatabaseError, ValidationError
from backend.core.logging import get_logger
from backend.dependencies import get_db
from backend.infrastructure.database.models import Backtest, BacktestTrade
from backend.infrastructure.database.repositories import (
    BacktestRepository,
    BacktestTradeRepository,
)
from backend.infrastructure.queue.task_manager import TaskManager
from backend.infrastructure.database.connection import get_async_session
from backend.schemas import PaginatedResponse
from backend.schemas.backtest import (
    BacktestRequest,
    BacktestSummary,
    BacktestResult,
    BacktestMetrics,
    BacktestTradeResponse,
    BacktestCancelResponse,
    StrategyConfig,
    FilterConfig,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


# Dependency injection helpers
def get_backtest_repo(db: AsyncSession = Depends(get_db)) -> BacktestRepository:
    """Dependency injection for BacktestRepository."""
    return BacktestRepository(db)


def get_trade_repo(db: AsyncSession = Depends(get_db)) -> BacktestTradeRepository:
    """Dependency injection for BacktestTradeRepository."""
    return BacktestTradeRepository(db)


async def get_task_manager() -> TaskManager:
    """
    Dependency injection for TaskManager.

    Creates TaskManager with session factory for background task processing.
    Uses the same session factory as the main application for SQLite compatibility.
    """
    from backend.dependencies import db_manager

    if db_manager._session_factory is None:
        # Fallback for tests or when db_manager isn't initialized
        from backend.infrastructure.database.connection import AsyncSessionLocal

        return TaskManager(session_factory=AsyncSessionLocal, max_workers=2)
    return TaskManager(session_factory=db_manager._session_factory, max_workers=2)


# Type aliases for cleaner signatures
BacktestRepoDep = Annotated[BacktestRepository, Depends(get_backtest_repo)]
TradeRepoDep = Annotated[BacktestTradeRepository, Depends(get_trade_repo)]
TaskManagerDep = Annotated[TaskManager, Depends(get_task_manager)]


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


def _backtest_to_summary(backtest: Backtest) -> BacktestSummary:
    """Convert Backtest model to BacktestSummary schema."""
    return BacktestSummary(
        id=backtest.id,
        name=backtest.name,
        status=backtest.status,
        progress=backtest.progress,
        symbols=json.loads(backtest.symbols),
        created_at=backtest.created_at,
        completed_at=backtest.completed_at,
        total_return=backtest.total_return,
        total_trades=backtest.total_trades,
    )


def _backtest_to_result(backtest: Backtest) -> BacktestResult:
    """Convert Backtest model to BacktestResult schema."""
    # Build metrics object if backtest has results
    metrics = None
    if backtest.status == "completed" and backtest.total_trades is not None:
        initial_equity = backtest.initial_equity or 10000.0
        total_return = backtest.total_return or 0.0
        max_drawdown = backtest.max_drawdown or 0.0
        win_rate = backtest.win_rate or 0.0
        total_trades = backtest.total_trades or 0

        # Calculate derived metrics
        total_return_pct = total_return / initial_equity if initial_equity > 0 else 0
        winning_trades = int(round(total_trades * win_rate))
        losing_trades = total_trades - winning_trades

        # Try to get additional metrics from results_json
        avg_win = None
        avg_loss = None
        largest_win = None
        largest_loss = None
        if backtest.results_json:
            try:
                results = json.loads(backtest.results_json)
                avg_win = results.get("avg_win")
                avg_loss = results.get("avg_loss")
                largest_win = results.get("largest_win")
                largest_loss = results.get("largest_loss")
            except (json.JSONDecodeError, TypeError):
                pass

        metrics = BacktestMetrics(
            total_return=total_return,
            total_return_pct=total_return_pct,
            sharpe_ratio=backtest.sharpe_ratio,
            max_drawdown=abs(max_drawdown),
            win_rate=win_rate,
            profit_factor=backtest.profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
        )

    # Parse config to get timeframe and other settings
    config = json.loads(backtest.config_json)
    filters = json.loads(backtest.filters) if backtest.filters else None

    # Calculate final equity
    final_equity = None
    if backtest.status == "completed" and backtest.initial_equity and backtest.total_return is not None:
        final_equity = backtest.initial_equity + backtest.total_return

    # Extract timeframe from first strategy if available
    strategies = json.loads(backtest.strategies)
    timeframe = None
    if strategies and len(strategies) > 0:
        timeframe = strategies[0].get("signal_timeframe")

    return BacktestResult(
        id=backtest.id,
        name=backtest.name,
        status=backtest.status,
        progress=backtest.progress,
        config=config,
        symbols=json.loads(backtest.symbols),
        strategies=strategies,
        filters=filters,
        timeframe=timeframe,
        fee_rate=backtest.fee_rate,
        initial_equity=backtest.initial_equity,
        final_equity=final_equity,
        metrics=metrics,
        created_at=backtest.created_at,
        completed_at=backtest.completed_at,
        error_message=backtest.error_message,
    )


def _trade_to_response(trade: BacktestTrade) -> BacktestTradeResponse:
    """Convert BacktestTrade model to BacktestTradeResponse schema."""
    return BacktestTradeResponse(
        id=trade.id,
        symbol=trade.symbol,
        strategy_id=trade.strategy_id,
        direction=trade.direction,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        exit_reason=trade.exit_reason,
        stop_level=trade.stop_level,
        tp_level=trade.tp_level,
        raw_pnl=trade.raw_pnl,
        fees=trade.fees,
        net_pnl=trade.net_pnl,
        portfolio_pnl=trade.portfolio_pnl,
        position_size=trade.position_size,
        equity=trade.equity,
        drawdown=trade.drawdown,
    )


@router.post(
    "",
    response_model=BacktestResult,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Backtest",
    description=(
        "Create and queue a new backtest for execution. "
        "The backtest will be processed asynchronously by a worker. "
        "Returns the created backtest with 'pending' status."
    ),
    responses={
        201: {
            "description": "Backtest created and queued successfully",
        },
        422: {
            "description": "Validation error in request parameters",
        },
        500: {
            "description": "Database or task queue error",
        },
    },
)
async def create_backtest(
    request: BacktestRequest,
    backtest_repo: BacktestRepoDep,
    task_manager: TaskManagerDep,
) -> BacktestResult:
    """
    Create and queue a new backtest.

    Creates a backtest record in the database and enqueues it for
    asynchronous processing by a background worker.

    Args:
        request: Backtest configuration with symbols, strategies, and parameters
        backtest_repo: BacktestRepository dependency
        task_manager: TaskManager dependency

    Returns:
        BacktestResult: Created backtest details with pending status

    Raises:
        HTTPException: If database or task queue operations fail
    """
    try:
        # Convert request to backtest configuration
        config_dict = {
            "version": 1,
            "engine": {
                "fee_rate": request.fee_rate,
                "debug": False,
                "cache": {
                    "enabled": True,
                    "dir": "data/cache/backtest",
                    "version": "v1",
                },
                "outputs": {
                    "trades_dir": "data/trades",
                    "portfolio_dir": "data/portfolio",
                    "reports_dir": "outputs/reports",
                },
            },
            "data": {
                "source": "bybit",
                "raw_dir": "data/raw/crypto",
                "raw_1m_dir": "data/raw/crypto",
                "start_date": request.start_date,
                "end_date": request.end_date,
            },
            "universe": {
                "symbols": request.symbols,
            },
            "strategies": [
                {
                    "id": s.type,
                    "type": s.type,
                    "enabled": s.enabled,
                    "signal_timeframe": s.signal_timeframe,
                    "params": s.params,
                }
                for s in request.strategies
            ],
            "steps": {
                "filters": {
                    "enabled": bool(request.filters),
                    "config_path": "config/backtest/filters.yaml",
                },
                "portfolio": {
                    "enabled": True,
                    "initial_equity": request.initial_equity,
                    "risk_per_trade": request.risk_per_trade,
                },
                "analysis": {
                    "enabled": True,
                },
            },
        }

        # Add filters if provided
        if request.filters:
            config_dict["filters"] = [
                {
                    "type": f.type,
                    "enabled": f.enabled,
                    "params": f.params,
                }
                for f in request.filters
            ]

        # Create backtest record
        backtest = Backtest(
            name=request.name,
            status="pending",
            progress=0.0,
            config_json=json.dumps(config_dict),
            symbols=json.dumps(request.symbols),
            strategies=json.dumps([s.model_dump() for s in request.strategies]),
            filters=json.dumps([f.model_dump() for f in request.filters]) if request.filters else None,
            fee_rate=request.fee_rate,
            initial_equity=request.initial_equity,
            risk_per_trade=request.risk_per_trade,
            start_date=request.start_date,
            end_date=request.end_date,
            created_at=_utc_now(),
        )

        backtest = await backtest_repo.create(backtest)

        logger.info(
            "Backtest created",
            backtest_id=backtest.id,
            name=request.name,
            symbols=request.symbols,
            strategies=[s.type for s in request.strategies],
        )

        # Enqueue backtest task for background processing
        task_payload = {
            "backtest_id": backtest.id,
            "config": config_dict,
        }

        # Pass session to share transaction with backtest creation
        # This prevents SQLite database locking issues
        task_id = await task_manager.enqueue(
            task_type="backtest",
            payload=task_payload,
            priority=0,
            max_attempts=1,  # Backtests should not auto-retry
            session=backtest_repo.session,
        )

        logger.info(
            "Backtest task enqueued",
            backtest_id=backtest.id,
            task_id=task_id,
        )

        # Commit transaction so backtest is visible immediately in list
        await backtest_repo.session.commit()

        return _backtest_to_result(backtest)

    except ValidationError as e:
        logger.warning("Backtest validation error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.to_dict(),
        )
    except (DatabaseError, Exception) as e:
        logger.error("Failed to create backtest", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "BACKTEST_CREATE_FAILED", "message": str(e)},
        )


@router.get(
    "",
    response_model=PaginatedResponse[BacktestSummary],
    summary="List Backtests",
    description=(
        "List all backtests with optional status filtering and pagination. " "Returns summaries ordered by creation date (most recent first)."
    ),
    responses={
        200: {
            "description": "Backtest list retrieved successfully",
        },
    },
)
async def list_backtests(
    backtest_repo: BacktestRepoDep,
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status (pending, running, completed, failed, cancelled)",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page"),
) -> PaginatedResponse[BacktestSummary]:
    """
    List all backtests with optional filtering and pagination.

    Args:
        backtest_repo: BacktestRepository dependency
        status_filter: Optional status filter
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        PaginatedResponse[BacktestSummary]: Paginated backtest summaries

    Raises:
        HTTPException: If database query fails
    """
    try:
        skip = (page - 1) * page_size

        # Get backtests based on filter
        if status_filter:
            backtests = await backtest_repo.get_by_status(
                status=status_filter,
                skip=skip,
                limit=page_size,
            )
            total = await backtest_repo.count_by_status(status_filter)
        else:
            backtests = await backtest_repo.get_all(skip=skip, limit=page_size)
            total = await backtest_repo.count()

        summaries = [_backtest_to_summary(bt) for bt in backtests]

        return PaginatedResponse.create(
            items=summaries,
            total=total,
            page=page,
            page_size=page_size,
        )

    except DatabaseError as e:
        logger.error("Failed to list backtests", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "BACKTEST_LIST_FAILED", "message": str(e)},
        )


@router.get(
    "/{backtest_id}",
    response_model=BacktestResult,
    summary="Get Backtest Details",
    description=("Get detailed information about a specific backtest including " "configuration, performance metrics, and execution status."),
    responses={
        200: {
            "description": "Backtest details retrieved successfully",
        },
        404: {
            "description": "Backtest not found",
        },
    },
)
async def get_backtest(
    backtest_id: str,
    backtest_repo: BacktestRepoDep,
) -> BacktestResult:
    """
    Get detailed backtest information.

    Args:
        backtest_id: Unique backtest identifier
        backtest_repo: BacktestRepository dependency

    Returns:
        BacktestResult: Detailed backtest information

    Raises:
        HTTPException: If backtest not found or database error
    """
    try:
        backtest = await backtest_repo.get_by_id(backtest_id)

        if backtest is None:
            raise NotFoundError(
                message=f"Backtest not found: {backtest_id}",
                error_code="BACKTEST_NOT_FOUND",
                details={"backtest_id": backtest_id},
            )

        return _backtest_to_result(backtest)

    except NotFoundError as e:
        logger.warning("Backtest not found", backtest_id=backtest_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except DatabaseError as e:
        logger.error("Failed to get backtest", backtest_id=backtest_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "BACKTEST_GET_FAILED", "message": str(e)},
        )


@router.get(
    "/{backtest_id}/trades",
    response_model=PaginatedResponse[BacktestTradeResponse],
    summary="Get Backtest Trades",
    description=("Get all trades from a specific backtest with pagination support. " "Trades are ordered by entry time."),
    responses={
        200: {
            "description": "Trades retrieved successfully",
        },
        404: {
            "description": "Backtest not found",
        },
    },
)
async def get_backtest_trades(
    backtest_id: str,
    backtest_repo: BacktestRepoDep,
    trade_repo: TradeRepoDep,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=10000, description="Items per page"),
) -> PaginatedResponse[BacktestTradeResponse]:
    """
    Get paginated trades for a specific backtest.

    Args:
        backtest_id: Unique backtest identifier
        backtest_repo: BacktestRepository dependency
        trade_repo: BacktestTradeRepository dependency
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        PaginatedResponse[BacktestTradeResponse]: Paginated trade list

    Raises:
        HTTPException: If backtest not found or database error
    """
    try:
        # Verify backtest exists
        backtest = await backtest_repo.get_by_id(backtest_id)
        if backtest is None:
            raise NotFoundError(
                message=f"Backtest not found: {backtest_id}",
                error_code="BACKTEST_NOT_FOUND",
                details={"backtest_id": backtest_id},
            )

        # Get trades with pagination
        skip = (page - 1) * page_size
        trades = await trade_repo.get_by_backtest(
            backtest_id=backtest_id,
            skip=skip,
            limit=page_size,
        )
        total = await trade_repo.count_by_backtest(backtest_id)

        trade_responses = [_trade_to_response(trade) for trade in trades]

        return PaginatedResponse.create(
            items=trade_responses,
            total=total,
            page=page,
            page_size=page_size,
        )

    except NotFoundError as e:
        logger.warning("Backtest not found for trades", backtest_id=backtest_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except DatabaseError as e:
        logger.error("Failed to get backtest trades", backtest_id=backtest_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "TRADES_GET_FAILED", "message": str(e)},
        )


@router.delete(
    "/{backtest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Backtest",
    description=(
        "Delete a backtest and all associated trades. "
        "Only completed, failed, or cancelled backtests can be deleted. "
        "Pending or running backtests must be cancelled first."
    ),
    responses={
        204: {
            "description": "Backtest deleted successfully",
        },
        404: {
            "description": "Backtest not found",
        },
        409: {
            "description": "Backtest cannot be deleted (still running or pending)",
        },
    },
)
async def delete_backtest(
    backtest_id: str,
    backtest_repo: BacktestRepoDep,
    trade_repo: TradeRepoDep,
) -> None:
    """
    Delete a backtest and all associated trades.

    Args:
        backtest_id: Unique backtest identifier
        backtest_repo: BacktestRepository dependency
        trade_repo: BacktestTradeRepository dependency

    Raises:
        HTTPException: If backtest not found, still running, or database error
    """
    try:
        # Verify backtest exists
        backtest = await backtest_repo.get_by_id(backtest_id)
        if backtest is None:
            raise NotFoundError(
                message=f"Backtest not found: {backtest_id}",
                error_code="BACKTEST_NOT_FOUND",
                details={"backtest_id": backtest_id},
            )

        # Check if backtest can be deleted
        if backtest.status in ("pending", "running"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "BACKTEST_CANNOT_DELETE",
                    "message": f"Cannot delete {backtest.status} backtest. Cancel it first.",
                    "backtest_id": backtest_id,
                    "status": backtest.status,
                },
            )

        # Delete trades first (cascade should handle this, but being explicit)
        await trade_repo.delete_by_backtest(backtest_id)

        # Delete backtest
        await backtest_repo.delete(backtest_id)

        logger.info(
            "Backtest deleted",
            backtest_id=backtest_id,
            name=backtest.name,
        )

    except NotFoundError as e:
        logger.warning("Backtest not found for deletion", backtest_id=backtest_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except DatabaseError as e:
        logger.error("Failed to delete backtest", backtest_id=backtest_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "BACKTEST_DELETE_FAILED", "message": str(e)},
        )


@router.post(
    "/{backtest_id}/cancel",
    response_model=BacktestCancelResponse,
    summary="Cancel Backtest",
    description=(
        "Cancel a pending or running backtest. "
        "The backtest status will be set to 'cancelled'. "
        "Completed, failed, or already cancelled backtests will return an error."
    ),
    responses={
        200: {
            "description": "Backtest cancelled successfully",
        },
        404: {
            "description": "Backtest not found",
        },
        409: {
            "description": "Backtest cannot be cancelled (wrong status)",
        },
    },
)
async def cancel_backtest(
    backtest_id: str,
    backtest_repo: BacktestRepoDep,
    task_manager: TaskManagerDep,
) -> BacktestCancelResponse:
    """
    Cancel a pending backtest.

    Cancels the backtest in the database and attempts to cancel
    the associated task in the task queue.

    Args:
        backtest_id: Unique backtest identifier
        backtest_repo: BacktestRepository dependency
        task_manager: TaskManager dependency

    Returns:
        BacktestCancelResponse: Cancellation result

    Raises:
        HTTPException: If backtest not found, cannot be cancelled, or database error
    """
    try:
        # Verify backtest exists
        backtest = await backtest_repo.get_by_id(backtest_id)
        if backtest is None:
            raise NotFoundError(
                message=f"Backtest not found: {backtest_id}",
                error_code="BACKTEST_NOT_FOUND",
                details={"backtest_id": backtest_id},
            )

        # Check if backtest can be cancelled
        if backtest.status not in ("pending", "running"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "BACKTEST_CANNOT_CANCEL",
                    "message": f"Cannot cancel {backtest.status} backtest. Only pending or running backtests can be cancelled.",
                    "backtest_id": backtest_id,
                    "status": backtest.status,
                },
            )

        # Cancel in database (works for both pending and running)
        if backtest.status == "pending":
            cancelled = await backtest_repo.cancel_pending(backtest_id)
        else:  # running
            # For running backtests, directly update status to cancelled
            await backtest_repo.update_status(backtest_id, "cancelled", error_message="Cancelled by user")
            cancelled = True

        if not cancelled:
            # Race condition - status changed between get and cancel
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "BACKTEST_CANCEL_RACE",
                    "message": "Backtest status changed during cancellation. Please retry.",
                    "backtest_id": backtest_id,
                },
            )

        # Attempt to cancel task in queue (best effort)
        # Note: The task_id is not stored in the backtest record,
        # so we cannot directly cancel it. The worker should check
        # backtest status before processing.

        logger.info(
            "Backtest cancelled",
            backtest_id=backtest_id,
            name=backtest.name,
        )

        return BacktestCancelResponse(
            success=True,
            message="Backtest cancelled successfully",
            backtest_id=backtest_id,
        )

    except NotFoundError as e:
        logger.warning("Backtest not found for cancellation", backtest_id=backtest_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except DatabaseError as e:
        logger.error("Failed to cancel backtest", backtest_id=backtest_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "BACKTEST_CANCEL_FAILED", "message": str(e)},
        )
