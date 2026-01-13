"""
Unit tests for RiskStateRepository - Risk management state tracking.

Tests cover risk state CRUD operations, kill switch functionality,
daily P&L tracking, exposure management, and automatic daily resets.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import DatabaseError
from backend.infrastructure.database.models import RiskState
from backend.infrastructure.database.repositories.risk_repo import RiskStateRepository


def _today_date() -> str:
    """Get today's date in YYYY-MM-DD format."""
    return datetime.utcnow().strftime("%Y-%m-%d")


def _yesterday_date() -> str:
    """Get yesterday's date in YYYY-MM-DD format."""
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
class TestRiskStateGetState:
    """Test risk state retrieval and initialization."""

    async def test_get_state_creates_if_not_exists(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that get_state creates initial state if it doesn't exist."""
        repo = RiskStateRepository(session=async_session)

        # Get state (should create it)
        state = await repo.get_state()

        assert state is not None
        assert state.id == RiskStateRepository.SINGLETON_ID
        assert state.kill_switch_active is False
        assert state.daily_pnl == 0.0
        assert state.daily_trades == 0
        assert state.total_open_positions == 0
        assert state.total_exposure == 0.0
        assert state.daily_reset_date == _today_date()

    async def test_get_state_returns_existing_state(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that get_state returns existing state if it exists."""
        repo = RiskStateRepository(session=async_session)

        # Create initial state
        first_state = await repo.get_state()

        # Update some values
        first_state.daily_pnl = 100.0
        first_state.daily_trades = 5
        await async_session.commit()

        # Get state again
        second_state = await repo.get_state()

        assert second_state.id == first_state.id
        assert second_state.daily_pnl == 100.0
        assert second_state.daily_trades == 5

    async def test_get_state_auto_resets_daily_counters_on_new_day(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that get_state automatically resets counters on a new day."""
        repo = RiskStateRepository(session=async_session)

        # Create state with yesterday's date
        state = await repo.get_state()
        state.daily_pnl = 500.0
        state.daily_trades = 10
        state.daily_reset_date = _yesterday_date()
        await async_session.commit()

        # Get state on "new day"
        refreshed_state = await repo.get_state()

        assert refreshed_state.daily_pnl == 0.0
        assert refreshed_state.daily_trades == 0
        assert refreshed_state.daily_reset_date == _today_date()


@pytest.mark.asyncio
class TestRiskStateKillSwitch:
    """Test kill switch functionality."""

    async def test_update_kill_switch_active(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test activating the kill switch with a reason."""
        repo = RiskStateRepository(session=async_session)

        # Activate kill switch
        reason = "Daily loss limit exceeded"
        state = await repo.update_kill_switch(active=True, reason=reason)

        assert state.kill_switch_active is True
        assert state.kill_switch_reason == reason
        assert state.kill_switch_activated_at is not None

        # Verify in database
        stmt = select(RiskState).where(RiskState.id == RiskStateRepository.SINGLETON_ID)
        result = await async_session.execute(stmt)
        db_state = result.scalar_one()

        assert db_state.kill_switch_active is True
        assert db_state.kill_switch_reason == reason

    async def test_update_kill_switch_inactive(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test deactivating the kill switch clears reason and activation time."""
        repo = RiskStateRepository(session=async_session)

        # First activate it
        await repo.update_kill_switch(active=True, reason="Test reason")

        # Then deactivate it
        state = await repo.update_kill_switch(active=False)

        assert state.kill_switch_active is False
        assert state.kill_switch_reason is None
        assert state.kill_switch_activated_at is None

        # Verify in database
        stmt = select(RiskState).where(RiskState.id == RiskStateRepository.SINGLETON_ID)
        result = await async_session.execute(stmt)
        db_state = result.scalar_one()

        assert db_state.kill_switch_active is False
        assert db_state.kill_switch_reason is None

    async def test_is_kill_switch_active(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test checking if kill switch is active."""
        repo = RiskStateRepository(session=async_session)

        # Initially should be False
        is_active = await repo.is_kill_switch_active()
        assert is_active is False

        # Activate kill switch
        await repo.update_kill_switch(active=True, reason="Test")

        # Should now be True
        is_active = await repo.is_kill_switch_active()
        assert is_active is True

        # Deactivate
        await repo.update_kill_switch(active=False)

        # Should be False again
        is_active = await repo.is_kill_switch_active()
        assert is_active is False


@pytest.mark.asyncio
class TestRiskStateDailyPnL:
    """Test daily P&L tracking functionality."""

    async def test_update_daily_pnl_increment(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test incrementing daily P&L and trade count."""
        repo = RiskStateRepository(session=async_session)

        # Initialize state
        await repo.get_state()

        # Add some profit
        state = await repo.update_daily_pnl(pnl=100.0, increment=True)

        assert state.daily_pnl == 100.0
        assert state.daily_trades == 1

        # Add more profit
        state = await repo.update_daily_pnl(pnl=50.0, increment=True)

        assert state.daily_pnl == 150.0
        assert state.daily_trades == 2

    async def test_update_daily_pnl_set_absolute(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test setting absolute daily P&L value."""
        repo = RiskStateRepository(session=async_session)

        # Initialize state with some P&L
        await repo.get_state()
        await repo.update_daily_pnl(pnl=100.0, increment=True)

        # Set absolute value (doesn't increment trade count)
        state = await repo.update_daily_pnl(pnl=250.0, increment=False)

        assert state.daily_pnl == 250.0
        assert state.daily_trades == 1  # Not incremented

    async def test_update_daily_pnl_handles_losses(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that negative P&L (losses) are tracked correctly."""
        repo = RiskStateRepository(session=async_session)

        await repo.get_state()

        # Add loss
        state = await repo.update_daily_pnl(pnl=-50.0, increment=True)

        assert state.daily_pnl == -50.0
        assert state.daily_trades == 1

        # Add more loss
        state = await repo.update_daily_pnl(pnl=-30.0, increment=True)

        assert state.daily_pnl == -80.0
        assert state.daily_trades == 2

    async def test_update_daily_pnl_mixed_wins_losses(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test tracking mixed wins and losses."""
        repo = RiskStateRepository(session=async_session)

        await repo.get_state()

        # Win
        await repo.update_daily_pnl(pnl=100.0, increment=True)
        # Loss
        await repo.update_daily_pnl(pnl=-30.0, increment=True)
        # Win
        state = await repo.update_daily_pnl(pnl=50.0, increment=True)

        assert state.daily_pnl == 120.0
        assert state.daily_trades == 3


@pytest.mark.asyncio
class TestRiskStateResetDaily:
    """Test daily counter reset functionality."""

    async def test_reset_daily(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test manually resetting daily counters."""
        repo = RiskStateRepository(session=async_session)

        # Set up some daily data
        await repo.get_state()
        await repo.update_daily_pnl(pnl=150.0, increment=True)
        await repo.update_daily_pnl(pnl=50.0, increment=True)

        # Reset
        state = await repo.reset_daily()

        assert state.daily_pnl == 0.0
        assert state.daily_trades == 0
        assert state.daily_reset_date == _today_date()

    async def test_reset_daily_with_custom_date(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test resetting daily counters with a custom date."""
        repo = RiskStateRepository(session=async_session)

        await repo.get_state()
        await repo.update_daily_pnl(pnl=100.0, increment=True)

        # Reset with custom date
        custom_date = "2024-06-15"
        state = await repo.reset_daily(date=custom_date)

        assert state.daily_pnl == 0.0
        assert state.daily_trades == 0
        assert state.daily_reset_date == custom_date

    async def test_reset_daily_preserves_other_fields(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that resetting daily counters doesn't affect other fields."""
        repo = RiskStateRepository(session=async_session)

        # Set up state with various values
        await repo.get_state()
        await repo.update_kill_switch(active=True, reason="Test")
        await repo.update_exposure(total_open_positions=5, total_exposure=10000.0)
        await repo.update_daily_pnl(pnl=200.0, increment=True)

        # Reset daily
        state = await repo.reset_daily()

        # Daily counters reset
        assert state.daily_pnl == 0.0
        assert state.daily_trades == 0

        # Other fields preserved
        assert state.kill_switch_active is True
        assert state.kill_switch_reason == "Test"
        assert state.total_open_positions == 5
        assert state.total_exposure == 10000.0


@pytest.mark.asyncio
class TestRiskStateExposure:
    """Test exposure tracking functionality."""

    async def test_update_exposure(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test updating exposure tracking values."""
        repo = RiskStateRepository(session=async_session)

        # Initialize and update exposure
        state = await repo.update_exposure(
            total_open_positions=3,
            total_exposure=15000.0,
        )

        assert state.total_open_positions == 3
        assert state.total_exposure == 15000.0

    async def test_update_exposure_multiple_times(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test updating exposure multiple times."""
        repo = RiskStateRepository(session=async_session)

        # First update
        await repo.update_exposure(
            total_open_positions=2,
            total_exposure=10000.0,
        )

        # Second update
        state = await repo.update_exposure(
            total_open_positions=5,
            total_exposure=25000.0,
        )

        assert state.total_open_positions == 5
        assert state.total_exposure == 25000.0


@pytest.mark.asyncio
class TestRiskStateHelperMethods:
    """Test helper and utility methods."""

    async def test_get_daily_stats(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test retrieving daily statistics."""
        repo = RiskStateRepository(session=async_session)

        # Set up state
        await repo.get_state()
        await repo.update_daily_pnl(pnl=150.0, increment=True)
        await repo.update_daily_pnl(pnl=-30.0, increment=True)
        await repo.update_exposure(
            total_open_positions=3,
            total_exposure=12000.0,
        )

        # Get stats
        stats = await repo.get_daily_stats()

        assert stats["daily_pnl"] == 120.0
        assert stats["daily_trades"] == 2
        assert stats["daily_reset_date"] == _today_date()
        assert stats["kill_switch_active"] is False
        assert stats["kill_switch_reason"] is None
        assert stats["total_open_positions"] == 3
        assert stats["total_exposure"] == 12000.0
        assert "updated_at" in stats

    async def test_increment_trade_count(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test incrementing trade counter independently."""
        repo = RiskStateRepository(session=async_session)

        await repo.get_state()

        # Increment trade count
        state = await repo.increment_trade_count()
        assert state.daily_trades == 1

        # Increment again
        state = await repo.increment_trade_count()
        assert state.daily_trades == 2

        # P&L should not be affected
        assert state.daily_pnl == 0.0


@pytest.mark.asyncio
class TestRiskStateCheckAndTriggerKillSwitch:
    """Test automatic kill switch triggering based on risk limits."""

    async def test_check_and_trigger_kill_switch_on_daily_loss(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that kill switch triggers on daily loss limit."""
        repo = RiskStateRepository(session=async_session)

        # Set up state with large loss
        await repo.get_state()
        await repo.update_daily_pnl(pnl=-600.0, increment=True)

        # Check limits (max loss is 500)
        triggered, reason = await repo.check_and_trigger_kill_switch(
            max_daily_loss=500.0
        )

        assert triggered is True
        assert "Daily loss limit exceeded" in reason
        assert "-600.00" in reason

        # Verify kill switch is active
        state = await repo.get_state()
        assert state.kill_switch_active is True

    async def test_check_and_trigger_kill_switch_on_max_positions(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that kill switch triggers on max positions limit."""
        repo = RiskStateRepository(session=async_session)

        # Set up state with too many positions
        await repo.get_state()
        await repo.update_exposure(
            total_open_positions=6,
            total_exposure=30000.0,
        )

        # Check limits (max positions is 5)
        triggered, reason = await repo.check_and_trigger_kill_switch(
            max_daily_loss=1000.0,
            max_open_positions=5,
        )

        assert triggered is True
        assert "Max positions exceeded" in reason
        assert "6" in reason

        # Verify kill switch is active
        state = await repo.get_state()
        assert state.kill_switch_active is True

    async def test_check_and_trigger_kill_switch_on_max_exposure(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that kill switch triggers on max exposure limit."""
        repo = RiskStateRepository(session=async_session)

        # Set up state with too much exposure
        await repo.get_state()
        await repo.update_exposure(
            total_open_positions=3,
            total_exposure=60000.0,
        )

        # Check limits (max exposure is 50000)
        triggered, reason = await repo.check_and_trigger_kill_switch(
            max_daily_loss=1000.0,
            max_exposure=50000.0,
        )

        assert triggered is True
        assert "Max exposure exceeded" in reason
        assert "60000.00" in reason

        # Verify kill switch is active
        state = await repo.get_state()
        assert state.kill_switch_active is True

    async def test_check_and_trigger_kill_switch_within_limits(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that kill switch doesn't trigger when within limits."""
        repo = RiskStateRepository(session=async_session)

        # Set up state within limits
        await repo.get_state()
        await repo.update_daily_pnl(pnl=-200.0, increment=True)
        await repo.update_exposure(
            total_open_positions=3,
            total_exposure=20000.0,
        )

        # Check limits
        triggered, reason = await repo.check_and_trigger_kill_switch(
            max_daily_loss=500.0,
            max_open_positions=5,
            max_exposure=50000.0,
        )

        assert triggered is False
        assert reason is None

        # Verify kill switch is not active
        state = await repo.get_state()
        assert state.kill_switch_active is False

    async def test_check_and_trigger_kill_switch_already_active(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that check returns True if kill switch is already active."""
        repo = RiskStateRepository(session=async_session)

        # Activate kill switch manually
        await repo.get_state()
        await repo.update_kill_switch(active=True, reason="Manual activation")

        # Check limits
        triggered, reason = await repo.check_and_trigger_kill_switch(
            max_daily_loss=500.0
        )

        assert triggered is True
        assert reason == "Manual activation"

    async def test_check_and_trigger_kill_switch_positive_pnl_not_triggered(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that positive P&L doesn't trigger kill switch."""
        repo = RiskStateRepository(session=async_session)

        # Set up state with profit
        await repo.get_state()
        await repo.update_daily_pnl(pnl=300.0, increment=True)

        # Check limits
        triggered, reason = await repo.check_and_trigger_kill_switch(
            max_daily_loss=500.0
        )

        assert triggered is False
        assert reason is None

        # Verify kill switch is not active
        state = await repo.get_state()
        assert state.kill_switch_active is False
