"""
File Service — Business logic for file upload and management.

Upload modes:
1. Individual files — single source code file upload
2. ZIP archive — extract and store all source files from ZIP
3. GitHub URL — clone repository and index all files

Storage strategy:
  Files stored at: uploads/{project_id}/{relative_path}
  Content also stored in DB for RAG retrieval (up to 10MB per file)
"""

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.file import ProjectFile
from app.models.project import Project
from app.models.user import User
from app.repositories.file_repo import FileRepository
from app.repositories.project_repo import ProjectRepository
from app.services.cache_service import CacheService
from app.utils.file_utils import (
    extract_zip_files,
    get_language,
    is_allowed_file,
    is_binary_file,
    compute_hash,
    count_lines,
    validate_zip_file,
    should_skip_file,
    MAX_FILE_SIZE_BYTES,
)

logger = logging.getLogger(__name__)

UPLOAD_BASE_DIR = Path(settings.UPLOAD_DIR)


class FileUploadError(Exception):
    """File upload validation error."""
    pass


class FileService:
    """
    Stateless file service — instantiated per request.
    Handles all file upload logic with storage and DB tracking.
    """

    def __init__(self, db: AsyncSession, redis: aioredis.Redis) -> None:
        self.db = db
        self.redis = redis
        self.file_repo = FileRepository(db)
        self.project_repo = ProjectRepository(db)
        self.cache = CacheService()

    # ─────────────────────────────────────────────
    # Upload Individual File
    # ─────────────────────────────────────────────

    async def upload_single_file(
        self,
        project: Project,
        filename: str,
        content: bytes,
        overwrite: bool = True,
    ) -> ProjectFile:
        """
        Upload a single source code file to a project.

        Args:
            project: Target project
            filename: Original file name
            content: File bytes
            overwrite: Replace existing file with same path

        Returns:
            Created ProjectFile instance

        Raises:
            FileUploadError: On validation failure
        """
        # Validate file type
        if not is_allowed_file(filename):
            ext = Path(filename).suffix
            raise FileUploadError(
                f"File type '{ext}' is not allowed. "
                f"Upload source code files (.py, .js, .ts, .java, etc.)"
            )

        # Validate file size
        if len(content) > MAX_FILE_SIZE_BYTES:
            size_mb = len(content) / 1024 / 1024
            raise FileUploadError(
                f"File too large: {size_mb:.1f}MB (max 10MB per file)"
            )

        # Detect properties
        language = get_language(filename)
        binary = is_binary_file(content)
        content_hash = compute_hash(content)
        line_count = count_lines(content) if not binary else 0

        # Check for duplicate (by hash)
        existing_by_hash = await self.file_repo.get_by_hash(project.id, content_hash)
        if existing_by_hash and existing_by_hash.file_path != filename:
            logger.info(f"Duplicate content detected: {filename} matches {existing_by_hash.file_path}")

        # Check for existing file at same path
        existing = await self.file_repo.get_by_path(project.id, filename)
        if existing and not overwrite:
            raise FileUploadError(f"File '{filename}' already exists in this project.")
        if existing and overwrite:
            await self.file_repo.delete(existing.id)

        # Save to disk
        file_disk_path = await self._save_to_disk(project.id, filename, content)

        # Create DB record
        project_file = ProjectFile(
            project_id=project.id,
            file_path=filename,
            file_name=Path(filename).name,
            file_extension=Path(filename).suffix.lower(),
            language=language,
            size_bytes=len(content),
            line_count=line_count,
            content=content.decode("utf-8", errors="replace") if not binary else None,
            content_hash=content_hash,
            encoding="utf-8",
            is_parsed=False,
            is_embedded=False,
            is_binary=binary,
            chunk_count=0,
        )
        project_file = await self.file_repo.create(project_file)

        # Update project stats
        await self._update_project_stats(project.id)
        await self._invalidate_cache(str(project.id))

        logger.info(
            f"File uploaded: {filename} → project {project.id} "
            f"({len(content)} bytes, lang={language})"
        )
        return project_file

    # ─────────────────────────────────────────────
    # Upload ZIP Archive
    # ─────────────────────────────────────────────

    async def upload_zip(
        self,
        project: Project,
        zip_content: bytes,
        replace_existing: bool = False,
    ) -> dict:
        """
        Extract and upload all source files from a ZIP archive.

        Args:
            project: Target project
            zip_content: ZIP file bytes
            replace_existing: Delete existing files before upload

        Returns:
            Summary dict with uploaded, skipped, errors counts

        Raises:
            FileUploadError: If ZIP is invalid
        """
        # Validate ZIP
        is_valid, error_msg = validate_zip_file(zip_content)
        if not is_valid:
            raise FileUploadError(error_msg)

        # Clear existing files if replacing
        if replace_existing:
            deleted = await self.file_repo.delete_by_project(project.id)
            logger.info(f"Cleared {deleted} existing files for project {project.id}")

        # Extract files from ZIP
        extracted = extract_zip_files(zip_content)
        if not extracted:
            raise FileUploadError(
                "ZIP file contains no supported source code files. "
                "Please upload a ZIP with .py, .js, .ts, .java files, etc."
            )

        # Bulk create ProjectFile records
        project_files = []
        skipped = 0
        errors: list[str] = []

        for file_info in extracted:
            try:
                # Check for duplicates
                existing = await self.file_repo.get_by_path(
                    project.id, file_info["path"]
                )
                if existing:
                    if not replace_existing:
                        skipped += 1
                        continue
                    await self.file_repo.delete(existing.id)

                # Save to disk
                await self._save_to_disk(
                    project.id,
                    file_info["path"],
                    file_info["content"],
                )

                project_file = ProjectFile(
                    project_id=project.id,
                    file_path=file_info["path"],
                    file_name=file_info["name"],
                    file_extension=Path(file_info["path"]).suffix.lower(),
                    language=file_info["language"],
                    size_bytes=file_info["size_bytes"],
                    line_count=file_info["line_count"],
                    content=(
                        file_info["content"].decode("utf-8", errors="replace")
                        if not file_info["is_binary"] and file_info["size_bytes"] < 500_000
                        else None
                    ),
                    content_hash=file_info["content_hash"],
                    encoding="utf-8",
                    is_parsed=False,
                    is_embedded=False,
                    is_binary=file_info["is_binary"],
                    chunk_count=0,
                )
                project_files.append(project_file)

            except Exception as exc:
                logger.warning(f"Error processing {file_info['path']}: {exc}")
                errors.append(f"{file_info['path']}: {exc}")

        # Bulk insert
        if project_files:
            await self.file_repo.bulk_create(project_files)

        # Update project stats
        await self._update_project_stats(project.id)
        await self._invalidate_cache(str(project.id))

        summary = {
            "uploaded": len(project_files),
            "skipped": skipped,
            "errors": len(errors),
            "error_details": errors[:10],
            "project_id": str(project.id),
        }
        logger.info(f"ZIP upload complete: {summary}")
        return summary

    # ─────────────────────────────────────────────
    # Clone GitHub Repository
    # ─────────────────────────────────────────────

    async def upload_from_github(
        self,
        project: Project,
        github_url: str,
        branch: str = "main",
    ) -> dict:
        """
        Clone a GitHub repository and upload all source files.

        Args:
            project: Target project
            github_url: GitHub repository URL (https or git format)
            branch: Branch to clone (default: main, falls back to master)

        Returns:
            Summary dict with uploaded, skipped counts

        Raises:
            FileUploadError: If URL is invalid or clone fails
        """
        # Validate GitHub URL
        github_url = github_url.strip()
        if not (github_url.startswith("https://github.com/") or
                github_url.startswith("https://gitlab.com/") or
                github_url.startswith("git@")):
            raise FileUploadError(
                "Invalid repository URL. Must be a GitHub or GitLab HTTPS URL. "
                "Example: https://github.com/username/repo"
            )

        # Remove .git suffix if present
        if github_url.endswith(".git"):
            github_url = github_url[:-4]

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir) / "repo"

            # Try cloning with specified branch, fall back to master
            success = False
            for try_branch in [branch, "master", "main", "develop"]:
                try:
                    logger.info(f"Cloning {github_url} branch={try_branch}...")
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda b=try_branch: subprocess.run(
                            [
                                "git", "clone",
                                "--depth", "1",
                                "--branch", b,
                                "--single-branch",
                                f"{github_url}.git",
                                str(clone_path),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )
                    )
                    if result.returncode == 0:
                        success = True
                        break
                    logger.debug(f"Clone failed for branch {try_branch}: {result.stderr}")
                except subprocess.TimeoutExpired:
                    raise FileUploadError("Repository clone timed out (120s). Repository may be too large.")
                except Exception as exc:
                    logger.warning(f"Clone attempt failed: {exc}")

            if not success:
                raise FileUploadError(
                    f"Could not clone repository: {github_url}. "
                    "Check the URL is correct and the repository is public."
                )

            # Walk the cloned directory and collect files
            uploaded = 0
            skipped = 0
            errors: list[str] = []
            project_files = []

            for root, dirs, files in os.walk(clone_path):
                # Prune skip directories in-place
                dirs[:] = [
                    d for d in dirs
                    if d not in {"node_modules", ".git", "__pycache__",
                                ".venv", "venv", "dist", "build", "target"}
                ]

                for filename in files:
                    abs_path = Path(root) / filename
                    relative_path = str(abs_path.relative_to(clone_path))

                    if should_skip_file(relative_path):
                        skipped += 1
                        continue

                    if not is_allowed_file(filename):
                        skipped += 1
                        continue

                    try:
                        content = abs_path.read_bytes()
                        if len(content) > MAX_FILE_SIZE_BYTES:
                            skipped += 1
                            continue

                        binary = is_binary_file(content)
                        project_file = ProjectFile(
                            project_id=project.id,
                            file_path=relative_path.replace("\\", "/"),
                            file_name=filename,
                            file_extension=Path(filename).suffix.lower(),
                            language=get_language(filename),
                            size_bytes=len(content),
                            line_count=count_lines(content) if not binary else 0,
                            content=(
                                content.decode("utf-8", errors="replace")
                                if not binary and len(content) < 500_000
                                else None
                            ),
                            content_hash=compute_hash(content),
                            encoding="utf-8",
                            is_parsed=False,
                            is_embedded=False,
                            is_binary=binary,
                            chunk_count=0,
                        )
                        project_files.append(project_file)

                        # Also save to disk
                        await self._save_to_disk(
                            project.id,
                            relative_path.replace("\\", "/"),
                            content,
                        )
                        uploaded += 1

                    except Exception as exc:
                        logger.warning(f"Error reading {relative_path}: {exc}")
                        errors.append(str(exc))

            # Bulk insert
            if project_files:
                await self.file_repo.bulk_create(project_files)

        # Update project
        await self._update_project_stats(project.id)

        # Update repo URL on project
        from sqlalchemy import update
        await self.db.execute(
            update(Project)
            .where(Project.id == project.id)
            .values(repo_url=github_url)
        )
        await self.db.commit()
        await self._invalidate_cache(str(project.id))

        return {
            "uploaded": uploaded,
            "skipped": skipped,
            "errors": len(errors),
            "project_id": str(project.id),
        }

    # ─────────────────────────────────────────────
    # File Listing and Retrieval
    # ─────────────────────────────────────────────

    async def list_files(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> dict:
        """
        List all files in a project with pagination.

        Args:
            project_id: UUID string of the project
            skip: Pagination offset
            limit: Max results

        Returns:
            Dict with items (list of file dicts) and total count
        """
        files = await self.file_repo.get_by_project(project_id, skip=skip, limit=limit)
        total = await self.file_repo.count_by_project(project_id)

        return {
            "items": [self._file_to_dict(f) for f in files],
            "total": total,
        }

    async def get_file_content(
        self,
        file_id: str,
        project_id: str,
    ) -> Optional[ProjectFile]:
        """
        Get a specific file with its content.

        Args:
            file_id: UUID string of the file
            project_id: UUID of the owning project (for security check)

        Returns:
            ProjectFile instance or None
        """
        file = await self.file_repo.get_by_id(file_id)
        if not file or str(file.project_id) != project_id:
            return None
        return file

    # ─────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────

    async def _save_to_disk(
        self,
        project_id,
        relative_path: str,
        content: bytes,
    ) -> Path:
        """
        Save file content to the uploads directory.
        Creates parent directories as needed.

        Args:
            project_id: UUID of the project (used as directory name)
            relative_path: Relative file path within project
            content: File bytes to write

        Returns:
            Absolute path where file was saved
        """
        # Sanitize path — prevent directory traversal
        clean_path = relative_path.lstrip("/").replace("..", "")
        disk_path = UPLOAD_BASE_DIR / str(project_id) / clean_path
        disk_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(disk_path, "wb") as f:
            await f.write(content)

        return disk_path

    async def _update_project_stats(self, project_id) -> None:
        """
        Recompute and update project aggregate stats from files.
        Called after every upload operation.
        """
        from sqlalchemy import update

        stats = await self.file_repo.get_project_stats(project_id)

        await self.db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                total_files=stats["total_files"],
                file_count=stats["total_files"],
                total_lines=stats["total_lines"],
                total_size_bytes=stats["total_size_bytes"],
                primary_language=self._detect_primary_language(stats["by_language"]),
            )
        )
        await self.db.commit()

    @staticmethod
    def _detect_primary_language(by_language: dict) -> Optional[str]:
        """Return the most common language in the project."""
        if not by_language:
            return None
        # Exclude 'unknown' and 'text' from primary language
        filtered = {k: v for k, v in by_language.items()
                    if k not in ("unknown", "text", "markdown", "json", "yaml")}
        if not filtered:
            return list(by_language.keys())[0] if by_language else None
        return max(filtered, key=lambda k: filtered[k])


    @staticmethod
    def _file_to_dict(f) -> dict:
        """Convert ProjectFile ORM object to a response dict.
        
        Uses getattr with defaults to handle any missing fields gracefully.
        """
        # Derive file_name and file_extension from file_path
        _file_path = getattr(f, "file_path", "") or ""
        _file_name = _file_path.split("/")[-1].split("\\")[-1]
        _parts = _file_name.rsplit(".", 1)
        _file_ext = ("." + _parts[1]) if len(_parts) > 1 else None

        return {
            "id": str(getattr(f, "id", "")),
            "project_id": str(getattr(f, "project_id", "")),
            "file_path": _file_path,
            "file_name": getattr(f, "file_name", None) or _file_name,
            "file_extension": getattr(f, "file_extension", None) or _file_ext,
            "language": getattr(f, "language", None) or "unknown",
            "size_bytes": int(getattr(f, "size_bytes", 0) or 0),
            "line_count": int(getattr(f, "line_count", 0) or 0),
            "is_binary": bool(getattr(f, "is_binary", False)),
            "is_parsed": bool(getattr(f, "is_parsed", False)),
            "is_embedded": bool(getattr(f, "is_embedded", False)),
            "content_hash": getattr(f, "content_hash", None),
            "chunk_count": int(getattr(f, "chunk_count", 0) or 0),
            "complexity_score": float(getattr(f, "complexity_score", 0.0) or 0.0),
            "parse_error": getattr(f, "parse_error", None),
            "created_at": (
                f.created_at.isoformat()
                if getattr(f, "created_at", None) else None
            ),
            "updated_at": (
                f.updated_at.isoformat()
                if getattr(f, "updated_at", None) else None
            ),
        }

    async def _invalidate_cache(self, project_id: str) -> None:
        """Invalidate project-related cache entries (graceful)."""
        try:
            if not hasattr(self, "cache") or self.cache is None:
                return
            if hasattr(self.cache, "invalidate_key"):
                await self.cache.invalidate_key(f"aca:project:single:{project_id}")
            if hasattr(self.cache, "invalidate_project_cache"):
                await self.cache.invalidate_project_cache(project_id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("Cache invalidation skipped: %s", exc)

