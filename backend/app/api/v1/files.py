"""
Files API Router — File upload and management endpoints.

Endpoints:
  POST   /api/v1/projects/{project_id}/files/upload         Upload single file
  POST   /api/v1/projects/{project_id}/files/upload-zip     Upload ZIP archive
  POST   /api/v1/projects/{project_id}/files/upload-github  Clone from GitHub
  GET    /api/v1/projects/{project_id}/files/               List project files
  GET    /api/v1/projects/{project_id}/files/{file_id}      Get file with content
  DELETE /api/v1/projects/{project_id}/files/{file_id}      Delete file
"""

import logging
from typing import Optional, Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.cache_service import get_redis
from app.services.file_service import FileService, FileUploadError
from app.services.project_service import ProjectService, ProjectNotFoundError
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.models.project import Project

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Files"])
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class GitHubUploadRequest(BaseModel):
    """Request body for GitHub repository import."""
    url: str = Field(..., description="GitHub or GitLab HTTPS URL",
                     example="https://github.com/tiangolo/fastapi")
    branch: str = Field(default="main", description="Branch to clone")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("https://github.com/") or
                v.startswith("https://gitlab.com/")):
            raise ValueError("URL must be a GitHub or GitLab HTTPS URL.")
        return v


class FileResponse(BaseModel):
    """File metadata response (without content)."""
    id: str
    project_id: str
    file_path: str
    file_name: str
    file_extension: Optional[str]
    language: Optional[str]
    size_bytes: int
    line_count: int
    is_binary: bool
    is_parsed: bool
    is_embedded: bool
    content_hash: Optional[str]
    created_at: str


class FileContentResponse(FileResponse):
    """File with content included."""
    content: Optional[str]


class UploadSummaryResponse(BaseModel):
    """Response for ZIP/GitHub upload operations."""
    uploaded: int
    skipped: int
    errors: int
    project_id: str
    message: str


class FileListResponse(BaseModel):
    """Paginated file list response."""
    items: list[FileResponse]
    total: int


class MessageResponse(BaseModel):
    message: str


# ─────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────

async def get_file_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> FileService:
    """Inject FileService."""
    return FileService(db=db, redis=redis)


async def get_project_service_dep(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> ProjectService:
    """Inject ProjectService."""
    return ProjectService(db=db, redis=redis)


async def verify_project_access(
    project_id: str,
    current_user: User = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service_dep),
) -> Project:
    """
    Dependency: verify project exists and belongs to current user.
    Uses get_current_user directly (not CurrentUser alias) to avoid
    double-Depends error with Annotated types.
    """
    try:
        return await project_service.get_project(project_id, current_user)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/files/upload",
    response_model=FileResponse,
    status_code=201,
    summary="Upload a single source file",
    description="Upload one source code file to a project. Max 10MB per file.",
)
async def upload_single_file(
    project_id: str,
    file: UploadFile = File(..., description="Source code file to upload"),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(verify_project_access),
    service: FileService = Depends(get_file_service),
) -> FileResponse:
    """Upload a single source code file to the project."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 100MB.")

    try:
        project_file = await service.upload_single_file(
            project=project,
            filename=file.filename,
            content=content,
        )
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"File upload error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="File upload failed.")

    return FileResponse(**service._file_to_dict(project_file))


@router.post(
    "/projects/{project_id}/files/upload-zip",
    response_model=UploadSummaryResponse,
    status_code=200,
    summary="Upload a ZIP archive",
    description="Upload a ZIP archive — all source files extracted and stored. Max 100MB.",
)
async def upload_zip(
    project_id: str,
    file: UploadFile = File(..., description="ZIP archive containing source code"),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(verify_project_access),
    service: FileService = Depends(get_file_service),
) -> UploadSummaryResponse:
    """Upload a ZIP archive and extract all source files."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="ZIP file too large. Max 100MB.")

    try:
        summary = await service.upload_zip(project=project, zip_content=content)
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"ZIP upload error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="ZIP upload failed.")

    return UploadSummaryResponse(
        uploaded=summary["uploaded"],
        skipped=summary["skipped"],
        errors=summary["errors"],
        project_id=summary["project_id"],
        message=f"Successfully uploaded {summary['uploaded']} files from ZIP archive.",
    )


@router.post(
    "/projects/{project_id}/files/upload-github",
    response_model=UploadSummaryResponse,
    status_code=200,
    summary="Import from GitHub repository",
    description="Clone a public GitHub repository and import all source files.",
)
async def upload_from_github(
    project_id: str,
    request: GitHubUploadRequest,
    current_user: User = Depends(get_current_user),
    project: Project = Depends(verify_project_access),
    service: FileService = Depends(get_file_service),
) -> UploadSummaryResponse:
    """Clone a GitHub repository and import all source code files."""
    try:
        summary = await service.upload_from_github(
            project=project,
            github_url=request.url,
            branch=request.branch,
        )
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"GitHub import error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="GitHub import failed.")

    return UploadSummaryResponse(
        uploaded=summary["uploaded"],
        skipped=summary["skipped"],
        errors=summary["errors"],
        project_id=summary["project_id"],
        message=f"Successfully imported {summary['uploaded']} files from GitHub.",
    )


@router.get(
    "/projects/{project_id}/files/",
    response_model=FileListResponse,
    status_code=200,
    summary="List project files",
    description="Get paginated list of all files in a project.",
)
async def list_files(
    project_id: str,
    current_user: User = Depends(get_current_user),
    project: Project = Depends(verify_project_access),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: FileService = Depends(get_file_service),
) -> FileListResponse:
    """List all files in a project."""
    result = await service.list_files(project_id=project_id, skip=skip, limit=limit)
    items = [FileResponse(**f) for f in result["items"]]
    return FileListResponse(items=items, total=result["total"])


@router.get(
    "/projects/{project_id}/files/{file_id}",
    response_model=FileContentResponse,
    status_code=200,
    summary="Get file with content",
    description="Get a specific file including its full source code content.",
)
async def get_file(
    project_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    project: Project = Depends(verify_project_access),
    service: FileService = Depends(get_file_service),
) -> FileContentResponse:
    """Get a specific file with its content."""
    f = await service.get_file_content(file_id=file_id, project_id=project_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found.")
    file_dict = service._file_to_dict(f)
    return FileContentResponse(**file_dict, content=f.content)


@router.delete(
    "/projects/{project_id}/files/{file_id}",
    response_model=MessageResponse,
    status_code=200,
    summary="Delete a file",
    description="Remove a file from the project.",
)
async def delete_file(
    project_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    project: Project = Depends(verify_project_access),
    service: FileService = Depends(get_file_service),
) -> MessageResponse:
    """Delete a specific file from the project."""
    f = await service.get_file_content(file_id=file_id, project_id=project_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found.")

    await service.file_repo.delete(file_id)
    await service._update_project_stats(project_id)

    return MessageResponse(message=f"File '{f.file_name}' deleted successfully.")