"""
Risk management API endpoints.

Provides endpoints for kill switch control, risk state monitoring,
and risk limit management.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import TradingError
from backend.core.logging import get_logger
from backend.dependencies import get_async_session
from backend.services.risk_service import RiskService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/risk", tags=["risk"])


# Request/Response Models
class KillSwitchActivateRequest(BaseModel):
    """Request to activate kill switch."""

    reason: str = Field(
        ...,
        description="Reason for activating kill switch",
        min_length=1,
        max_length=500,
    )


class RiskLimitsUpdateRequest(BaseModel):
    """Request to update risk limits."""

    max_daily_loss: Optional[float] = Field(
        None,
        description="Maximum daily loss allowed (positive number)",
        gt=0,
    )
    max_positions: Optional[int] = Field(
        None,
        description="Maximum number of open positions",
        gt=0,
    )
    max_exposure: Optional[float] = Field(
        None,
        description="Maximum total notional exposure",
        gt=0,
    )


class RiskLimits(BaseModel):
    """Risk limits configuration."""

    max_daily_loss: float = Field(default=1000.0, description="Maximum daily loss allowed")
    max_positions: int = Field(default=5, description="Maximum number of open positions")
    max_exposure: float = Field(default=50000.0, description="Maximum total notional exposure")
    max_position_size: Optional[float] = Field(default=10000.0, description="Maximum single position size")


class RiskStateResponse(BaseModel):
    """Risk state response."""

    kill_switch_active: bool
    kill_switch_reason: Optional[str]
    kill_switch_activated_at: Optional[str]
    daily_pnl: float
    daily_trades: int
    daily_reset_date: Optional[str]
    total_open_positions: int
    total_exposure: float
    total_unrealized_pnl: float
    updated_at: str
    risk_limits: RiskLimits = Field(default_factory=RiskLimits)


class RiskLimitsResponse(BaseModel):
    """Risk limits update response."""

    max_daily_loss: Optional[float]
    max_positions: Optional[int]
    max_exposure: Optional[float]
    within_limits: bool
    breach_reason: Optional[str]


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


# Dependency to get risk service
async def get_risk_service(
    session: AsyncSession = Depends(get_async_session),
) -> RiskService:
    """Get risk service instance."""
    return RiskService(session)


@router.get(
    "",
    response_model=RiskStateResponse,
    summary="Get risk state",
    description="Get current risk management state including kill switch, daily P&L, and exposure",
)
async def get_risk_state(
    service: RiskService = Depends(get_risk_service),
) -> RiskStateResponse:
    """
    Get current risk state.

    Returns complete risk management state including:
    - Kill switch status and reason
    - Daily P&L and trade count
    - Total open positions and exposure
    - Total unrealized P&L
    """
    try:
        state = await service.get_risk_state()
        return RiskStateResponse(**state)

    except TradingError as e:
        logger.error("Failed to get risk state", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error getting risk state", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.post(
    "/kill-switch",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate kill switch",
    description="Activate emergency kill switch to stop all trading immediately",
)
async def activate_kill_switch(
    request: KillSwitchActivateRequest,
    service: RiskService = Depends(get_risk_service),
) -> MessageResponse:
    """
    Activate emergency kill switch.

    Stops all trading immediately. All new trade attempts will be blocked
    until the kill switch is manually deactivated.

    Use this for emergency situations such as:
    - Critical system errors
    - Market conditions requiring immediate halt
    - Manual intervention needed
    - Risk limits severely breached
    """
    try:
        await service.activate_kill_switch(reason=request.reason)

        logger.warning(
            "Kill switch activated via API",
            reason=request.reason,
        )

        return MessageResponse(
            message=f"Kill switch activated: {request.reason}"
        )

    except TradingError as e:
        logger.error("Failed to activate kill switch", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error activating kill switch", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.delete(
    "/kill-switch",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Deactivate kill switch",
    description="Deactivate kill switch to resume trading",
)
async def deactivate_kill_switch(
    service: RiskService = Depends(get_risk_service),
) -> MessageResponse:
    """
    Deactivate kill switch to resume trading.

    Use with caution - ensure the reason for activation has been resolved
    before deactivating the kill switch.
    """
    try:
        await service.deactivate_kill_switch()

        logger.info("Kill switch deactivated via API")

        return MessageResponse(message="Kill switch deactivated - trading resumed")

    except TradingError as e:
        logger.error("Failed to deactivate kill switch", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error deactivating kill switch", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.put(
    "/limits",
    response_model=RiskLimitsResponse,
    status_code=status.HTTP_200_OK,
    summary="Update risk limits",
    description="Update risk limits and check current state against new limits",
)
async def update_risk_limits(
    request: RiskLimitsUpdateRequest,
    service: RiskService = Depends(get_risk_service),
) -> RiskLimitsResponse:
    """
    Update risk limits.

    Updates the risk limits and immediately checks if current state
    violates the new limits. If limits are breached, the kill switch
    will be automatically activated.

    Returns the updated limits and whether they are currently within bounds.
    """
    try:
        # Validate at least one limit is provided
        if all(
            v is None
            for v in [
                request.max_daily_loss,
                request.max_positions,
                request.max_exposure,
            ]
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "VALIDATION_ERROR",
                    "message": "At least one limit must be provided",
                },
            )

        result = await service.update_risk_limits(
            max_daily_loss=request.max_daily_loss,
            max_positions=request.max_positions,
            max_exposure=request.max_exposure,
        )

        logger.info(
            "Risk limits updated via API",
            limits=result,
        )

        return RiskLimitsResponse(**result)

    except TradingError as e:
        logger.error("Failed to update risk limits", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error updating risk limits", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )


@router.post(
    "/reset-daily",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset daily counters",
    description="Manually reset daily P&L and trade counters",
)
async def reset_daily_counters(
    service: RiskService = Depends(get_risk_service),
) -> MessageResponse:
    """
    Manually reset daily counters.

    Resets daily P&L and trade count to zero. Use this for testing
    or manual intervention. Daily counters normally reset automatically
    at the start of each UTC day.
    """
    try:
        await service.reset_daily_counters()

        logger.info("Daily counters reset via API")

        return MessageResponse(message="Daily counters reset successfully")

    except TradingError as e:
        logger.error("Failed to reset daily counters", error=e.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.to_dict(),
        )
    except Exception as e:
        logger.error("Unexpected error resetting daily counters", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": str(e)},
        )
