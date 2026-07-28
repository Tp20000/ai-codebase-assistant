"""
Projects API Router - Full CRUD for project management.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.project_service import ProjectService, ProjectError, ProjectNotFoundError
from app.middleware.auth_middleware import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["Projects"])

SUPPORTED_LANGUAGES = {
    "python", "javascript", "typescript", "java",
    "cpp", "go", "rust", "ruby", "php", "csharp", "mixed",
}


class CreateProjectRequest(BaseModel):
    """Request body for creating a project."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    language: str = Field(default="python")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language '{v}'.")
        return v

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class UpdateProjectRequest(BaseModel):
    """Request body for updating a project."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    language: Optional[str] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.lower().strip()
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language '{v}'.")
        return v


class ProjectResponse(BaseModel):
    """Project data response."""
    id: str
    name: str
    description: Optional[str] = None
    language: str
    status: str
    file_count: int
    total_size_bytes: int
    owner_id: str
    created_at: str
    updated_at: str
    indexed_at: Optional[str] = None

    @classmethod
    def from_project(cls, p) -> "ProjectResponse":
        """Build response from Project ORM instance."""
        # Use getattr with fallbacks for computed properties
        language = getattr(p, 'effective_language', None) or getattr(p, 'language', 'python')
        file_count = getattr(p, 'effective_file_count', None) or getattr(p, 'file_count', 0) or 0
        return cls(
            id=str(p.id),
            name=p.name,
            description=p.description,
            language=language,
            status=p.status,
            file_count=file_count,
            total_size_bytes=getattr(p, 'total_size_bytes', 0) or 0,
            owner_id=str(p.owner_id),
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
            indexed_at=p.indexed_at.isoformat() if p.indexed_at else None,
        )


class PaginatedProjectsResponse(BaseModel):
    """Paginated list of projects."""
    items: list[ProjectResponse]
    total: int
    page: int
    size: int
    pages: int


class StatsResponse(BaseModel):
    """Project statistics."""
    total: int
    total_files: int
    by_status: dict[str, int]


class MessageResponse(BaseModel):
    """Generic success message."""
    message: str


def get_project_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectService:
    """
    FastAPI dependency that returns a ProjectService instance.
    Redis is optional - service degrades gracefully without it.
    """
    return ProjectService(db=db)


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=201,
    summary="Create a new project",
)
async def create_project(
    request: CreateProjectRequest,
    current_user: CurrentUser,
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    """Create a new codebase project for the authenticated user."""
    try:
        project = await service.create_project(
            name=request.name,
            owner=current_user,
            description=request.description,
            language=request.language,
        )
    except ProjectError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error("Create project error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create project: {exc}")
    return ProjectResponse.from_project(project)


@router.get(
    "/stats",
    response_model=StatsResponse,
    status_code=200,
    summary="Get project statistics",
)
async def get_stats(
    current_user: CurrentUser,
    service: ProjectService = Depends(get_project_service),
) -> StatsResponse:
    """Get aggregate statistics for the current user's projects."""
    stats = await service.get_project_stats(owner=current_user)
    return StatsResponse(**stats)


@router.get(
    "",
    response_model=PaginatedProjectsResponse,
    include_in_schema=False,
)
@router.get(
    "/",
    response_model=PaginatedProjectsResponse,
    status_code=200,
    summary="List user projects",
)
async def list_projects(
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    service: ProjectService = Depends(get_project_service),
) -> PaginatedProjectsResponse:
    """List all projects owned by the current user with pagination."""
    result = await service.list_projects(owner=current_user, page=page, size=size)
    items = [ProjectResponse(**item) for item in result["items"]]
    return PaginatedProjectsResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=200,
    summary="Get project by ID",
)
async def get_project(
    project_id: str,
    current_user: CurrentUser,
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    """Get a specific project by ID. Only the owner can access."""
    try:
        project = await service.get_project(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ProjectResponse.from_project(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=200,
    summary="Update project",
)
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    current_user: CurrentUser,
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    """Update project name, description, or language."""
    try:
        project = await service.update_project(
            project_id=project_id,
            owner=current_user,
            name=request.name,
            description=request.description,
            language=request.language,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProjectError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ProjectResponse.from_project(project)


@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    status_code=200,
    summary="Delete project",
)
async def delete_project(
    project_id: str,
    current_user: CurrentUser,
    service: ProjectService = Depends(get_project_service),
) -> MessageResponse:
    """Delete a project and all associated files, embeddings, and chat sessions."""
    try:
        await service.delete_project(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return MessageResponse(message=f"Project '{project_id}' deleted successfully.")
