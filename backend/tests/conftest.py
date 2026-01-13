"""
Pytest configuration and fixtures for good-signal backend tests.

Provides reusable test fixtures for database sessions, test clients,
and test configuration management.
"""

import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import Settings
from backend.infrastructure.database.models import Base, Backtest, BacktestTrade


@pytest.fixture(scope="session")
def test_db_path() -> str:
    """
    Create a temporary SQLite database path for testing.

    Returns:
        str: Path to temporary test database file.
    """
    # Create a temporary directory for the test database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_good_signal.db")
    return db_path


@pytest.fixture(scope="session")
def test_settings(test_db_path: str) -> Settings:
    """
    Create test settings with test database configuration.

    Args:
        test_db_path: Path to test database file.

    Returns:
        Settings: Test configuration with test database URL.
    """
    # Override environment variables for testing
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{test_db_path}"
    os.environ["DEBUG"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"

    # Create settings instance
    settings = Settings(
        DATABASE_URL=f"sqlite+aiosqlite:///{test_db_path}",
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        MAX_BACKTEST_WORKERS=2,
    )

    return settings


@pytest_asyncio.fixture(scope="function")
async def async_engine(test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """
    Create an async database engine for testing.

    Args:
        test_settings: Test configuration settings.

    Yields:
        AsyncEngine: SQLAlchemy async engine for testing.
    """
    engine = create_async_engine(
        test_settings.DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """
    Create a session factory for testing.

    Args:
        async_engine: Async database engine.

    Returns:
        async_sessionmaker: Session factory for creating test sessions.
    """
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(scope="function")
async def async_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session for testing.

    Each test gets a fresh session with automatic rollback.

    Args:
        session_factory: Session factory for creating sessions.

    Yields:
        AsyncSession: Database session for testing.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(scope="function")
async def clean_db(async_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean database session that's reset after each test.

    This fixture ensures complete isolation between tests by
    truncating all tables after each test run.

    Args:
        async_session: Database session.

    Yields:
        AsyncSession: Clean database session for testing.
    """
    yield async_session

    # Clean up all tables after test
    await async_session.rollback()

    # Truncate all tables (order matters due to foreign keys)
    from backend.infrastructure.database.models import (
        BacktestTrade,
        Backtest,
        LiveTrade,
        Position,
        LiveConfig,
        TaskQueue,
        RiskState,
        SavedConfig,
    )

    for model in [
        BacktestTrade,
        LiveTrade,
        Position,
        Backtest,
        LiveConfig,
        TaskQueue,
        RiskState,
        SavedConfig,
    ]:
        await async_session.execute(model.__table__.delete())

    await async_session.commit()


@pytest_asyncio.fixture(scope="function")
async def test_client(
    test_settings: Settings,
    async_engine: AsyncEngine,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP test client for API testing.

    Creates a test client with the FastAPI app and test database.

    Args:
        test_settings: Test configuration settings.
        async_engine: Test database engine.

    Yields:
        AsyncClient: HTTP client for testing API endpoints.
    """
    # Import here to avoid circular dependencies
    from backend.main import create_app
    from backend.dependencies import db_manager

    # Initialize database manager with test settings
    await db_manager.initialize(test_settings)

    # Create FastAPI app
    app = create_app(settings=test_settings)

    # Create test client
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    # Clean up
    await db_manager.close()


# Helper fixtures for common test data


@pytest.fixture
def sample_task_payload() -> dict[str, Any]:
    """
    Provide sample task payload for testing.

    Returns:
        dict: Sample task payload data.
    """
    return {
        "config_id": "test-config-123",
        "symbol": "BTCUSDT",
        "strategy": "supertrend",
        "timeframe": "1h",
    }


@pytest.fixture
def sample_backtest_config() -> dict[str, Any]:
    """
    Provide sample backtest configuration for testing.

    Returns:
        dict: Sample backtest configuration.
    """
    return {
        "name": "Test Backtest",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "strategies": ["supertrend"],
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "initial_equity": 10000.0,
        "fee_rate": 0.001,
        "risk_per_trade": 0.02,
    }


@pytest.fixture
def sample_live_config() -> dict[str, Any]:
    """
    Provide sample live trading configuration for testing.

    Returns:
        dict: Sample live trading configuration.
    """
    return {
        "name": "Test Live Config",
        "symbol": "BTCUSDT",
        "strategy_type": "supertrend",
        "initial_equity": 10000.0,
        "risk_per_trade": 0.02,
        "timeframe": "1h",
        "fee_rate": 0.001,
        "max_daily_loss": 500.0,
        "max_open_positions": 3,
    }


# Backtest-specific fixtures


@pytest.fixture
def sample_backtest_request() -> dict[str, Any]:
    """
    Provide sample backtest request payload for testing.

    Returns:
        dict: Sample backtest request data.
    """
    return {
        "name": "Test Backtest",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "strategies": [
            {
                "type": "supertrend",
                "enabled": True,
                "signal_timeframe": "4h",
                "params": {
                    "atr_period": 10,
                    "atr_multiplier": 3.0,
                },
            }
        ],
        "filters": [
            {
                "type": "low_volatility_pct",
                "enabled": True,
                "params": {
                    "percentile": 0.25,
                },
            }
        ],
        "fee_rate": 0.0015,
        "initial_equity": 10000.0,
        "risk_per_trade": 0.02,
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    }


@pytest_asyncio.fixture
async def sample_backtest_record(
    clean_db: AsyncSession,
) -> Backtest:
    """
    Create a sample backtest record in the database.

    Args:
        clean_db: Clean database session.

    Returns:
        Backtest: Created backtest record with pending status.
    """
    import json
    from backend.infrastructure.database.models import Backtest, utc_now

    backtest = Backtest(
        name="Test Backtest",
        status="pending",
        progress=0.0,
        config_json=json.dumps({
            "version": 1,
            "engine": {"fee_rate": 0.0015},
            "universe": {"symbols": ["BTCUSDT", "ETHUSDT"]},
            "strategies": [{"id": "supertrend", "type": "supertrend"}],
        }),
        symbols=json.dumps(["BTCUSDT", "ETHUSDT"]),
        strategies=json.dumps([{"type": "supertrend", "enabled": True}]),
        fee_rate=0.0015,
        initial_equity=10000.0,
        risk_per_trade=0.02,
        start_date="2024-01-01",
        end_date="2024-01-31",
        created_at=utc_now(),
    )

    clean_db.add(backtest)
    await clean_db.commit()
    await clean_db.refresh(backtest)

    return backtest


@pytest_asyncio.fixture
async def completed_backtest_record(
    clean_db: AsyncSession,
) -> Backtest:
    """
    Create a completed backtest record with performance metrics.

    Args:
        clean_db: Clean database session.

    Returns:
        Backtest: Created backtest record with completed status and metrics.
    """
    import json
    from backend.infrastructure.database.models import Backtest, utc_now

    backtest = Backtest(
        name="Completed Test Backtest",
        status="completed",
        progress=1.0,
        config_json=json.dumps({
            "version": 1,
            "engine": {"fee_rate": 0.0015},
            "universe": {"symbols": ["BTCUSDT"]},
            "strategies": [{"id": "supertrend", "type": "supertrend"}],
        }),
        symbols=json.dumps(["BTCUSDT"]),
        strategies=json.dumps([{"type": "supertrend", "enabled": True}]),
        fee_rate=0.0015,
        initial_equity=10000.0,
        risk_per_trade=0.02,
        start_date="2024-01-01",
        end_date="2024-01-31",
        created_at=utc_now(),
        completed_at=utc_now(),
        total_return=15.5,
        sharpe_ratio=1.8,
        max_drawdown=-8.5,
        win_rate=0.65,
        profit_factor=2.3,
        total_trades=25,
    )

    clean_db.add(backtest)
    await clean_db.commit()
    await clean_db.refresh(backtest)

    return backtest


@pytest_asyncio.fixture
async def running_backtest_record(
    clean_db: AsyncSession,
) -> Backtest:
    """
    Create a running backtest record.

    Args:
        clean_db: Clean database session.

    Returns:
        Backtest: Created backtest record with running status.
    """
    import json
    from backend.infrastructure.database.models import Backtest, utc_now

    backtest = Backtest(
        name="Running Test Backtest",
        status="running",
        progress=0.45,
        config_json=json.dumps({
            "version": 1,
            "engine": {"fee_rate": 0.0015},
            "universe": {"symbols": ["ETHUSDT"]},
            "strategies": [{"id": "supertrend", "type": "supertrend"}],
        }),
        symbols=json.dumps(["ETHUSDT"]),
        strategies=json.dumps([{"type": "supertrend", "enabled": True}]),
        fee_rate=0.0015,
        initial_equity=10000.0,
        risk_per_trade=0.02,
        start_date="2024-01-01",
        end_date="2024-01-31",
        created_at=utc_now(),
        started_at=utc_now(),
    )

    clean_db.add(backtest)
    await clean_db.commit()
    await clean_db.refresh(backtest)

    return backtest


@pytest_asyncio.fixture
async def failed_backtest_record(
    clean_db: AsyncSession,
) -> Backtest:
    """
    Create a failed backtest record with error message.

    Args:
        clean_db: Clean database session.

    Returns:
        Backtest: Created backtest record with failed status.
    """
    import json
    from backend.infrastructure.database.models import Backtest, utc_now

    backtest = Backtest(
        name="Failed Test Backtest",
        status="failed",
        progress=0.0,
        config_json=json.dumps({
            "version": 1,
            "engine": {"fee_rate": 0.0015},
            "universe": {"symbols": ["INVALID"]},
            "strategies": [{"id": "supertrend", "type": "supertrend"}],
        }),
        symbols=json.dumps(["INVALID"]),
        strategies=json.dumps([{"type": "supertrend", "enabled": True}]),
        fee_rate=0.0015,
        initial_equity=10000.0,
        risk_per_trade=0.02,
        start_date="2024-01-01",
        end_date="2024-01-31",
        created_at=utc_now(),
        completed_at=utc_now(),
        error_message="Data not found for symbol INVALID",
    )

    clean_db.add(backtest)
    await clean_db.commit()
    await clean_db.refresh(backtest)

    return backtest


@pytest_asyncio.fixture
async def multiple_backtest_records(
    clean_db: AsyncSession,
) -> list[Backtest]:
    """
    Create multiple backtest records with different statuses.

    Args:
        clean_db: Clean database session.

    Returns:
        list[Backtest]: List of created backtest records.
    """
    import json
    from backend.infrastructure.database.models import Backtest, utc_now
    from datetime import datetime, timedelta

    base_time = datetime.utcnow()
    backtests = []

    # Create backtests with different statuses and timestamps
    statuses = ["pending", "running", "completed", "failed", "completed"]
    for i, status in enumerate(statuses):
        backtest = Backtest(
            name=f"Test Backtest {i+1}",
            status=status,
            progress=1.0 if status == "completed" else 0.0,
            config_json=json.dumps({
                "version": 1,
                "engine": {"fee_rate": 0.0015},
                "universe": {"symbols": ["BTCUSDT"]},
                "strategies": [{"id": "supertrend", "type": "supertrend"}],
            }),
            symbols=json.dumps(["BTCUSDT"]),
            strategies=json.dumps([{"type": "supertrend", "enabled": True}]),
            fee_rate=0.0015,
            initial_equity=10000.0,
            risk_per_trade=0.02,
            start_date="2024-01-01",
            end_date="2024-01-31",
            created_at=(base_time - timedelta(hours=i)).isoformat(),
            total_return=10.0 + i if status == "completed" else None,
            total_trades=20 + i if status == "completed" else None,
        )
        clean_db.add(backtest)
        backtests.append(backtest)

    await clean_db.commit()

    # Refresh all backtests
    for backtest in backtests:
        await clean_db.refresh(backtest)

    return backtests


@pytest_asyncio.fixture
async def backtest_with_trades(
    clean_db: AsyncSession,
) -> tuple[Backtest, list[BacktestTrade]]:
    """
    Create a backtest record with associated trades.

    Args:
        clean_db: Clean database session.

    Returns:
        tuple[Backtest, list[BacktestTrade]]: Backtest and its trades.
    """
    import json
    from backend.infrastructure.database.models import Backtest, BacktestTrade, utc_now
    from datetime import datetime, timedelta

    # Create backtest
    backtest = Backtest(
        name="Backtest with Trades",
        status="pending",
        progress=0.0,
        config_json=json.dumps({
            "version": 1,
            "engine": {"fee_rate": 0.0015},
            "universe": {"symbols": ["BTCUSDT"]},
            "strategies": [{"id": "supertrend", "type": "supertrend"}],
        }),
        symbols=json.dumps(["BTCUSDT"]),
        strategies=json.dumps([{"type": "supertrend", "enabled": True}]),
        fee_rate=0.0015,
        initial_equity=10000.0,
        risk_per_trade=0.02,
        start_date="2024-01-01",
        end_date="2024-01-31",
        created_at=utc_now(),
    )

    clean_db.add(backtest)
    await clean_db.commit()
    await clean_db.refresh(backtest)

    # Create sample trades
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    trades = []

    for i in range(10):
        entry_time = base_time + timedelta(hours=i * 6)
        exit_time = entry_time + timedelta(hours=4)

        trade = BacktestTrade(
            backtest_id=backtest.id,
            symbol="BTCUSDT",
            strategy_id="supertrend",
            direction="long" if i % 2 == 0 else "short",
            entry_time=entry_time.isoformat(),
            exit_time=exit_time.isoformat(),
            entry_price=40000.0 + (i * 100),
            exit_price=40100.0 + (i * 100) if i % 3 != 0 else 39900.0 + (i * 100),
            stop_level=39500.0 + (i * 100),
            tp_level=40500.0 + (i * 100),
            raw_pnl=100.0 if i % 3 != 0 else -100.0,
            fees=15.0,
            net_pnl=85.0 if i % 3 != 0 else -115.0,
            portfolio_pnl=0.85 if i % 3 != 0 else -1.15,
            position_size=1.0,
            exit_reason="take_profit" if i % 3 != 0 else "stop_loss",
            created_at=utc_now(),
        )
        clean_db.add(trade)
        trades.append(trade)

    await clean_db.commit()

    # Refresh all trades
    for trade in trades:
        await clean_db.refresh(trade)

    return backtest, trades
