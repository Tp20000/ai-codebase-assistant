"""
Chat History REST API.

Provides endpoints for managing, searching, and exporting
conversation history. Used primarily by the frontend chat sidebar.

Endpoints:
- GET  /history/sessions              — List sessions with pagination
- GET  /history/sessions/{id}/summary — Session summary + analytics
- PUT  /history/sessions/{id}/title   — Rename a session
- GET  /history/sessions/{id}/export/markdown — Export as Markdown
- GET  /history/sessions/{id}/export/json     — Export as JSON
- GET  /history/search                — Search messages full-text
- GET  /history/analytics/project     — Project-level chat analytics
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.chat_repo import ChatRepository
from app.services.chat_service import ChatService
from app.utils.jwt_handler import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/history", tags=["history"])


# ─────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────

class UpdateTitleRequest(BaseModel):
    """Request body for renaming a chat session."""
    title: str = Field(..., min_length=1, max_length=255)


class SessionSummaryResponse(BaseModel):
    """Session summary with analytics for sidebar display."""
    model_config = ConfigDict(protected_namespaces=())

    session_id: str
    title: str
    project_id: str
    message_count: int
    created_at: str
    updated_at: str
    last_response_preview: Optional[str] = None
    analytics: dict


class PaginatedSessionsResponse(BaseModel):
    """Paginated list of session summaries."""
    sessions: list[dict]
    total: int
    limit: int
    offset: int
    has_more: bool


class SearchResponse(BaseModel):
    """Search results with matched messages."""
    results: list[dict]
    query: str
    total_returned: int


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@router.get(
    "/sessions",
    response_model=PaginatedSessionsResponse,
    summary="List chat sessions with pagination",
)
async def list_sessions(
    project_id: UUID = Query(..., description="Project to list sessions for"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    order_by: str = Query(default="updated_at", pattern="^(updated_at|created_at|title)$"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PaginatedSessionsResponse:
    """
    List all active chat sessions for a project with pagination.

    Returns sessions ordered by most recently updated by default.
    Used by the frontend chat sidebar to show conversation history.
    """
    repo = ChatRepository(db)

    sessions = await repo.list_sessions(
        project_id=project_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    total = await repo.count_sessions(
        project_id=project_id, user_id=current_user.id
    )

    session_dicts = [
        {
            "session_id": str(s.id),
            "title": s.title,
            "project_id": str(s.project_id),
            "message_count": s.message_count,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }
        for s in sessions
    ]

    return PaginatedSessionsResponse(
        sessions=session_dicts,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.get(
    "/sessions/{session_id}/summary",
    response_model=SessionSummaryResponse,
    summary="Get session summary with analytics",
)
async def get_session_summary(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SessionSummaryResponse:
    """
    Get a lightweight session summary including analytics.

    Returns session metadata, last AI response preview, and
    aggregated metrics without loading all messages.
    """
    svc = ChatService(db)
    try:
        summary = await svc.get_session_summary(
            session_id=session_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return SessionSummaryResponse(**summary)


@router.put(
    "/sessions/{session_id}/title",
    status_code=status.HTTP_200_OK,
    summary="Rename a chat session",
)
async def update_session_title(
    session_id: UUID,
    body: UpdateTitleRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    Rename a chat session with a custom title.

    Used when the user wants to override the auto-generated title
    with a more descriptive name.
    """
    repo = ChatRepository(db)
    updated = await repo.update_session_title(
        session_id=session_id,
        user_id=current_user.id,
        title=body.title,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied",
        )
    return {"session_id": str(session_id), "title": body.title}


@router.get(
    "/sessions/{session_id}/export/markdown",
    summary="Export session as Markdown",
    response_class=Response,
)
async def export_markdown(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    """
    Export the full conversation as a formatted Markdown document.

    Returns a downloadable .md file with all messages, source
    citations, and generation metrics as HTML comments.
    """
    svc = ChatService(db)
    try:
        markdown = await svc.export_session_markdown(
            session_id=session_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    filename = f"conversation-{session_id}.md"
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(markdown.encode())),
        },
    )


@router.get(
    "/sessions/{session_id}/export/json",
    summary="Export session as JSON",
)
async def export_json(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    Export the full conversation as structured JSON.

    Includes complete message history with RAG metadata,
    source chunks, timing metrics, and session analytics.
    """
    svc = ChatService(db)
    try:
        data = await svc.export_session_json(
            session_id=session_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return data


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Full-text search across chat messages",
)
async def search_messages(
    q: str = Query(..., min_length=1, max_length=500, description="Search term"),
    project_id: Optional[UUID] = Query(default=None),
    session_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SearchResponse:
    """
    Search for messages containing the query string.

    Performs case-insensitive full-text search across all of the
    user's messages. Can be scoped to a specific project or session.
    """
    repo = ChatRepository(db)
    results = await repo.search_messages(
        user_id=current_user.id,
        query=q,
        project_id=project_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return SearchResponse(
        results=results,
        query=q,
        total_returned=len(results),
    )


@router.get(
    "/analytics/project",
    summary="Project-level chat analytics",
)
async def project_analytics(
    project_id: UUID = Query(..., description="Project to analyze"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    Get aggregated chat analytics for a project.

    Returns: total conversations, message counts, prompt type
    distribution, model usage, and token consumption stats.
    Used by the Analytics dashboard page.
    """
    repo = ChatRepository(db)
    analytics = await repo.get_project_chat_analytics(
        project_id=project_id,
        user_id=current_user.id,
    )
    return {"project_id": str(project_id), **analytics}
