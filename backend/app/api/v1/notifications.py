"""
Notifications API Router - WORKING VERSION
get_current_user returns User ORM object, NOT a dict.
Use current_user.id (attribute access), NOT current_user["id"].
AI Codebase Assistant v2.0
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationSchema(BaseModel):
    """Single notification item."""
    id: str
    type: str
    title: str
    message: str
    priority: str = "low"
    read: bool = False
    created_at: str
    metadata: Optional[dict[str, Any]] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    agent_type: Optional[str] = None
    task_id: Optional[str] = None


class NotificationListResponse(BaseModel):
    """Paginated notification list."""
    notifications: list[NotificationSchema]
    total: int
    unread_count: int
    page: int
    per_page: int


class MarkReadRequest(BaseModel):
    """IDs to mark as read."""
    notification_ids: list[str]


class CreateNotificationRequest(BaseModel):
    """Create notification payload."""
    type: str
    title: str
    message: str
    priority: str = "low"
    metadata: Optional[dict[str, Any]] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    agent_type: Optional[str] = None
    task_id: Optional[str] = None


_store: dict[str, list[dict[str, Any]]] = {}


def _get(user_id: str) -> list[dict[str, Any]]:
    """Return notification list for a user."""
    return _store.get(user_id, [])


def _add(user_id: str, notif: dict[str, Any]) -> None:
    """Add notification, max 100 per user."""
    if user_id not in _store:
        _store[user_id] = []
    _store[user_id].insert(0, notif)
    _store[user_id] = _store[user_id][:100]


@router.get("/unread-count")
async def get_unread_count(
    current_user=Depends(get_current_user),
) -> dict[str, int]:
    """Return unread notification count."""
    user_id = str(current_user.id)
    count = sum(1 for n in _get(user_id) if not n.get("read", False))
    return {"unread_count": count}


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """Return paginated notifications."""
    user_id = str(current_user.id)
    items = _get(user_id)
    if unread_only:
        items = [n for n in items if not n.get("read", False)]
    total = len(items)
    unread_count = sum(1 for n in _get(user_id) if not n.get("read", False))
    start = (page - 1) * per_page
    return NotificationListResponse(
        notifications=[NotificationSchema(**n) for n in items[start: start + per_page]],
        total=total,
        unread_count=unread_count,
        page=page,
        per_page=per_page,
    )


@router.post("/", response_model=NotificationSchema, status_code=status.HTTP_201_CREATED)
async def create_notification(
    request: CreateNotificationRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationSchema:
    """Create a new notification."""
    user_id = str(current_user.id)
    notif: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "type": request.type,
        "title": request.title,
        "message": request.message,
        "priority": request.priority,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": request.metadata,
        "project_id": request.project_id,
        "project_name": request.project_name,
        "agent_type": request.agent_type,
        "task_id": request.task_id,
    }
    _add(user_id, notif)
    logger.info("Created notification [%s] for user %s", notif["id"], user_id)
    return NotificationSchema(**notif)


@router.patch("/mark-all-read")
async def mark_all_read(
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Mark all notifications as read."""
    user_id = str(current_user.id)
    count = 0
    for n in _get(user_id):
        if not n["read"]:
            n["read"] = True
            count += 1
    return {"message": f"Marked {count} notifications as read", "updated": count}


@router.patch("/mark-read")
async def mark_notifications_read(
    request: MarkReadRequest,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Mark specific notification IDs as read."""
    user_id = str(current_user.id)
    count = 0
    for n in _get(user_id):
        if n["id"] in request.notification_ids and not n["read"]:
            n["read"] = True
            count += 1
    return {"message": f"Marked {count} notifications as read", "updated": count}


@router.delete("/clear-all")
async def clear_all_notifications(
    current_user=Depends(get_current_user),
) -> dict[str, str]:
    """Delete all notifications for current user."""
    user_id = str(current_user.id)
    count = len(_get(user_id))
    _store[user_id] = []
    return {"message": f"Cleared {count} notifications"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user=Depends(get_current_user),
) -> Response:
    """Delete one notification by ID. Returns 204."""
    user_id = str(current_user.id)
    before = len(_get(user_id))
    _store[user_id] = [n for n in _get(user_id) if n["id"] != notification_id]
    if len(_store.get(user_id, [])) == before:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification '{notification_id}' not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)