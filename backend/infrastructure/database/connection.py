"""Database connection and session management."""

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Default database URL - SQLite with aiosqlite driver
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data/db/good_signal.db"
)

# SQLite connection arguments with timeout for concurrent access
_sqlite_connect_args = {
    "check_same_thread": False,
    "timeout": 30,  # Wait up to 30 seconds for locks
}

# Create async engine
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    poolclass=NullPool,  # SQLite doesn't benefit from connection pooling
    connect_args=_sqlite_connect_args if "sqlite" in DATABASE_URL else {},
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async session dependency for FastAPI.

    Usage:
        @app.get("/endpoint")
        async def endpoint(session: AsyncSession = Depends(get_async_session)):
            ...

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database - create all tables.

    This function should be called on application startup.
    It will create the database file and all tables if they don't exist.
    """
    from sqlalchemy import text
    from .models import Base

    # Ensure the database directory exists
    if "sqlite" in DATABASE_URL:
        db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    # Create all tables and enable WAL mode for better concurrent performance
    async with engine.begin() as conn:
        # Enable WAL mode for SQLite (better concurrent reads/writes)
        if "sqlite" in DATABASE_URL:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))
        await conn.run_sync(Base.metadata.create_all)

    print(f"Database initialized at: {DATABASE_URL}")
