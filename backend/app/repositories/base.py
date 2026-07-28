"""
Base Repository - Generic async CRUD repository pattern.
All domain repositories inherit from this base class.
"""

from __future__ import annotations

import logging
from typing import Generic, TypeVar, Type, Optional, Any
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

logger = logging.getLogger(__name__)
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic async repository providing standard CRUD operations.

    Stores session as both self.db and self._db for compatibility
    with different subclass implementations.

    Usage:
        class UserRepository(BaseRepository[User]):
            def __init__(self, db: AsyncSession):
                super().__init__(User, db)
    """

    def __init__(self, model: Type[ModelType], db: AsyncSession) -> None:
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            db: Async database session
        """
        self.model = model
        self.db = db
        self._db = db  # alias for backward compatibility

    async def get_by_id(self, id: Any) -> Optional[ModelType]:
        """Retrieve single record by primary key."""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """Retrieve paginated list of records."""
        result = await self.db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, obj: ModelType) -> ModelType:
        """Persist a new model instance."""
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        logger.debug("Created %s id=%s", self.model.__name__, obj.id)
        return obj

    async def update(self, obj: ModelType) -> ModelType:
        """Persist changes to an existing model instance."""
        await self.db.commit()
        await self.db.refresh(obj)
        logger.debug("Updated %s id=%s", self.model.__name__, obj.id)
        return obj

    async def delete(self, id: Any) -> bool:
        """Delete a record by primary key."""
        result = await self.db.execute(
            delete(self.model).where(self.model.id == id)
        )
        await self.db.commit()
        deleted = result.rowcount > 0
        logger.debug("Deleted %s id=%s: %s", self.model.__name__, id, deleted)
        return deleted

    async def exists(self, id: Any) -> bool:
        """Check if a record exists by primary key."""
        result = await self.db.execute(
            select(self.model.id).where(self.model.id == id)
        )
        return result.scalar_one_or_none() is not None
