"""
Project Service â€” Business logic for project management.
"""

import logging
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.repositories.project_repo import ProjectRepository
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


class ProjectError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class ProjectService:
    def __init__(self, db: AsyncSession, redis=None) -> None:
        self.db = db
        self.redis = redis
        self.repo = ProjectRepository(db)
        self._redis = redis

    async def create_project(
        self,
        name: str,
        owner: User,
        description: Optional[str] = None,
        language: str = "python",
    ) -> Project:
        """Create project. Validates name uniqueness per owner."""
        name = name.strip()
        if not name:
            raise ProjectError("Project name cannot be empty.")
        if len(name) > 100:
            raise ProjectError("Project name cannot exceed 100 characters.")

        existing = await self.repo.get_by_name_and_owner(name, owner.id)
        if existing:
            raise ProjectError(
                f"You already have a project named '{name}'."
            )

        project = Project(
            name=name,
            description=description,
            language=language,
            primary_language=language,
            status="pending",
            file_count=0,
            total_files=0,
            total_size_bytes=0,
            owner_id=owner.id,
        )
        project = await self.repo.create(project)
        await self._invalidate_user_cache(str(owner.id))
        logger.info(f"Project created: id={project.id}, name={name}")
        return project

    async def list_projects(self, owner: User, page: int = 1, size: int = 20) -> dict:
        """List user projects with pagination and caching."""
        size = min(size, 100)
        skip = (page - 1) * size
        cache_key = f"aca:project:list:{owner.id}:p{page}:s{size}"

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        projects = await self.repo.get_by_owner(owner.id, skip=skip, limit=size)
        total = await self.repo.count_by_owner(owner.id)
        pages = (total + size - 1) // size if total > 0 else 0

        result = {
            "items": [self._to_dict(p) for p in projects],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }
        await self._cache_set(cache_key, result, ttl=300)
        return result

    async def get_project(self, project_id: str, owner: User) -> Project:
        """Get project by ID, enforcing ownership."""
        project = await self.repo.get_by_id_and_owner(project_id, owner.id)
        if not project:
            raise ProjectNotFoundError(
                f"Project '{project_id}' not found or access denied."
            )
        return project

    async def get_project_stats(self, owner: User) -> dict:
        """Get aggregate stats with 2-minute cache."""
        cache_key = f"aca:project:stats:{owner.id}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached
        stats = await self.repo.get_stats_by_owner(owner.id)
        await self._cache_set(cache_key, stats, ttl=120)
        return stats

    async def update_project(
        self,
        project_id: str,
        owner: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Project:
        """Update project metadata. Only owner can update."""
        project = await self.get_project(project_id, owner)

        if name is not None:
            name = name.strip()
            if not name:
                raise ProjectError("Project name cannot be empty.")
            if len(name) > 100:
                raise ProjectError("Project name cannot exceed 100 characters.")
            if name != project.name:
                existing = await self.repo.get_by_name_and_owner(name, owner.id)
                if existing:
                    raise ProjectError(f"You already have a project named '{name}'.")
            project.name = name

        if description is not None:
            project.description = description

        if language is not None:
            project.language = language
            project.primary_language = language

        project = await self.repo.update(project)
        await self._invalidate_project_cache(project_id, str(owner.id))
        return project

    async def delete_project(self, project_id: str, owner: User) -> bool:
        """Delete project. Only owner can delete."""
        project = await self.get_project(project_id, owner)
        deleted = await self.repo.delete(project.id)
        if deleted:
            await self._invalidate_project_cache(project_id, str(owner.id))
        return deleted



    async def _cache_get(self, key: str):
        """Get from cache, returns None if Redis unavailable."""
        if not self._redis:
            return None
        try:
            from app.services.cache_service import CacheService
            cs = CacheService()
            cs._redis = self._redis
            cs._connected = True
            return await cs.get_cached_response(key)
        except Exception:
            return None

    async def _cache_set(self, key: str, value, ttl: int = 300) -> None:
        """Set in cache, silently fails if Redis unavailable."""
        if not self._redis:
            return
        try:
            from app.services.cache_service import CacheService
            cs = CacheService()
            cs._redis = self._redis
            cs._connected = True
            await cs.set_cached_response(key, value, ttl=ttl)
        except Exception:
            pass

    async def _cache_delete(self, key: str) -> None:
        """Delete from cache, silently fails if Redis unavailable."""
        if not self._redis:
            return
        try:
            if self._redis:
                await self._redis.delete(key)
        except Exception:
            pass

    async def _cache_invalidate_pattern(self, pattern: str) -> None:
        """Invalidate cache pattern, silently fails if unavailable."""
        if not self._redis:
            return
        try:
            cursor = b"0"
            while cursor:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == b"0" or cursor == 0:
                    break
        except Exception:
            pass

    async def _invalidate_user_cache(self, user_id: str) -> None:
        await self._cache_invalidate_pattern(f"aca:project:list:{user_id}:*")
        await self._cache_delete(f"aca:project:stats:{user_id}")

    async def _invalidate_project_cache(self, project_id: str, user_id: str) -> None:
        await self._cache_delete(f"aca:project:single:{project_id}")
        await self._invalidate_user_cache(user_id)

    @staticmethod
    def _to_dict(project: Project) -> dict:
        """Serialize project using effective property accessors."""
        return {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "language": project.language or "unknown",
            "status": project.status,
            "file_count": int(getattr(project, "file_count", None) or getattr(project, "total_files", None) or 0),
            "total_size_bytes": project.total_size_bytes,
            "owner_id": str(project.owner_id),
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "indexed_at": project.indexed_at.isoformat() if project.indexed_at else None,
        }