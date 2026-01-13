"""
Risk management service for live trading.

Handles risk state monitoring, kill switch control, and risk limit enforcement.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import RiskLimitError, TradingError
from backend.core.logging import get_logger
from backend.infrastructure.database.models import RiskState
from backend.infrastructure.database.repositories.position_repo import PositionRepository
from backend.infrastructure.database.repositories.risk_repo import RiskStateRepository

logger = get_logger(__name__)


class RiskService:
    """
    Service for managing trading risk state.

    Provides kill switch control, daily P&L tracking,
    and risk limit enforcement.

    Example:
        >>> service = RiskService(session)
        >>> can_trade = await service.check_can_trade()
        >>> if not can_trade:
        ...     print("Trading is disabled")
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize risk service.

        Args:
            session: Database session
        """
        self._session = session
        self._risk_repo = RiskStateRepository(session)
        self._position_repo = PositionRepository(session)

    async def check_can_trade(
        self,
        max_daily_loss: Optional[float] = None,
        max_positions: Optional[int] = None,
        max_exposure: Optional[float] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if trading is allowed.

        Verifies kill switch status and optionally checks risk limits.

        Args:
            max_daily_loss: Optional maximum daily loss limit to check
            max_positions: Optional maximum positions limit to check
            max_exposure: Optional maximum exposure limit to check

        Returns:
            tuple of (can_trade: bool, reason: Optional[str])
            If can_trade is False, reason contains the blocking reason.

        Raises:
            TradingError: If risk state check fails
        """
        try:
            state = await self._risk_repo.get_state()

            # Check kill switch
            if state.kill_switch_active:
                logger.warning(
                    "Trading blocked by kill switch",
                    reason=state.kill_switch_reason,
                )
                return False, f"Kill switch active: {state.kill_switch_reason}"

            # Check daily loss limit if provided
            if max_daily_loss is not None:
                if state.daily_pnl < -abs(max_daily_loss):
                    reason = f"Daily loss limit exceeded: {state.daily_pnl:.2f}"
                    logger.warning(
                        "Trading blocked by daily loss limit",
                        daily_pnl=state.daily_pnl,
                        max_daily_loss=max_daily_loss,
                    )
                    return False, reason

            # Check position limit if provided
            if max_positions is not None:
                if state.total_open_positions >= max_positions:
                    reason = f"Maximum positions reached: {state.total_open_positions}"
                    logger.warning(
                        "Trading blocked by position limit",
                        total_positions=state.total_open_positions,
                        max_positions=max_positions,
                    )
                    return False, reason

            # Check exposure limit if provided
            if max_exposure is not None:
                if state.total_exposure >= max_exposure:
                    reason = f"Maximum exposure reached: {state.total_exposure:.2f}"
                    logger.warning(
                        "Trading blocked by exposure limit",
                        total_exposure=state.total_exposure,
                        max_exposure=max_exposure,
                    )
                    return False, reason

            return True, None

        except Exception as e:
            logger.error("Failed to check trading status", error=str(e))
            raise TradingError(
                message=f"Failed to check if trading is allowed: {e}",
                error_code="RISK_CHECK_FAILED",
                details={"error": str(e)},
            )

    async def activate_kill_switch(self, reason: str) -> RiskState:
        """
        Activate emergency kill switch to stop all trading.

        Args:
            reason: Reason for activating kill switch

        Returns:
            Updated RiskState

        Raises:
            TradingError: If activation fails
        """
        logger.warning(
            "Activating kill switch",
            reason=reason,
        )

        try:
            state = await self._risk_repo.update_kill_switch(
                active=True,
                reason=reason,
            )

            logger.error(
                "Kill switch activated - all trading stopped",
                reason=reason,
            )

            return state

        except Exception as e:
            logger.error("Failed to activate kill switch", error=str(e))
            raise TradingError(
                message=f"Failed to activate kill switch: {e}",
                error_code="KILL_SWITCH_ACTIVATION_FAILED",
                details={"error": str(e)},
            )

    async def deactivate_kill_switch(self) -> RiskState:
        """
        Deactivate kill switch to resume trading.

        Returns:
            Updated RiskState

        Raises:
            TradingError: If deactivation fails
        """
        logger.info("Deactivating kill switch")

        try:
            state = await self._risk_repo.update_kill_switch(active=False)

            logger.info("Kill switch deactivated - trading resumed")

            return state

        except Exception as e:
            logger.error("Failed to deactivate kill switch", error=str(e))
            raise TradingError(
                message=f"Failed to deactivate kill switch: {e}",
                error_code="KILL_SWITCH_DEACTIVATION_FAILED",
                details={"error": str(e)},
            )

    async def check_daily_loss_limit(
        self,
        max_loss: float,
        auto_activate_kill_switch: bool = True,
    ) -> bool:
        """
        Check if daily loss limit has been exceeded.

        Args:
            max_loss: Maximum allowed daily loss (positive number)
            auto_activate_kill_switch: If True, activates kill switch on breach

        Returns:
            bool: True if limit exceeded, False otherwise

        Raises:
            RiskLimitError: If limit exceeded and auto_activate_kill_switch is True
        """
        try:
            state = await self._risk_repo.get_state()

            # Check if daily loss exceeds limit
            if state.daily_pnl < -abs(max_loss):
                logger.error(
                    "Daily loss limit exceeded",
                    daily_pnl=state.daily_pnl,
                    max_loss=max_loss,
                )

                if auto_activate_kill_switch:
                    await self.activate_kill_switch(
                        reason=f"Daily loss limit exceeded: {state.daily_pnl:.2f}"
                    )
                    raise RiskLimitError(
                        message=f"Daily loss limit exceeded: {state.daily_pnl:.2f}",
                        error_code="DAILY_LOSS_LIMIT_EXCEEDED",
                        details={
                            "daily_pnl": state.daily_pnl,
                            "max_loss": max_loss,
                        },
                    )

                return True

            return False

        except RiskLimitError:
            raise
        except Exception as e:
            logger.error("Failed to check daily loss limit", error=str(e))
            raise TradingError(
                message=f"Failed to check daily loss limit: {e}",
                error_code="DAILY_LOSS_CHECK_FAILED",
                details={"error": str(e)},
            )

    async def update_daily_pnl(self, pnl: float) -> RiskState:
        """
        Add to daily P&L tracker.

        Args:
            pnl: P&L amount to add (can be positive or negative)

        Returns:
            Updated RiskState

        Raises:
            TradingError: If update fails
        """
        logger.debug(
            "Updating daily PnL",
            pnl=pnl,
        )

        try:
            state = await self._risk_repo.update_daily_pnl(
                pnl=pnl,
                increment=True,
            )

            logger.info(
                "Daily PnL updated",
                daily_pnl=state.daily_pnl,
                added_pnl=pnl,
            )

            return state

        except Exception as e:
            logger.error("Failed to update daily PnL", error=str(e))
            raise TradingError(
                message=f"Failed to update daily P&L: {e}",
                error_code="DAILY_PNL_UPDATE_FAILED",
                details={"error": str(e)},
            )

    async def get_risk_state(self) -> dict:
        """
        Get current risk state with statistics.

        Returns:
            dict with risk state including kill switch, daily stats, exposure

        Raises:
            TradingError: If retrieval fails
        """
        try:
            state = await self._risk_repo.get_state()

            # Get additional statistics
            open_count = await self._position_repo.count_open()
            total_exposure = await self._position_repo.get_total_exposure()
            unrealized_pnl = await self._position_repo.get_total_unrealized_pnl()

            return {
                "kill_switch_active": state.kill_switch_active,
                "kill_switch_reason": state.kill_switch_reason,
                "kill_switch_activated_at": state.kill_switch_activated_at,
                "daily_pnl": state.daily_pnl,
                "daily_trades": state.daily_trades,
                "daily_reset_date": state.daily_reset_date,
                "total_open_positions": open_count,
                "total_exposure": total_exposure,
                "total_unrealized_pnl": unrealized_pnl,
                "updated_at": state.updated_at,
            }

        except Exception as e:
            logger.error("Failed to get risk state", error=str(e))
            raise TradingError(
                message=f"Failed to get risk state: {e}",
                error_code="RISK_STATE_RETRIEVAL_FAILED",
                details={"error": str(e)},
            )

    async def update_exposure_tracking(self) -> RiskState:
        """
        Update exposure tracking from current positions.

        Recalculates total positions and exposure from database.

        Returns:
            Updated RiskState

        Raises:
            TradingError: If update fails
        """
        try:
            open_count = await self._position_repo.count_open()
            total_exposure = await self._position_repo.get_total_exposure()

            logger.debug(
                "Updating exposure tracking",
                open_positions=open_count,
                total_exposure=total_exposure,
            )

            state = await self._risk_repo.update_exposure(
                total_open_positions=open_count,
                total_exposure=total_exposure,
            )

            return state

        except Exception as e:
            logger.error("Failed to update exposure tracking", error=str(e))
            raise TradingError(
                message=f"Failed to update exposure tracking: {e}",
                error_code="EXPOSURE_UPDATE_FAILED",
                details={"error": str(e)},
            )

    async def check_and_enforce_limits(
        self,
        max_daily_loss: Optional[float] = None,
        max_positions: Optional[int] = None,
        max_exposure: Optional[float] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Check all risk limits and auto-activate kill switch if breached.

        This is a comprehensive check that enforces all provided limits.

        Args:
            max_daily_loss: Maximum allowed daily loss
            max_positions: Maximum allowed open positions
            max_exposure: Maximum allowed total exposure

        Returns:
            tuple of (within_limits: bool, breach_reason: Optional[str])

        Raises:
            TradingError: If check fails
        """
        try:
            # Update exposure tracking first
            await self.update_exposure_tracking()

            # Check limits using repository method
            triggered, reason = await self._risk_repo.check_and_trigger_kill_switch(
                max_daily_loss=max_daily_loss or float("inf"),
                max_open_positions=max_positions,
                max_exposure=max_exposure,
            )

            if triggered:
                logger.error(
                    "Risk limits breached - kill switch activated",
                    reason=reason,
                )
                return False, reason

            return True, None

        except Exception as e:
            logger.error("Failed to check and enforce limits", error=str(e))
            raise TradingError(
                message=f"Failed to check risk limits: {e}",
                error_code="RISK_LIMIT_CHECK_FAILED",
                details={"error": str(e)},
            )

    async def reset_daily_counters(self) -> RiskState:
        """
        Manually reset daily counters.

        Useful for testing or manual intervention.

        Returns:
            Updated RiskState

        Raises:
            TradingError: If reset fails
        """
        logger.info("Manually resetting daily counters")

        try:
            state = await self._risk_repo.reset_daily()

            logger.info("Daily counters reset", reset_date=state.daily_reset_date)

            return state

        except Exception as e:
            logger.error("Failed to reset daily counters", error=str(e))
            raise TradingError(
                message=f"Failed to reset daily counters: {e}",
                error_code="DAILY_RESET_FAILED",
                details={"error": str(e)},
            )

    async def update_risk_limits(
        self,
        max_daily_loss: Optional[float] = None,
        max_positions: Optional[int] = None,
        max_exposure: Optional[float] = None,
    ) -> dict:
        """
        Update and enforce risk limits.

        This method checks the new limits against current state
        and activates kill switch if already breached.

        Args:
            max_daily_loss: New maximum daily loss limit
            max_positions: New maximum positions limit
            max_exposure: New maximum exposure limit

        Returns:
            dict with updated limits and enforcement status

        Raises:
            TradingError: If update fails
        """
        logger.info(
            "Updating risk limits",
            max_daily_loss=max_daily_loss,
            max_positions=max_positions,
            max_exposure=max_exposure,
        )

        try:
            # Check if new limits are already breached
            within_limits, reason = await self.check_and_enforce_limits(
                max_daily_loss=max_daily_loss,
                max_positions=max_positions,
                max_exposure=max_exposure,
            )

            return {
                "max_daily_loss": max_daily_loss,
                "max_positions": max_positions,
                "max_exposure": max_exposure,
                "within_limits": within_limits,
                "breach_reason": reason,
            }

        except Exception as e:
            logger.error("Failed to update risk limits", error=str(e))
            raise TradingError(
                message=f"Failed to update risk limits: {e}",
                error_code="RISK_LIMITS_UPDATE_FAILED",
                details={"error": str(e)},
            )
