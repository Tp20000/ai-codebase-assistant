"""
Admin API - Step 37
AI Codebase Assistant v2.0

REST endpoints for API analytics and administration:
    GET /api/v1/admin/analytics/overview      - Traffic summary
    GET /api/v1/admin/analytics/endpoints     - Top endpoint stats
    GET /api/v1/admin/analytics/errors        - Recent errors
    GET /api/v1/admin/analytics/status-codes  - Status code breakdown
    GET /api/v1/admin/analytics/daily/{date}  - Daily stats
    GET /api/v1/admin/analytics/logs/{hour}   - Hourly raw logs
    GET /api/v1/admin/rate-limits             - Rate limit tier info
    POST /api/v1/admin/rate-limits/reset      - Reset a rate limit
    GET /api/v1/admin/rate-limits/status      - Check a limit status
    GET /api/v1/admin/system/info             - System information
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# =============================================================================
# Models
# =============================================================================

class RateLimitResetRequest(BaseModel):
    """Request to reset a rate limit counter."""
    tier_name: str = Field(..., description="Rate limit tier name")
    identifier: str = Field(
        ..., description="IP address (ip:x.x.x.x) or user ID (user:uuid)"
    )


# =============================================================================
# Analytics Endpoints
# =============================================================================

@router.get(
    "/analytics/overview",
    summary="API traffic overview",
    description="Returns high-level API usage statistics.",
)
async def get_analytics_overview() -> dict[str, Any]:
    """
    Return current API analytics overview.

    Combines daily stats, top endpoints, and recent errors
    into a single dashboard-ready response.

    Returns:
        Dict with today's stats, top endpoints, error count
    """
    from app.middleware.logging_middleware import get_analytics_store

    store = get_analytics_store()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    daily = store.get_daily_stats(today)
    top_endpoints = store.get_top_endpoints(limit=10)
    recent_errors = store.get_recent_errors(limit=5)
    status_codes = store.get_status_code_breakdown()

    return {
        "today": daily,
        "top_endpoints": top_endpoints,
        "recent_errors": recent_errors,
        "status_code_breakdown": status_codes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/analytics/endpoints",
    summary="Top API endpoints by request count",
)
async def get_top_endpoints(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """
    Return top N most-called API endpoints with latency stats.

    Args:
        limit: Maximum number of endpoints to return

    Returns:
        Dict with endpoints list sorted by request count
    """
    from app.middleware.logging_middleware import get_analytics_store

    store = get_analytics_store()
    endpoints = store.get_top_endpoints(limit=limit)
    return {
        "endpoints": endpoints,
        "count": len(endpoints),
    }


@router.get(
    "/analytics/endpoint/{path_group:path}",
    summary="Detailed stats for a specific endpoint",
)
async def get_endpoint_detail(path_group: str) -> dict[str, Any]:
    """
    Get detailed statistics for a specific endpoint path group.

    Args:
        path_group: URL-encoded path group e.g. /api/v1/agents

    Returns:
        Detailed endpoint stats with latency percentiles
    """
    from app.middleware.logging_middleware import get_analytics_store

    store = get_analytics_store()
    return store.get_endpoint_stats(f"/{path_group}")


@router.get(
    "/analytics/errors",
    summary="Recent API errors (4xx and 5xx)",
)
async def get_recent_errors(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """
    Return recent API errors for debugging.

    Args:
        limit: Maximum errors to return

    Returns:
        Dict with errors list and count
    """
    from app.middleware.logging_middleware import get_analytics_store

    store = get_analytics_store()
    errors = store.get_recent_errors(limit=limit)
    return {
        "errors": errors,
        "count": len(errors),
    }


@router.get(
    "/analytics/status-codes",
    summary="HTTP status code frequency breakdown",
)
async def get_status_codes() -> dict[str, Any]:
    """
    Return count of each HTTP status code seen.

    Returns:
        Dict mapping status_code -> count
    """
    from app.middleware.logging_middleware import get_analytics_store

    store = get_analytics_store()
    breakdown = store.get_status_code_breakdown()

    # Group into families
    families: dict[str, int] = {
        "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0
    }
    for code_str, count in breakdown.items():
        try:
            code = int(code_str)
            family = f"{code // 100}xx"
            if family in families:
                families[family] += count
        except ValueError:
            pass

    return {
        "by_code": breakdown,
        "by_family": families,
        "total": sum(breakdown.values()),
    }


@router.get(
    "/analytics/daily/{date}",
    summary="Daily API statistics for a specific date",
)
async def get_daily_stats(
    date: str,
) -> dict[str, Any]:
    """
    Get daily API statistics for a specific date.

    Args:
        date: Date string in YYYY-MM-DD format

    Returns:
        Daily stats dict with totals and error rates
    """
    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format '{date}'. Use YYYY-MM-DD.",
        )

    from app.middleware.logging_middleware import get_analytics_store
    return get_analytics_store().get_daily_stats(date)


@router.get(
    "/analytics/logs/{hour_key}",
    summary="Raw request logs for a specific hour",
)
async def get_hourly_logs(
    hour_key: str,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    """
    Get raw request log entries for a specific hour.

    Args:
        hour_key: Hour in YYYY-MM-DD-HH format e.g. "2024-01-15-14"
        limit:    Maximum entries to return

    Returns:
        Dict with logs list
    """
    from app.middleware.logging_middleware import get_analytics_store

    store = get_analytics_store()
    logs = store.get_hourly_logs(hour_key, limit=limit)
    return {
        "hour": hour_key,
        "count": len(logs),
        "logs": logs,
    }


# =============================================================================
# Rate Limit Admin Endpoints
# =============================================================================

@router.get(
    "/rate-limits",
    summary="List all rate limit tiers",
)
async def list_rate_limit_tiers() -> dict[str, Any]:
    """
    Return all configured rate limit tiers with their settings.

    Returns:
        Dict with tiers list
    """
    from app.middleware.rate_limiter import list_tiers
    return {"tiers": list_tiers()}


@router.post(
    "/rate-limits/reset",
    summary="Reset rate limit for an identifier",
    description="Clears the rate limit counter for a specific IP or user.",
)
async def reset_rate_limit_endpoint(
    request: RateLimitResetRequest,
) -> dict[str, Any]:
    """
    Reset the rate limit counter for a specific identifier.

    Args:
        request: RateLimitResetRequest with tier_name and identifier

    Returns:
        Success/failure confirmation
    """
    from app.middleware.rate_limiter import reset_rate_limit, TIERS

    if request.tier_name not in TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tier '{request.tier_name}'. "
                   f"Valid: {list(TIERS.keys())}",
        )

    success = reset_rate_limit(request.tier_name, request.identifier)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset rate limit (Redis error)",
        )

    return {
        "success": True,
        "tier": request.tier_name,
        "identifier": request.identifier,
        "message": f"Rate limit reset for {request.identifier} on tier {request.tier_name}",
    }


@router.get(
    "/rate-limits/status",
    summary="Check rate limit status for an identifier",
)
async def check_rate_limit_status(
    tier: str = Query(..., description="Tier name"),
    identifier: str = Query(..., description="ip:x.x.x.x or user:uuid"),
) -> dict[str, Any]:
    """
    Check current rate limit usage for an identifier.

    Args:
        tier:       Rate limit tier name
        identifier: IP or user identifier

    Returns:
        Current count, limit, and remaining quota
    """
    from app.middleware.rate_limiter import get_rate_limit_status

    return get_rate_limit_status(tier, identifier)


# =============================================================================
# System Info
# =============================================================================

@router.get(
    "/system/info",
    summary="System information and health",
)
async def get_system_info() -> dict[str, Any]:
    """
    Return system information for debugging and monitoring.

    Returns:
        Dict with Python version, environment, uptime info
    """
    import platform

    return {
        "python_version": sys.version,
        "platform": platform.system(),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "api_version": "2.0.0",
        "rate_limiting": os.getenv("RATE_LIMIT_ENABLED", "true"),
        "redis_url": (
            os.getenv("REDIS_URL", "redis://localhost:6379/0")
            .split("@")[-1]  # Remove credentials from URL
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
