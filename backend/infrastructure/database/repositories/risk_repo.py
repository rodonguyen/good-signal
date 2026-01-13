"""
Repository for RiskState entity operations.

Provides specialized methods for risk management state tracking
including kill switch control, daily P&L tracking, and exposure management.
"""

from datetime import datetime
from typing import Optional, Type

from sqlalchemy import select, update

from backend.core.exceptions import DatabaseError
from backend.infrastructure.database.models import RiskState

from .base import BaseRepository


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat()


def _today_date() -> str:
    """Get today's date in YYYY-MM-DD format."""
    return datetime.utcnow().strftime("%Y-%m-%d")


class RiskStateRepository(BaseRepository[RiskState]):
    """
    Repository for RiskState entity operations.

    RiskState is a singleton table (id=1) that maintains global
    risk management state. This repository provides methods for
    safe state access and updates.

    Example:
        >>> repo = RiskStateRepository(session)
        >>> state = await repo.get_state()  # Creates if not exists
        >>> await repo.update_kill_switch(True, "Daily loss limit reached")
    """

    # Singleton ID for the risk state record
    SINGLETON_ID = 1

    @property
    def _model(self) -> Type[RiskState]:
        return RiskState

    @property
    def _id_column_name(self) -> str:
        """RiskState uses integer id."""
        return "id"

    async def get_state(self) -> RiskState:
        """
        Get the global risk state, creating it if it doesn't exist.

        This is the primary method to access the risk state.
        It ensures a valid state always exists.

        Returns:
            RiskState: The global risk state record.

        Raises:
            DatabaseError: If state retrieval or creation fails.
        """
        try:
            # Try to get existing state
            stmt = select(RiskState).where(RiskState.id == self.SINGLETON_ID)
            result = await self._session.execute(stmt)
            state = result.scalar_one_or_none()

            if state is not None:
                # Check if daily reset is needed
                today = _today_date()
                if state.daily_reset_date != today:
                    state = await self._reset_daily_counters(state, today)
                return state

            # Create initial state
            state = RiskState(
                id=self.SINGLETON_ID,
                kill_switch_active=False,
                daily_pnl=0.0,
                daily_trades=0,
                daily_reset_date=_today_date(),
                total_open_positions=0,
                total_exposure=0.0,
                updated_at=_utc_now(),
            )

            self._session.add(state)
            await self._session.flush()
            await self._session.refresh(state)
            return state

        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get risk state: {e}",
                error_code="RISK_STATE_GET_FAILED",
                details={"error": str(e)},
            )

    async def _reset_daily_counters(
        self,
        state: RiskState,
        today: str,
    ) -> RiskState:
        """
        Reset daily counters when a new day starts.

        Args:
            state: Current risk state.
            today: Today's date string.

        Returns:
            RiskState: Updated state with reset counters.
        """
        state.daily_pnl = 0.0
        state.daily_trades = 0
        state.daily_reset_date = today
        state.updated_at = _utc_now()

        await self._session.flush()
        await self._session.refresh(state)
        return state

    async def update_kill_switch(
        self,
        active: bool,
        reason: Optional[str] = None,
    ) -> RiskState:
        """
        Update the kill switch state.

        When activated, the kill switch should prevent all new trading
        activity until manually deactivated.

        Args:
            active: Whether to activate (True) or deactivate (False) the kill switch.
            reason: Reason for activation (required when activating).

        Returns:
            RiskState: Updated risk state.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            # Get or create state first
            state = await self.get_state()

            # Update the state object directly
            state.kill_switch_active = active
            state.updated_at = _utc_now()

            if active:
                state.kill_switch_reason = reason
                state.kill_switch_activated_at = _utc_now()
            else:
                # Clear reason and activation time on deactivation
                state.kill_switch_reason = None
                state.kill_switch_activated_at = None

            await self._session.flush()
            await self._session.refresh(state)
            return state

        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update kill switch: {e}",
                error_code="RISK_KILL_SWITCH_UPDATE_FAILED",
                details={"active": active, "reason": reason, "error": str(e)},
            )

    async def update_daily_pnl(
        self,
        pnl: float,
        increment: bool = True,
    ) -> RiskState:
        """
        Update the daily P&L value.

        Args:
            pnl: P&L value to add (if increment=True) or set (if increment=False).
            increment: If True, adds to existing value. If False, sets absolute value.

        Returns:
            RiskState: Updated risk state.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            state = await self.get_state()

            if increment:
                state.daily_pnl += pnl
                state.daily_trades += 1
            else:
                state.daily_pnl = pnl

            state.updated_at = _utc_now()

            await self._session.flush()
            await self._session.refresh(state)
            return state

        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update daily PnL: {e}",
                error_code="RISK_DAILY_PNL_UPDATE_FAILED",
                details={"pnl": pnl, "increment": increment, "error": str(e)},
            )

    async def reset_daily(self, date: Optional[str] = None) -> RiskState:
        """
        Manually reset daily counters.

        Args:
            date: Date to set as reset date (defaults to today).

        Returns:
            RiskState: Updated risk state with reset counters.

        Raises:
            DatabaseError: If reset fails.
        """
        try:
            reset_date = date or _today_date()

            # Get or create state first
            state = await self.get_state()

            # Update the state object directly to preserve the custom date
            state.daily_pnl = 0.0
            state.daily_trades = 0
            state.daily_reset_date = reset_date
            state.updated_at = _utc_now()

            await self._session.flush()
            await self._session.refresh(state)
            return state

        except Exception as e:
            raise DatabaseError(
                message=f"Failed to reset daily counters: {e}",
                error_code="RISK_DAILY_RESET_FAILED",
                details={"date": date, "error": str(e)},
            )

    async def update_exposure(
        self,
        total_open_positions: int,
        total_exposure: float,
    ) -> RiskState:
        """
        Update exposure tracking values.

        Args:
            total_open_positions: Current count of open positions.
            total_exposure: Total notional exposure across positions.

        Returns:
            RiskState: Updated risk state.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            # Get or create state first
            state = await self.get_state()

            # Update the state object directly
            state.total_open_positions = total_open_positions
            state.total_exposure = total_exposure
            state.updated_at = _utc_now()

            await self._session.flush()
            await self._session.refresh(state)
            return state

        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update exposure: {e}",
                error_code="RISK_EXPOSURE_UPDATE_FAILED",
                details={
                    "total_open_positions": total_open_positions,
                    "total_exposure": total_exposure,
                    "error": str(e),
                },
            )

    async def is_kill_switch_active(self) -> bool:
        """
        Check if the kill switch is currently active.

        Returns:
            bool: True if kill switch is active.

        Raises:
            DatabaseError: If check fails.
        """
        try:
            state = await self.get_state()
            return state.kill_switch_active
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to check kill switch: {e}",
                error_code="RISK_KILL_SWITCH_CHECK_FAILED",
                details={"error": str(e)},
            )

    async def get_daily_stats(self) -> dict:
        """
        Get current daily trading statistics.

        Returns:
            dict: Daily stats including pnl, trades, and reset date.

        Raises:
            DatabaseError: If retrieval fails.
        """
        try:
            state = await self.get_state()
            return {
                "daily_pnl": state.daily_pnl,
                "daily_trades": state.daily_trades,
                "daily_reset_date": state.daily_reset_date,
                "kill_switch_active": state.kill_switch_active,
                "kill_switch_reason": state.kill_switch_reason,
                "total_open_positions": state.total_open_positions,
                "total_exposure": state.total_exposure,
                "updated_at": state.updated_at,
            }
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get daily stats: {e}",
                error_code="RISK_DAILY_STATS_FAILED",
                details={"error": str(e)},
            )

    async def increment_trade_count(self) -> RiskState:
        """
        Increment the daily trade counter.

        Returns:
            RiskState: Updated risk state.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            state = await self.get_state()
            state.daily_trades += 1
            state.updated_at = _utc_now()

            await self._session.flush()
            await self._session.refresh(state)
            return state

        except Exception as e:
            raise DatabaseError(
                message=f"Failed to increment trade count: {e}",
                error_code="RISK_TRADE_COUNT_FAILED",
                details={"error": str(e)},
            )

    async def check_and_trigger_kill_switch(
        self,
        max_daily_loss: float,
        max_open_positions: Optional[int] = None,
        max_exposure: Optional[float] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Check risk limits and trigger kill switch if exceeded.

        Args:
            max_daily_loss: Maximum allowed daily loss (positive number).
            max_open_positions: Optional maximum open positions.
            max_exposure: Optional maximum total exposure.

        Returns:
            tuple[bool, Optional[str]]: (triggered, reason) - whether kill switch
                was triggered and the reason if so.

        Raises:
            DatabaseError: If check or update fails.
        """
        try:
            state = await self.get_state()

            # Already active
            if state.kill_switch_active:
                return True, state.kill_switch_reason

            # Check daily loss limit
            if state.daily_pnl < -abs(max_daily_loss):
                reason = f"Daily loss limit exceeded: {state.daily_pnl:.2f}"
                await self.update_kill_switch(True, reason)
                return True, reason

            # Check position limit
            if max_open_positions and state.total_open_positions > max_open_positions:
                reason = f"Max positions exceeded: {state.total_open_positions}"
                await self.update_kill_switch(True, reason)
                return True, reason

            # Check exposure limit
            if max_exposure and state.total_exposure > max_exposure:
                reason = f"Max exposure exceeded: {state.total_exposure:.2f}"
                await self.update_kill_switch(True, reason)
                return True, reason

            return False, None

        except Exception as e:
            raise DatabaseError(
                message=f"Failed to check risk limits: {e}",
                error_code="RISK_LIMIT_CHECK_FAILED",
                details={"error": str(e)},
            )
