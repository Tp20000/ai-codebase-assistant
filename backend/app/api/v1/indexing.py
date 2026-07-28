"""
Indexing API Router - Step 29
AI Codebase Assistant v2.0

REST endpoints for codebase indexing:
    POST /api/v1/indexing/{project_id}/start
        Queue full project indexing

    POST /api/v1/indexing/{project_id}/reindex-file
        Queue single file re-indexing

    GET  /api/v1/indexing/{project_id}/progress
        Poll indexing progress from Redis

    GET  /api/v1/indexing/{project_id}/stats
        Get derived statistics (speed, ETA, success rate)

    DELETE /api/v1/indexing/{project_id}/cancel
        Cancel a running indexing task
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.indexing_service import IndexingService
from app.tasks.indexing_tasks import get_indexing_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/indexing", tags=["indexing"])


# =============================================================================
# Request / Response Models
# =============================================================================

class FileEntry(BaseModel):
    """A single file to be indexed."""

    path: str = Field(..., description="Relative file path e.g. 'src/main.py'")
    content: str = Field(..., description="Raw file content string")


class IndexingStartRequest(BaseModel):
    """Request body for starting a project indexing task."""

    user_id: str = Field(..., description="User UUID")
    files: list[FileEntry] = Field(
        ...,
        min_length=1,
        description="List of files to index",
    )
    force_reindex: bool = Field(
        default=False,
        description="Re-index files even if already indexed",
    )
    chunk_size: int = Field(
        default=1000,
        ge=100,
        le=4000,
        description="Target chunk size in characters",
    )
    chunk_overlap: int = Field(
        default=200,
        ge=0,
        le=500,
        description="Overlap characters between consecutive chunks",
    )


class ReindexFileRequest(BaseModel):
    """Request body for re-indexing a single file."""

    user_id: str = Field(..., description="User UUID")
    file_path: str = Field(..., description="File path to re-index")
    content: str = Field(..., min_length=1, description="Updated file content")
    chunk_size: int = Field(default=1000, ge=100, le=4000)
    chunk_overlap: int = Field(default=200, ge=0, le=500)


class IndexingQueuedResponse(BaseModel):
    """Response when indexing is successfully queued."""

    task_id: str
    status: str
    project_id: str
    file_count: int | None = None
    message: str
    progress_url: str | None = None


class IndexingProgressResponse(BaseModel):
    """Response for progress polling endpoint."""

    task_id: str | None
    project_id: str
    status: str
    progress: float
    total_files: int
    indexed_files: int
    failed_files: int
    indexed_chunks: int
    current_file: str | None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    file_results: list[dict[str, Any]] | None = None


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/{project_id}/start",
    response_model=IndexingQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue full project indexing",
    description=(
        "Queue all project files for background indexing into ChromaDB. "
        "Returns immediately with task_id. "
        "Poll GET /{project_id}/progress for real-time status."
    ),
)
async def start_indexing(
    project_id: str,
    request: IndexingStartRequest,
) -> IndexingQueuedResponse:
    """
    Queue a full project indexing task.

    Args:
        project_id: Project UUID from URL path
        request:    IndexingStartRequest with files list

    Returns:
        IndexingQueuedResponse with task_id and progress URL
    """
    try:
        files = [
            {"path": f.path, "content": f.content}
            for f in request.files
        ]
        result = IndexingService.queue_project_indexing(
            project_id=project_id,
            user_id=request.user_id,
            files=files,
            force_reindex=request.force_reindex,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
        return IndexingQueuedResponse(
            task_id=result["task_id"],
            status=result["status"],
            project_id=project_id,
            file_count=result["file_count"],
            message=result["message"],
            progress_url=result.get("progress_url"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "Failed to queue indexing: project=%s error=%s",
            project_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue indexing task: {exc}",
        )


@router.post(
    "/{project_id}/reindex-file",
    response_model=IndexingQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-index a single file",
)
async def reindex_file(
    project_id: str,
    request: ReindexFileRequest,
) -> IndexingQueuedResponse:
    """
    Queue a single file re-indexing task.

    Removes existing chunks for the file and re-indexes
    with updated content.

    Args:
        project_id: Project UUID
        request:    ReindexFileRequest with file_path and content

    Returns:
        IndexingQueuedResponse with task_id
    """
    try:
        result = IndexingService.queue_file_reindex(
            project_id=project_id,
            user_id=request.user_id,
            file_path=request.file_path,
            content=request.content,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
        return IndexingQueuedResponse(
            task_id=result["task_id"],
            status=result["status"],
            project_id=project_id,
            message=result["message"],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "Failed to queue re-index: project=%s file=%s error=%s",
            project_id, request.file_path, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue re-index: {exc}",
        )


@router.get(
    "/{project_id}/progress",
    response_model=IndexingProgressResponse,
    summary="Get indexing progress",
    description=(
        "Poll this endpoint to get real-time indexing progress. "
        "Data is stored in Redis and updated after every file. "
        "Frontend should poll every 1-2 seconds while status=RUNNING."
    ),
)
async def get_progress(project_id: str) -> IndexingProgressResponse:
    """
    Get real-time indexing progress for a project.

    Args:
        project_id: Project UUID

    Returns:
        IndexingProgressResponse with current status and file counts
    """
    progress = IndexingService.get_progress(project_id)

    return IndexingProgressResponse(
        task_id=progress.get("task_id"),
        project_id=project_id,
        status=progress.get("status", "NOT_STARTED"),
        progress=float(progress.get("progress", 0.0)),
        total_files=int(progress.get("total_files", 0)),
        indexed_files=int(progress.get("indexed_files", 0)),
        failed_files=int(progress.get("failed_files", 0)),
        indexed_chunks=int(progress.get("indexed_chunks", 0)),
        current_file=progress.get("current_file"),
        started_at=progress.get("started_at"),
        completed_at=progress.get("completed_at"),
        error=progress.get("error"),
        file_results=progress.get("file_results"),
    )


@router.get(
    "/{project_id}/stats",
    summary="Get indexing statistics",
)
async def get_stats(project_id: str) -> dict[str, Any]:
    """
    Get derived indexing statistics for a project.

    Args:
        project_id: Project UUID

    Returns:
        Dict with progress + derived stats (speed, ETA, success rate)
    """
    progress = IndexingService.get_progress(project_id)
    stats = IndexingService.get_indexing_stats(progress)

    return {
        **progress,
        "stats": stats,
    }


@router.delete(
    "/{project_id}/cancel",
    summary="Cancel running indexing task",
)
async def cancel_indexing(project_id: str) -> dict[str, str]:
    """
    Attempt to cancel a running indexing task.

    Looks up the task_id from Redis progress and sends
    a Celery revoke signal.

    Args:
        project_id: Project UUID

    Returns:
        Confirmation message dict
    """
    progress = get_indexing_progress(project_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No indexing task found for project {project_id}",
        )

    task_id = progress.get("task_id")
    if not task_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No task_id found in indexing progress",
        )

    current_status = progress.get("status")
    if current_status in ("COMPLETED", "FAILED"):
        return {
            "task_id": task_id,
            "message": f"Task already {current_status} — nothing to cancel",
        }

    try:
        from app.tasks.celery_app import celery_app
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        logger.info(
            "Indexing task revoked: project=%s task=%s",
            project_id, task_id,
        )
        return {
            "task_id": task_id,
            "message": "Indexing task cancel signal sent",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel task: {exc}",
        )
