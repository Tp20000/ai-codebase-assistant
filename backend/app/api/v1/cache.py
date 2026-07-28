"""
Cache Management API.

Provides endpoints for monitoring and managing the Redis cache:
- GET  /cache/stats       — Cache hit/miss statistics
- POST /cache/invalidate  — Invalidate project cache
- POST /cache/clear       — Clear all cache (admin only)
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.cache_service import cache_service
from app.utils.jwt_handler import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cache", tags=["cache"])


class InvalidateRequest(BaseModel):
    """Request to invalidate cache for a project."""
    project_id: UUID = Field(..., description="Project to invalidate cache for")


class InvalidateResponse(BaseModel):
    """Response from cache invalidation."""
    project_id: str
    keys_invalidated: int
    message: str


@router.get(
    "/stats",
    summary="Get cache performance statistics",
    description="Returns Redis cache hit/miss counters, hit rate, and total cached keys.",
)
async def get_cache_stats(
    current_user=Depends(get_current_user),
) -> dict:
    """Get cache hit/miss statistics and connection health."""
    if not cache_service.is_connected:
        connected = await cache_service.connect()
        if not connected:
            return {
                "connected": False,
                "message": "Redis is not available. Caching is disabled.",
            }

    return await cache_service.get_cache_stats()


@router.post(
    "/invalidate",
    response_model=InvalidateResponse,
    summary="Invalidate cache for a project",
    description="Clears all cached RAG responses for a project. Call this after re-indexing a project's codebase.",
)
async def invalidate_project_cache(
    body: InvalidateRequest,
    current_user=Depends(get_current_user),
) -> InvalidateResponse:
    """Invalidate all cached responses for a specific project."""
    if not cache_service.is_connected:
        await cache_service.connect()

    count = await cache_service.invalidate_project_cache(str(body.project_id))

    return InvalidateResponse(
        project_id=str(body.project_id),
        keys_invalidated=count,
        message=f"Invalidated {count} cached response(s)",
    )


@router.post(
    "/clear",
    summary="Clear ALL cached responses",
    description="Clears the entire RAG cache. Use with caution in production.",
)
async def clear_all_cache(
    current_user=Depends(get_current_user),
) -> dict:
    """Clear all cached RAG responses from Redis."""
    if not cache_service.is_connected:
        await cache_service.connect()

    count = await cache_service.clear_all()
    return {
        "keys_cleared": count,
        "message": f"Cleared {count} cached entries",
    }
