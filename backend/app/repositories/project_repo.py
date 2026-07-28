"""
Project Repository — Data access layer for Project model.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.models.project import Project
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def _to_uuid(value) -> UUID:
    """Convert string or UUID to UUID object."""
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


class ProjectRepository(BaseRepository[Project]):
    """Repository for all Project database operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Project, db)

    async def get_by_owner(
        self,
        owner_id,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Project]:
        """Get all projects owned by a user, paginated, newest first."""
        result = await self.db.execute(
            select(Project)
            .where(Project.owner_id == _to_uuid(owner_id))
            .order_by(Project.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_owner(self, owner_id) -> int:
        """Count total projects owned by a user."""
        result = await self.db.execute(
            select(func.count(Project.id))
            .where(Project.owner_id == _to_uuid(owner_id))
        )
        return result.scalar_one() or 0

    async def get_by_id_and_owner(
        self,
        project_id,
        owner_id,
    ) -> Optional[Project]:
        """Get project by ID only if owned by requesting user."""
        try:
            pid = _to_uuid(project_id)
            oid = _to_uuid(owner_id)
        except (ValueError, AttributeError) as exc:
            logger.warning(f"Invalid UUID in get_by_id_and_owner: {exc}")
            return None

        result = await self.db.execute(
            select(Project).where(
                and_(
                    Project.id == pid,
                    Project.owner_id == oid,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name_and_owner(
        self,
        name: str,
        owner_id,
    ) -> Optional[Project]:
        """Check if project name already exists for this owner."""
        result = await self.db.execute(
            select(Project).where(
                and_(
                    Project.name == name.strip(),
                    Project.owner_id == _to_uuid(owner_id),
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, project_id, status: str) -> Optional[Project]:
        """Update project indexing status."""
        values: dict = {"status": status}
        if status == "ready":
            values["indexed_at"] = datetime.now(timezone.utc)
        await self.db.execute(
            update(Project)
            .where(Project.id == _to_uuid(project_id))
            .values(**values)
        )
        await self.db.commit()
        return await self.get_by_id(project_id)

    async def increment_file_count(self, project_id, count: int = 1) -> None:
        """Increment file count after upload."""
        await self.db.execute(
            update(Project)
            .where(Project.id == _to_uuid(project_id))
            .values(file_count=Project.file_count + count)
        )
        await self.db.commit()

    async def get_stats_by_owner(self, owner_id) -> dict:
        """Get aggregate project statistics for dashboard."""
        result = await self.db.execute(
            select(
                func.count(Project.id).label("total"),
                func.sum(Project.file_count).label("total_files"),
                Project.status,
            )
            .where(Project.owner_id == _to_uuid(owner_id))
            .group_by(Project.status)
        )
        rows = result.all()
        stats: dict = {"total": 0, "total_files": 0, "by_status": {}}
        for row in rows:
            stats["total"] += row.total
            stats["total_files"] += int(row.total_files or 0)
            stats["by_status"][row.status] = row.total
        return stats