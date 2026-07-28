"""
User Repository - Data access layer for User model.
"""

from __future__ import annotations

import logging
import uuid as _uuid_module
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for all User database operations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session."""
        super().__init__(User, db)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Fetch user by UUID string."""
        try:
            uid = _uuid_module.UUID(str(user_id))
        except (ValueError, AttributeError):
            logger.warning("Invalid UUID: %s", user_id)
            return None
        result = await self.db.execute(select(User).where(User.id == uid))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch user by email (case-insensitive)."""
        result = await self.db.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        """Fetch user by username."""
        result = await self.db.execute(
            select(User).where(User.username == username.strip())
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Check if email is registered."""
        result = await self.db.execute(
            select(User.id).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none() is not None

    async def username_exists(self, username: str) -> bool:
        """Check if username is taken."""
        result = await self.db.execute(
            select(User.id).where(User.username == username.strip())
        )
        return result.scalar_one_or_none() is not None

    async def update_last_login(self, user_id: UUID) -> None:
        """Update last_login timestamp."""
        now = datetime.now(timezone.utc)
        try:
            await self.db.execute(
                update(User).where(User.id == user_id).values(last_login_at=now)
            )
            await self.db.commit()
        except Exception as exc:
            logger.warning("update_last_login failed: %s", exc)
            try:
                await self.db.rollback()
            except Exception:
                pass

    async def set_active(self, user_id: UUID, is_active: bool) -> None:
        """Enable or disable a user account."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(is_active=is_active)
        )
        await self.db.commit()
