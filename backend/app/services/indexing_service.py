"""
Indexing Service - Step 29
AI Codebase Assistant v2.0

Business logic layer for codebase indexing operations.
Bridges the FastAPI API layer and the Celery task queue.

Responsibilities:
    - Validate files before queuing
    - Queue indexing tasks via Celery
    - Track and expose indexing status
    - Calculate indexing statistics
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.tasks.indexing_tasks import (
    get_indexing_progress,
    index_project_files,
    reindex_single_file,
)

logger = logging.getLogger(__name__)

# Max files per indexing batch
MAX_FILES_PER_BATCH = 500
# Max total content size per batch (50MB)
MAX_TOTAL_CONTENT_BYTES = 50 * 1024 * 1024


class IndexingService:
    """
    Service layer for codebase indexing operations.

    Provides a clean interface for the API layer to trigger
    background indexing without directly importing Celery tasks.
    """

    @staticmethod
    def queue_project_indexing(
        project_id: str,
        user_id: str,
        files: list[dict[str, str]],
        force_reindex: bool = False,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> dict[str, Any]:
        """
        Validate and queue a full project indexing task.

        Performs pre-flight validation on the file list before
        queuing the Celery task. Returns immediately with task_id.

        Args:
            project_id:    Project UUID
            user_id:       User UUID
            files:         List of {"path": str, "content": str} dicts
            force_reindex: Re-index even if already indexed
            chunk_size:    Target characters per chunk
            chunk_overlap: Overlap characters between chunks

        Returns:
            Dict with task_id, status, file_count, message

        Raises:
            ValueError: If files list is empty or too large
        """
        # Validate input
        if not files:
            raise ValueError("No files provided for indexing")

        if len(files) > MAX_FILES_PER_BATCH:
            raise ValueError(
                f"Too many files: {len(files)} > {MAX_FILES_PER_BATCH} max. "
                "Split into multiple batches."
            )

        # Check total content size
        total_bytes = sum(
            len(f.get("content", "").encode("utf-8")) for f in files
        )
        if total_bytes > MAX_TOTAL_CONTENT_BYTES:
            raise ValueError(
                f"Total content too large: {total_bytes / 1024 / 1024:.1f}MB "
                f"> {MAX_TOTAL_CONTENT_BYTES / 1024 / 1024:.0f}MB max"
            )

        # Validate each file entry has required fields
        validated_files: list[dict[str, str]] = []
        for i, f in enumerate(files):
            if not isinstance(f, dict):
                raise ValueError(f"File entry {i} must be a dict")
            path = str(f.get("path", "")).strip()
            content = str(f.get("content", ""))
            if not path:
                raise ValueError(f"File entry {i} missing 'path' field")
            validated_files.append({"path": path, "content": content})

        logger.info(
            "Queuing indexing: project=%s files=%d total_mb=%.1f",
            project_id, len(validated_files),
            total_bytes / 1024 / 1024,
        )

        # Queue Celery task
        task = index_project_files.apply_async(
            kwargs={
                "project_id": project_id,
                "user_id": user_id,
                "files": validated_files,
                "force_reindex": force_reindex,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            },
            queue="low",
        )

        return {
            "task_id": task.id,
            "status": "QUEUED",
            "project_id": project_id,
            "file_count": len(validated_files),
            "total_size_mb": round(total_bytes / 1024 / 1024, 2),
            "message": (
                f"Indexing {len(validated_files)} files queued. "
                f"Poll /api/v1/indexing/{project_id}/progress for status."
            ),
            "progress_url": f"/api/v1/indexing/{project_id}/progress",
        }

    @staticmethod
    def queue_file_reindex(
        project_id: str,
        user_id: str,
        file_path: str,
        content: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> dict[str, Any]:
        """
        Queue a single file re-indexing task.

        Args:
            project_id:    Project UUID
            user_id:       User UUID
            file_path:     File path to re-index
            content:       Updated file content
            chunk_size:    Target chunk size
            chunk_overlap: Chunk overlap

        Returns:
            Dict with task_id, status, message

        Raises:
            ValueError: If content is empty
        """
        if not content or not content.strip():
            raise ValueError("File content cannot be empty for re-indexing")
        if not file_path or not file_path.strip():
            raise ValueError("file_path cannot be empty")

        task = reindex_single_file.apply_async(
            kwargs={
                "project_id": project_id,
                "user_id": user_id,
                "file_path": file_path,
                "content": content,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            },
            queue="default",
        )

        logger.info(
            "Queued re-index: project=%s file=%s task=%s",
            project_id, file_path, task.id,
        )

        return {
            "task_id": task.id,
            "status": "QUEUED",
            "project_id": project_id,
            "file_path": file_path,
            "message": f"Re-indexing '{file_path}' queued.",
        }

    @staticmethod
    def get_progress(project_id: str) -> dict[str, Any]:
        """
        Get current indexing progress for a project.

        Args:
            project_id: Project UUID

        Returns:
            Progress dict or a default "not started" response
        """
        progress = get_indexing_progress(project_id)
        if not progress:
            return {
                "project_id": project_id,
                "status": "NOT_STARTED",
                "progress": 0.0,
                "total_files": 0,
                "indexed_files": 0,
                "failed_files": 0,
                "indexed_chunks": 0,
                "current_file": None,
                "message": "No indexing task found for this project",
            }
        return progress

    @staticmethod
    def get_indexing_stats(progress: dict[str, Any]) -> dict[str, Any]:
        """
        Calculate derived statistics from a progress dict.

        Args:
            progress: Progress dict from get_progress()

        Returns:
            Stats dict with success_rate, files_per_second, eta_seconds
        """
        total = int(progress.get("total_files") or 0)
        indexed = int(progress.get("indexed_files") or 0)
        failed = int(progress.get("failed_files") or 0)
        processed = indexed + failed

        success_rate = round(indexed / max(processed, 1) * 100, 1)

        # Calculate speed
        started_str = progress.get("started_at")
        files_per_second = 0.0
        eta_seconds: float | None = None

        if started_str and processed > 0:
            try:
                started = datetime.fromisoformat(started_str)
                elapsed = (
                    datetime.now(timezone.utc) - started
                ).total_seconds()
                if elapsed > 0:
                    files_per_second = round(processed / elapsed, 2)
                    remaining = total - processed
                    if files_per_second > 0 and remaining > 0:
                        eta_seconds = round(remaining / files_per_second, 0)
            except Exception:
                pass

        return {
            "success_rate_pct": success_rate,
            "files_per_second": files_per_second,
            "eta_seconds": eta_seconds,
            "total_chunks": int(progress.get("indexed_chunks") or 0),
        }
