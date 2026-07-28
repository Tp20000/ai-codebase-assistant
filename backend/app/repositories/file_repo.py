"""
File Repository — Data access layer for ProjectFile model.
Maps to the project_files table created in Step 3.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import ProjectFile
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class FileRepository(BaseRepository[ProjectFile]):
    """Repository for all ProjectFile database operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(ProjectFile, db)

    async def get_by_project(
        self,
        project_id: UUID | str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ProjectFile]:
        """
        Get all files for a project, paginated.

        Args:
            project_id: UUID of the project
            skip: Pagination offset
            limit: Max results

        Returns:
            List of ProjectFile instances ordered by file path
        """
        result = await self.db.execute(
            select(ProjectFile)
            .where(ProjectFile.project_id == project_id)
            .order_by(ProjectFile.file_path.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_project(self, project_id: UUID | str) -> int:
        """Count total files in a project."""
        result = await self.db.execute(
            select(func.count(ProjectFile.id))
            .where(ProjectFile.project_id == project_id)
        )
        return result.scalar_one() or 0

    async def get_by_path(
        self,
        project_id: UUID | str,
        file_path: str,
    ) -> Optional[ProjectFile]:
        """
        Get a file by its path within a project.
        Used to detect duplicate files during re-upload.

        Args:
            project_id: UUID of the project
            file_path: Relative path of the file

        Returns:
            ProjectFile if found, None otherwise
        """
        result = await self.db.execute(
            select(ProjectFile).where(
                and_(
                    ProjectFile.project_id == project_id,
                    ProjectFile.file_path == file_path,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_hash(
        self,
        project_id: UUID | str,
        content_hash: str,
    ) -> Optional[ProjectFile]:
        """
        Get file by content hash within a project.
        Used for deduplication — skip files with identical content.

        Args:
            project_id: UUID of the project
            content_hash: SHA-256 hash of file content

        Returns:
            Existing ProjectFile with matching hash, or None
        """
        result = await self.db.execute(
            select(ProjectFile).where(
                and_(
                    ProjectFile.project_id == project_id,
                    ProjectFile.content_hash == content_hash,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_language(
        self,
        project_id: UUID | str,
        language: str,
    ) -> list[ProjectFile]:
        """
        Get all files of a specific language in a project.
        Used by the code parser to batch-process by language.

        Args:
            project_id: UUID of the project
            language: Language string (e.g., 'python')

        Returns:
            List of matching ProjectFile instances
        """
        result = await self.db.execute(
            select(ProjectFile).where(
                and_(
                    ProjectFile.project_id == project_id,
                    ProjectFile.language == language,
                )
            )
        )
        return list(result.scalars().all())

    async def get_project_stats(self, project_id: UUID | str) -> dict:
        """
        Compute aggregate file statistics for a project.
        Used to update project.total_files, total_lines, total_size_bytes.

        Args:
            project_id: UUID of the project

        Returns:
            Dict with total_files, total_lines, total_size_bytes, by_language
        """
        # Aggregate totals
        result = await self.db.execute(
            select(
                func.count(ProjectFile.id).label("total_files"),
                func.sum(ProjectFile.line_count).label("total_lines"),
                func.sum(ProjectFile.size_bytes).label("total_size_bytes"),
            ).where(ProjectFile.project_id == project_id)
        )
        row = result.one()

        # Language breakdown
        lang_result = await self.db.execute(
            select(
                ProjectFile.language,
                func.count(ProjectFile.id).label("count"),
            )
            .where(ProjectFile.project_id == project_id)
            .group_by(ProjectFile.language)
        )
        by_language = {r.language: r.count for r in lang_result.all()}

        return {
            "total_files": int(row.total_files or 0),
            "total_lines": int(row.total_lines or 0),
            "total_size_bytes": int(row.total_size_bytes or 0),
            "by_language": by_language,
        }

    async def delete_by_project(self, project_id: UUID | str) -> int:
        """
        Delete all files for a project.
        Called when re-uploading or deleting a project.

        Args:
            project_id: UUID of the project

        Returns:
            Number of files deleted
        """
        result = await self.db.execute(
            delete(ProjectFile).where(ProjectFile.project_id == project_id)
        )
        await self.db.commit()
        deleted = result.rowcount
        logger.info(f"Deleted {deleted} files for project {project_id}")
        return deleted

    async def bulk_create(self, files: list[ProjectFile]) -> list[ProjectFile]:
        """
        Efficiently insert multiple files in a single transaction.
        Used during ZIP extraction to batch-insert hundreds of files.

        Args:
            files: List of ProjectFile instances to insert

        Returns:
            List of created ProjectFile instances
        """
        if not files:
            return []

        for f in files:
            self.db.add(f)

        await self.db.commit()

        # Refresh all instances
        for f in files:
            await self.db.refresh(f)

        logger.info(f"Bulk created {len(files)} files")
        return files