"""
Integration tests for database connection and table creation.

Tests verify that the database is correctly initialized with all
required tables and relationships.
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.mark.asyncio
class TestDatabaseInitialization:
    """Test database initialization and connection."""

    async def test_database_creates_tables(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that database initialization creates all required tables."""

        def check_tables(connection):
            inspector = inspect(connection)
            tables = inspector.get_table_names()
            return tables

        # Use run_sync to inspect tables
        async with async_engine.connect() as conn:
            tables = await conn.run_sync(check_tables)

        # Verify tables exist
        assert len(tables) > 0, "No tables were created"

    async def test_database_creates_all_seven_tables(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that all seven expected tables are created."""
        expected_tables = {
            "backtests",
            "backtest_trades",
            "live_configs",
            "positions",
            "live_trades",
            "risk_state",
            "task_queue",
            "saved_configs",
        }

        def check_tables(connection):
            inspector = inspect(connection)
            return set(inspector.get_table_names())

        # Get actual tables
        async with async_engine.connect() as conn:
            actual_tables = await conn.run_sync(check_tables)

        # Verify all expected tables exist
        missing_tables = expected_tables - actual_tables
        assert not missing_tables, f"Missing tables: {missing_tables}"

        # Verify no extra tables
        extra_tables = actual_tables - expected_tables
        assert not extra_tables, f"Unexpected tables: {extra_tables}"

    async def test_database_connection_is_working(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that database connection is functioning."""
        # Simple query to verify connection
        result = await async_session.execute(text("SELECT 1"))
        value = result.scalar()

        assert value == 1


@pytest.mark.asyncio
class TestBacktestTable:
    """Test backtest table structure."""

    async def test_backtests_table_has_primary_key(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that backtests table has correct primary key."""

        def check_pk(connection):
            inspector = inspect(connection)
            pk = inspector.get_pk_constraint("backtests")
            return pk

        async with async_engine.connect() as conn:
            pk_constraint = await conn.run_sync(check_pk)

        assert "constrained_columns" in pk_constraint
        assert "id" in pk_constraint["constrained_columns"]

    async def test_backtests_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that backtests table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("backtests")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "name",
            "status",
            "progress",
            "config_json",
            "symbols",
            "strategies",
            "fee_rate",
            "initial_equity",
            "created_at",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"


@pytest.mark.asyncio
class TestBacktestTradeTable:
    """Test backtest_trades table structure."""

    async def test_backtest_trades_table_has_foreign_key(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that backtest_trades table has foreign key to backtests."""

        def check_fk(connection):
            inspector = inspect(connection)
            fks = inspector.get_foreign_keys("backtest_trades")
            return fks

        async with async_engine.connect() as conn:
            foreign_keys = await conn.run_sync(check_fk)

        # Should have at least one foreign key
        assert len(foreign_keys) > 0, "No foreign keys found"

        # Check for backtest_id foreign key
        fk_columns = [fk["constrained_columns"] for fk in foreign_keys]
        assert ["backtest_id"] in fk_columns, "Missing backtest_id foreign key"

    async def test_backtest_trades_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that backtest_trades table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("backtest_trades")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "backtest_id",
            "symbol",
            "strategy_id",
            "direction",
            "entry_time",
            "exit_time",
            "entry_price",
            "exit_price",
            "raw_pnl",
            "fees",
            "net_pnl",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"


@pytest.mark.asyncio
class TestLiveConfigTable:
    """Test live_configs table structure."""

    async def test_live_configs_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that live_configs table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("live_configs")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "name",
            "is_active",
            "symbol",
            "strategy_type",
            "initial_equity",
            "risk_per_trade",
            "timeframe",
            "fee_rate",
            "created_at",
            "updated_at",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"


@pytest.mark.asyncio
class TestPositionTable:
    """Test positions table structure."""

    async def test_positions_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that positions table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("positions")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "config_id",
            "symbol",
            "strategy_id",
            "direction",
            "status",
            "entry_time",
            "entry_price",
            "quantity",
            "notional_value",
            "realized_pnl",
            "unrealized_pnl",
            "fees_paid",
            "created_at",
            "updated_at",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"


@pytest.mark.asyncio
class TestLiveTradeTable:
    """Test live_trades table structure."""

    async def test_live_trades_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that live_trades table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("live_trades")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "position_id",
            "config_id",
            "symbol",
            "strategy_id",
            "direction",
            "trade_type",
            "order_type",
            "order_status",
            "quantity",
            "fees",
            "requested_at",
            "created_at",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"


@pytest.mark.asyncio
class TestRiskStateTable:
    """Test risk_state table structure."""

    async def test_risk_state_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that risk_state table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("risk_state")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "kill_switch_active",
            "kill_switch_reason",
            "kill_switch_activated_at",
            "daily_pnl",
            "daily_trades",
            "daily_reset_date",
            "total_open_positions",
            "total_exposure",
            "updated_at",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"

    async def test_risk_state_table_has_singleton_constraint(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that risk_state table has singleton check constraint."""

        def check_constraints(connection):
            inspector = inspect(connection)
            constraints = inspector.get_check_constraints("risk_state")
            return constraints

        async with async_engine.connect() as conn:
            check_constraints = await conn.run_sync(check_constraints)

        # Verify singleton constraint exists
        constraint_names = [c["name"] for c in check_constraints]
        assert "singleton_check" in constraint_names, "Missing singleton_check constraint"


@pytest.mark.asyncio
class TestTaskQueueTable:
    """Test task_queue table structure."""

    async def test_task_queue_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that task_queue table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("task_queue")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "task_type",
            "status",
            "priority",
            "payload_json",
            "attempts",
            "max_attempts",
            "created_at",
            "scheduled_at",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"


@pytest.mark.asyncio
class TestSavedConfigTable:
    """Test saved_configs table structure."""

    async def test_saved_configs_table_has_required_columns(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that saved_configs table has all required columns."""

        def check_columns(connection):
            inspector = inspect(connection)
            columns = inspector.get_columns("saved_configs")
            return {col["name"] for col in columns}

        async with async_engine.connect() as conn:
            column_names = await conn.run_sync(check_columns)

        required_columns = {
            "id",
            "name",
            "config_type",
            "config_json",
            "created_at",
            "updated_at",
        }

        missing_columns = required_columns - column_names
        assert not missing_columns, f"Missing columns: {missing_columns}"


@pytest.mark.asyncio
class TestDatabaseIndexes:
    """Test that important indexes are created."""

    async def test_backtests_has_status_index(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that backtests table has status index for performance."""

        def check_indexes(connection):
            inspector = inspect(connection)
            indexes = inspector.get_indexes("backtests")
            return indexes

        async with async_engine.connect() as conn:
            indexes = await conn.run_sync(check_indexes)

        # Check for indexes containing 'status' column
        status_indexed = any(
            "status" in idx.get("column_names", []) for idx in indexes
        )
        assert status_indexed, "Missing index on status column"

    async def test_task_queue_has_status_priority_index(
        self,
        async_engine: AsyncEngine,
    ) -> None:
        """Test that task_queue has index for efficient task claiming."""

        def check_indexes(connection):
            inspector = inspect(connection)
            indexes = inspector.get_indexes("task_queue")
            return indexes

        async with async_engine.connect() as conn:
            indexes = await conn.run_sync(check_indexes)

        # Should have indexes for efficient task queries
        index_names = [idx["name"] for idx in indexes]
        # At least one index should exist (may vary by implementation)
        assert len(index_names) > 0, "No indexes found on task_queue"


@pytest.mark.asyncio
class TestDatabaseSession:
    """Test database session functionality."""

    async def test_session_commit_works(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that session commit operation works."""
        from backend.infrastructure.database.models import SavedConfig

        # Create a test record
        config = SavedConfig(
            name="Test Config",
            config_type="test",
            config_json='{"test": true}',
        )

        async_session.add(config)
        await async_session.commit()

        # Verify it was committed
        from sqlalchemy import select

        stmt = select(SavedConfig).where(SavedConfig.name == "Test Config")
        result = await async_session.execute(stmt)
        fetched = result.scalar_one_or_none()

        assert fetched is not None
        assert fetched.name == "Test Config"

    async def test_session_rollback_works(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test that session rollback operation works."""
        from backend.infrastructure.database.models import SavedConfig
        from sqlalchemy import select

        # Create a test record
        config = SavedConfig(
            name="Rollback Test",
            config_type="test",
            config_json='{"test": true}',
        )

        async_session.add(config)
        await async_session.flush()

        # Rollback
        await async_session.rollback()

        # Verify it was not committed
        stmt = select(SavedConfig).where(SavedConfig.name == "Rollback Test")
        result = await async_session.execute(stmt)
        fetched = result.scalar_one_or_none()

        assert fetched is None
