"""
Base repository with generic CRUD operations.

Provides a foundation for all entity-specific repositories with
common database operations and type safety through generics.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, Optional, TypeVar, Type

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError, DatabaseError
from backend.infrastructure.database.models import Base


# Type variable for entity models
T = TypeVar("T", bound=Base)


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


class BaseRepository(ABC, Generic[T]):
    """
    Base repository with generic CRUD operations.

    Provides standard database operations for any SQLAlchemy model.
    Subclasses should specify the model class and add specialized methods.

    Type Parameters:
        T: The SQLAlchemy model class this repository manages.

    Attributes:
        session: The async SQLAlchemy session for database operations.

    Example:
        >>> class UserRepository(BaseRepository[User]):
        ...     _model = User
        ...
        >>> repo = UserRepository(session)
        >>> user = await repo.get_by_id("user-123")
    """

    @property
    @abstractmethod
    def _model(self) -> Type[T]:
        """
        The SQLAlchemy model class this repository manages.

        Subclasses must define this property.
        """
        ...

    @property
    def _id_column_name(self) -> str:
        """
        Name of the primary key column.

        Override in subclass if primary key is not 'id'.
        """
        return "id"

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize the repository with an async session.

        Args:
            session: SQLAlchemy AsyncSession for database operations.
        """
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """Get the underlying database session."""
        return self._session

    def _get_id_column(self):
        """Get the ID column attribute from the model."""
        return getattr(self._model, self._id_column_name)

    async def get_by_id(self, id: str | int) -> Optional[T]:
        """
        Get an entity by its primary key.

        Args:
            id: Primary key value.

        Returns:
            Optional[T]: The entity if found, None otherwise.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(self._model).where(self._get_id_column() == id)
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get {self._model.__name__} by id: {e}",
                error_code="REPOSITORY_GET_FAILED",
                details={"model": self._model.__name__, "id": str(id), "error": str(e)},
            )

    async def get_by_id_or_raise(self, id: str | int) -> T:
        """
        Get an entity by its primary key or raise NotFoundError.

        Args:
            id: Primary key value.

        Returns:
            T: The entity.

        Raises:
            NotFoundError: If entity is not found.
            DatabaseError: If query execution fails.
        """
        entity = await self.get_by_id(id)
        if entity is None:
            raise NotFoundError(
                message=f"{self._model.__name__} not found: {id}",
                error_code="ENTITY_NOT_FOUND",
                details={"model": self._model.__name__, "id": str(id)},
            )
        return entity

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[T]:
        """
        Get all entities with pagination.

        Args:
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            list[T]: List of entities.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = select(self._model).offset(skip).limit(limit)
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to get all {self._model.__name__}: {e}",
                error_code="REPOSITORY_LIST_FAILED",
                details={"model": self._model.__name__, "error": str(e)},
            )

    async def create(self, obj: T) -> T:
        """
        Create a new entity.

        Args:
            obj: The entity instance to create.

        Returns:
            T: The created entity with any generated values.

        Raises:
            DatabaseError: If creation fails.
        """
        try:
            self._session.add(obj)
            await self._session.flush()
            await self._session.refresh(obj)
            return obj
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to create {self._model.__name__}: {e}",
                error_code="REPOSITORY_CREATE_FAILED",
                details={"model": self._model.__name__, "error": str(e)},
            )

    async def create_many(self, objects: list[T]) -> list[T]:
        """
        Create multiple entities in bulk.

        Args:
            objects: List of entity instances to create.

        Returns:
            list[T]: List of created entities.

        Raises:
            DatabaseError: If bulk creation fails.
        """
        try:
            self._session.add_all(objects)
            await self._session.flush()
            for obj in objects:
                await self._session.refresh(obj)
            return objects
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to bulk create {self._model.__name__}: {e}",
                error_code="REPOSITORY_BULK_CREATE_FAILED",
                details={"model": self._model.__name__, "count": len(objects), "error": str(e)},
            )

    async def update(self, obj: T) -> T:
        """
        Update an existing entity.

        Args:
            obj: The entity instance with updated values.

        Returns:
            T: The updated entity.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            # Update the updated_at timestamp if the model has it
            if hasattr(obj, "updated_at"):
                obj.updated_at = _utc_now()  # type: ignore

            await self._session.merge(obj)
            await self._session.flush()
            await self._session.refresh(obj)
            return obj
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to update {self._model.__name__}: {e}",
                error_code="REPOSITORY_UPDATE_FAILED",
                details={"model": self._model.__name__, "error": str(e)},
            )

    async def delete(self, id: str | int) -> bool:
        """
        Delete an entity by its primary key.

        Args:
            id: Primary key value of the entity to delete.

        Returns:
            bool: True if entity was deleted, False if not found.

        Raises:
            DatabaseError: If deletion fails.
        """
        try:
            stmt = delete(self._model).where(self._get_id_column() == id)
            result = await self._session.execute(stmt)
            await self._session.flush()
            return result.rowcount > 0  # type: ignore
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to delete {self._model.__name__}: {e}",
                error_code="REPOSITORY_DELETE_FAILED",
                details={"model": self._model.__name__, "id": str(id), "error": str(e)},
            )

    async def delete_or_raise(self, id: str | int) -> None:
        """
        Delete an entity by its primary key or raise NotFoundError.

        Args:
            id: Primary key value of the entity to delete.

        Raises:
            NotFoundError: If entity is not found.
            DatabaseError: If deletion fails.
        """
        deleted = await self.delete(id)
        if not deleted:
            raise NotFoundError(
                message=f"{self._model.__name__} not found: {id}",
                error_code="ENTITY_NOT_FOUND",
                details={"model": self._model.__name__, "id": str(id)},
            )

    async def count(self) -> int:
        """
        Count total entities.

        Returns:
            int: Total number of entities.

        Raises:
            DatabaseError: If count query fails.
        """
        try:
            stmt = select(func.count()).select_from(self._model)
            result = await self._session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to count {self._model.__name__}: {e}",
                error_code="REPOSITORY_COUNT_FAILED",
                details={"model": self._model.__name__, "error": str(e)},
            )

    async def exists(self, id: str | int) -> bool:
        """
        Check if an entity exists by its primary key.

        Args:
            id: Primary key value.

        Returns:
            bool: True if entity exists, False otherwise.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            stmt = (
                select(func.count())
                .select_from(self._model)
                .where(self._get_id_column() == id)
            )
            result = await self._session.execute(stmt)
            count = result.scalar() or 0
            return count > 0
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to check existence of {self._model.__name__}: {e}",
                error_code="REPOSITORY_EXISTS_FAILED",
                details={"model": self._model.__name__, "id": str(id), "error": str(e)},
            )
