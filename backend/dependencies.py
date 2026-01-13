"""
Dependency injection container for the Good Signal application.

Provides centralized dependency management using FastAPI's
dependency injection system for clean, testable architecture.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import Settings, get_settings
from backend.core.logging import get_logger

# Re-export existing database session dependency for backwards compatibility
from backend.infrastructure.database.connection import (
    get_async_session,
    init_db,
)

logger = get_logger(__name__)


# Type alias for settings dependency
SettingsDep = Annotated[Settings, Depends(get_settings)]


class DatabaseManager:
    """
    Manages database connections and session lifecycle.

    Implements the singleton pattern for the database engine
    while providing per-request session management.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self, settings: Settings) -> None:
        """
        Initialize database engine and session factory.

        Args:
            settings: Application settings containing database URL
        """
        if self._engine is not None:
            logger.warning("Database already initialized, skipping")
            return

        # Configure engine based on database type
        engine_kwargs: dict = {
            "echo": settings.DEBUG,
            "future": True,
        }

        # SQLite-specific configuration
        if settings.is_sqlite:
            engine_kwargs["connect_args"] = {
                "check_same_thread": False,
                "timeout": 30,  # Wait up to 30 seconds for locks
            }
        else:
            # Production database settings
            engine_kwargs.update({
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "pool_pre_ping": True,
            })

        self._engine = create_async_engine(
            settings.DATABASE_URL,
            **engine_kwargs,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        logger.info(
            "Database initialized",
            database_url=settings.DATABASE_URL.split("@")[-1],  # Hide credentials
            debug_mode=settings.DEBUG,
        )

    async def close(self) -> None:
        """Close database connections and cleanup resources."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connections closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Provide a transactional scope around a series of operations.

        Yields:
            AsyncSession instance for database operations

        Raises:
            RuntimeError: If database is not initialized
        """
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @property
    def engine(self) -> AsyncEngine:
        """Get the database engine instance."""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._engine

    @property
    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._engine is not None


# Global database manager instance
db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides database sessions.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...

    Yields:
        AsyncSession instance for database operations
    """
    async with db_manager.session() as session:
        yield session


# Type alias for database session dependency
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]


class ServiceContainer:
    """
    Service container for managing application services.

    Provides lazy initialization and dependency resolution
    for application services and repositories.
    """

    def __init__(self) -> None:
        self._services: dict = {}

    def register(self, name: str, service: object) -> None:
        """Register a service in the container."""
        self._services[name] = service
        logger.debug("Service registered", service_name=name)

    def get(self, name: str) -> object:
        """Get a service from the container."""
        if name not in self._services:
            raise KeyError(f"Service '{name}' not registered")
        return self._services[name]

    def clear(self) -> None:
        """Clear all registered services."""
        self._services.clear()


# Global service container
service_container = ServiceContainer()


def get_service_container() -> ServiceContainer:
    """Get the service container instance."""
    return service_container
