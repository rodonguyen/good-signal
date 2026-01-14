"""
Repositories for configuration entities.

Provides repository classes for LiveConfig and SavedConfig entities
with specialized query methods for configuration management.
"""

import json
from datetime import datetime
from typing import Optional, Type

from sqlalchemy import select, update, desc

from backend.core.exceptions import NotFoundError, DatabaseError
from backend.infrastructure.database.models import LiveConfig, SavedConfig

from .base import BaseRepository


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


class LiveConfigRepository(BaseRepository[LiveConfig]):
    """
    Repository for LiveConfig entity operations.

    Provides methods for managing live trading configurations
    including activation, deactivation, and symbol-based queries.

    Example:
        >>> repo = LiveConfigRepository(session)
        >>> active_configs = await repo.get_active()
        >>> await repo.activate(config_id)
    """

    @property
    def _model(self) -> Type[LiveConfig]:
        return LiveConfig

    async def get_active(self) -> list[LiveConfig]:
        """
        Get all active live trading configurations.

        Returns:
            list[LiveConfig]: All configurations where is_active is True.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveConfig)
                .where(LiveConfig.is_active == True)  # noqa: E712
                .order_by(LiveConfig.name)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get active live configs: {e}",
                error_code="LIVE_CONFIG_ACTIVE_QUERY_FAILED",
                details={"error": str(e)},
            )

    async def get_by_symbol(self, symbol: str) -> list[LiveConfig]:
        """
        Get configurations for a specific symbol.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT").

        Returns:
            list[LiveConfig]: Configurations for the symbol.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveConfig)
                .where(LiveConfig.symbol == symbol)
                .order_by(desc(LiveConfig.created_at))
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get live configs by symbol: {e}",
                error_code="LIVE_CONFIG_SYMBOL_QUERY_FAILED",
                details={"symbol": symbol, "error": str(e)},
            )

    async def get_active_by_symbol(self, symbol: str) -> Optional[LiveConfig]:
        """
        Get the active configuration for a specific symbol.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT").

        Returns:
            Optional[LiveConfig]: Active configuration for the symbol if exists.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(LiveConfig)
                .where(
                    LiveConfig.symbol == symbol,
                    LiveConfig.is_active == True,  # noqa: E712
                )
                .limit(1)
            )
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get active live config by symbol: {e}",
                error_code="LIVE_CONFIG_ACTIVE_SYMBOL_QUERY_FAILED",
                details={"symbol": symbol, "error": str(e)},
            )

    async def activate(self, id: str) -> None:
        """
        Activate a live trading configuration.

        Args:
            id: Configuration ID.

        Raises:
            NotFoundError: If configuration is not found.
            DatabaseError: If activation fails.
        """
        try:
            stmt = (
                update(LiveConfig)
                .where(LiveConfig.id == id)
                .values(is_active=True, updated_at=_utc_now())
                .returning(LiveConfig.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise NotFoundError(
                    message=f"Live config not found: {id}",
                    error_code="LIVE_CONFIG_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to activate live config: {e}",
                error_code="LIVE_CONFIG_ACTIVATE_FAILED",
                details={"id": id, "error": str(e)},
            )

    async def deactivate(self, id: str) -> None:
        """
        Deactivate a live trading configuration.

        Args:
            id: Configuration ID.

        Raises:
            NotFoundError: If configuration is not found.
            DatabaseError: If deactivation fails.
        """
        try:
            stmt = (
                update(LiveConfig)
                .where(LiveConfig.id == id)
                .values(is_active=False, updated_at=_utc_now())
                .returning(LiveConfig.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise NotFoundError(
                    message=f"Live config not found: {id}",
                    error_code="LIVE_CONFIG_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to deactivate live config: {e}",
                error_code="LIVE_CONFIG_DEACTIVATE_FAILED",
                details={"id": id, "error": str(e)},
            )

    async def deactivate_all(self) -> int:
        """
        Deactivate all live trading configurations.

        Returns:
            int: Number of configurations deactivated.

        Raises:
            DatabaseError: If deactivation fails.
        """
        try:
            stmt = (
                update(LiveConfig)
                .where(LiveConfig.is_active == True)  # noqa: E712
                .values(is_active=False, updated_at=_utc_now())
                .returning(LiveConfig.id)
            )
            result = await self._session.execute(stmt)
            deactivated = result.scalars().all()
            await self._session.flush()
            return len(deactivated)
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to deactivate all live configs: {e}",
                error_code="LIVE_CONFIG_DEACTIVATE_ALL_FAILED",
                details={"error": str(e)},
            )

    async def count_active(self) -> int:
        """
        Count active live trading configurations.

        Returns:
            int: Number of active configurations.

        Raises:
            DatabaseError: If count query fails.
        """
        try:
            from sqlalchemy import func

            stmt = (
                select(func.count())
                .select_from(LiveConfig)
                .where(LiveConfig.is_active == True)  # noqa: E712
            )
            result = await self._session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to count active live configs: {e}",
                error_code="LIVE_CONFIG_COUNT_FAILED",
                details={"error": str(e)},
            )


class SavedConfigRepository(BaseRepository[SavedConfig]):
    """
    Repository for SavedConfig entity operations.

    Provides methods for managing saved configuration templates
    including filtering by type and searching by name.

    Example:
        >>> repo = SavedConfigRepository(session)
        >>> backtest_configs = await repo.get_by_type("backtest")
    """

    @property
    def _model(self) -> Type[SavedConfig]:
        return SavedConfig

    async def get_by_type(
        self,
        config_type: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[SavedConfig]:
        """
        Get saved configurations by type.

        Args:
            config_type: Configuration type (backtest, live, strategy).
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            list[SavedConfig]: Configurations of the specified type.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(SavedConfig)
                .where(SavedConfig.config_type == config_type)
                .order_by(desc(SavedConfig.created_at))
                .offset(skip)
                .limit(limit)
            )
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get saved configs by type: {e}",
                error_code="SAVED_CONFIG_TYPE_QUERY_FAILED",
                details={"config_type": config_type, "error": str(e)},
            )

    async def get_by_name(self, name: str) -> Optional[SavedConfig]:
        """
        Get a saved configuration by name.

        Args:
            name: Configuration name.

        Returns:
            Optional[SavedConfig]: Configuration with the name if exists.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(SavedConfig).where(SavedConfig.name == name).limit(1)
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get saved config by name: {e}",
                error_code="SAVED_CONFIG_NAME_QUERY_FAILED",
                details={"name": name, "error": str(e)},
            )

    async def search_by_name(
        self,
        query: str,
        config_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[SavedConfig]:
        """
        Search saved configurations by name.

        Args:
            query: Search query (case-insensitive partial match).
            config_type: Optional type filter.
            limit: Maximum number of results.

        Returns:
            list[SavedConfig]: Matching configurations.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(SavedConfig).where(
                SavedConfig.name.ilike(f"%{query}%")
            )

            if config_type is not None:
                stmt = stmt.where(SavedConfig.config_type == config_type)

            stmt = stmt.order_by(desc(SavedConfig.created_at)).limit(limit)

            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to search saved configs: {e}",
                error_code="SAVED_CONFIG_SEARCH_FAILED",
                details={"query": query, "error": str(e)},
            )

    async def update_config(
        self,
        id: str,
        config_json: dict,
        name: Optional[str] = None,
    ) -> None:
        """
        Update a saved configuration.

        Args:
            id: Configuration ID.
            config_json: New configuration data.
            name: Optional new name.

        Raises:
            NotFoundError: If configuration is not found.
            DatabaseError: If update fails.
        """
        try:
            values: dict = {
                "config_json": json.dumps(config_json),
                "updated_at": _utc_now(),
            }

            if name is not None:
                values["name"] = name

            stmt = (
                update(SavedConfig)
                .where(SavedConfig.id == id)
                .values(**values)
                .returning(SavedConfig.id)
            )
            result = await self._session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise NotFoundError(
                    message=f"Saved config not found: {id}",
                    error_code="SAVED_CONFIG_NOT_FOUND",
                    details={"id": id},
                )

            await self._session.flush()
        except NotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update saved config: {e}",
                error_code="SAVED_CONFIG_UPDATE_FAILED",
                details={"id": id, "error": str(e)},
            )

    async def count_by_type(self, config_type: str) -> int:
        """
        Count saved configurations by type.

        Args:
            config_type: Configuration type to count.

        Returns:
            int: Number of configurations of the type.

        Raises:
            DatabaseError: If count query fails.
        """
        try:
            from sqlalchemy import func

            stmt = (
                select(func.count())
                .select_from(SavedConfig)
                .where(SavedConfig.config_type == config_type)
            )
            result = await self._session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to count saved configs by type: {e}",
                error_code="SAVED_CONFIG_COUNT_FAILED",
                details={"config_type": config_type, "error": str(e)},
            )
