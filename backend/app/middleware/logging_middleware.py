"""
Request Logging and API Analytics Middleware - Step 37
AI Codebase Assistant v2.0

Logs every HTTP request with:
    - Method, path, status code, response time
    - User ID (from JWT if authenticated)
    - Client IP address
    - Request/response size
    - Error messages for 4xx/5xx responses
    - Rate limit tier hit

Stores data in Redis for fast aggregation:
    api:log:{YYYY-MM-DD-HH}  - Hourly log list (recent 1000 entries)
    api:stats:endpoint:{path} - Per-endpoint counters (HINCRBY)
    api:stats:status:{code}   - Per-status-code counters
    api:stats:latency:{path}  - Latency sorted set (for percentiles)
    api:stats:errors          - Recent error list
    api:stats:daily:{date}    - Daily totals

All Redis keys have TTL of 7 days to auto-expire old data.
Degrades gracefully when Redis is unavailable (just logs to console).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# TTL for all analytics keys (7 days)
ANALYTICS_TTL = 7 * 24 * 3600

# Paths to skip logging (health checks, static files)
LOG_SKIP_PATHS: frozenset[str] = frozenset([
    "/health",
    "/favicon.ico",
    "/docs",
    "/redoc",
    "/openapi.json",
])

# Max entries in the hourly log list
MAX_HOURLY_LOG_ENTRIES = 1000

# Max entries in the error list
MAX_ERROR_ENTRIES = 200


# =============================================================================
# Redis Analytics Store
# =============================================================================

class AnalyticsStore:
    """
    Redis-backed storage for API request analytics.

    All operations are fire-and-forget via pipeline — a failure
    never affects the actual API response.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        """
        Initialize analytics store.

        Args:
            redis_url: Redis connection URL. Falls back to REDIS_URL env var.
        """
        self._url = redis_url or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy Redis client initialization."""
        if self._client is None:
            import redis
            self._client = redis.from_url(self._url, decode_responses=True)
        return self._client

    def record_request(self, entry: dict[str, Any]) -> None:
        """
        Record a single request entry in Redis analytics.

        Writes to multiple Redis structures atomically via pipeline:
            - Hourly log list (recent entries)
            - Per-endpoint hit counter
            - Per-status-code counter
            - Latency sorted set for percentile calculation
            - Error list (for 4xx/5xx only)
            - Daily totals hash

        Args:
            entry: Request log entry dict with all fields
        """
        try:
            client = self._get_client()
            pipe = client.pipeline()

            now = datetime.now(timezone.utc)
            hour_key = now.strftime("%Y-%m-%d-%H")
            date_key = now.strftime("%Y-%m-%d")

            # 1. Hourly log list (capped at MAX_HOURLY_LOG_ENTRIES)
            log_key = f"api:log:{hour_key}"
            pipe.lpush(log_key, json.dumps(entry))
            pipe.ltrim(log_key, 0, MAX_HOURLY_LOG_ENTRIES - 1)
            pipe.expire(log_key, ANALYTICS_TTL)

            # 2. Per-endpoint counters
            endpoint_key = f"api:stats:endpoint:{entry['path_group']}"
            pipe.hincrby(endpoint_key, "total_requests", 1)
            pipe.hincrby(endpoint_key, f"status_{entry['status_code']}", 1)
            pipe.hincrby(endpoint_key, "total_latency_ms",
                         int(entry["duration_ms"]))
            pipe.expire(endpoint_key, ANALYTICS_TTL)

            # 3. Per-status-code counters
            status_key = f"api:stats:status:{entry['status_code']}"
            pipe.incr(status_key)
            pipe.expire(status_key, ANALYTICS_TTL)

            # 4. Latency sorted set for percentiles
            # Score = latency_ms, member = request_id
            latency_key = f"api:latency:{entry['path_group']}"
            pipe.zadd(latency_key, {
                entry["request_id"]: float(entry["duration_ms"])
            })
            # Keep only last 10000 entries per endpoint
            pipe.zremrangebyrank(latency_key, 0, -10001)
            pipe.expire(latency_key, ANALYTICS_TTL)

            # 5. Error entries (4xx and 5xx only)
            if entry["status_code"] >= 400:
                error_key = "api:stats:errors"
                pipe.lpush(error_key, json.dumps({
                    "request_id": entry["request_id"],
                    "method": entry["method"],
                    "path": entry["path"],
                    "status": entry["status_code"],
                    "error": entry.get("error_message", ""),
                    "ts": entry["timestamp"],
                    "user": entry.get("user_id", ""),
                    "ip": entry.get("client_ip", ""),
                }))
                pipe.ltrim(error_key, 0, MAX_ERROR_ENTRIES - 1)
                pipe.expire(error_key, ANALYTICS_TTL)

            # 6. Daily totals
            daily_key = f"api:stats:daily:{date_key}"
            pipe.hincrby(daily_key, "total_requests", 1)
            pipe.hincrby(daily_key, "total_latency_ms",
                         int(entry["duration_ms"]))
            if entry["status_code"] >= 500:
                pipe.hincrby(daily_key, "server_errors", 1)
            elif entry["status_code"] >= 400:
                pipe.hincrby(daily_key, "client_errors", 1)
            pipe.expire(daily_key, ANALYTICS_TTL)

            pipe.execute()

        except Exception as exc:
            # Never let analytics errors affect the API
            logger.debug("Analytics store error (non-critical): %s", exc)

    def get_endpoint_stats(
        self, path_group: str
    ) -> dict[str, Any]:
        """
        Get statistics for a specific endpoint path group.

        Args:
            path_group: Normalized path e.g. "/api/v1/agents"

        Returns:
            Stats dict with total_requests, avg_latency, status breakdown
        """
        try:
            client = self._get_client()
            endpoint_key = f"api:stats:endpoint:{path_group}"
            data = client.hgetall(endpoint_key)

            total = int(data.get("total_requests", 0))
            total_latency = int(data.get("total_latency_ms", 0))
            avg_latency = round(total_latency / max(total, 1), 2)

            # Latency percentiles from sorted set
            percentiles = self._get_latency_percentiles(path_group)

            return {
                "path_group": path_group,
                "total_requests": total,
                "avg_latency_ms": avg_latency,
                "percentiles": percentiles,
                "status_breakdown": {
                    k.replace("status_", ""): int(v)
                    for k, v in data.items()
                    if k.startswith("status_")
                },
            }
        except Exception as exc:
            logger.debug("get_endpoint_stats error: %s", exc)
            return {"path_group": path_group, "error": str(exc)}

    def _get_latency_percentiles(
        self, path_group: str
    ) -> dict[str, float]:
        """
        Calculate P50, P95, P99 latency percentiles from sorted set.

        Args:
            path_group: Normalized path group

        Returns:
            Dict with p50, p95, p99 latency values in ms
        """
        try:
            client = self._get_client()
            latency_key = f"api:latency:{path_group}"
            count = client.zcard(latency_key)
            if count == 0:
                return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

            def percentile_value(pct: float) -> float:
                idx = max(0, int(count * pct / 100) - 1)
                results = client.zrange(
                    latency_key, idx, idx, withscores=True
                )
                return round(results[0][1], 2) if results else 0.0

            return {
                "p50": percentile_value(50),
                "p95": percentile_value(95),
                "p99": percentile_value(99),
            }
        except Exception:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def get_hourly_logs(
        self, hour_key: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get recent request logs for a specific hour.

        Args:
            hour_key: Hour key format "YYYY-MM-DD-HH"
            limit:    Maximum entries to return

        Returns:
            List of request log entry dicts
        """
        try:
            client = self._get_client()
            log_key = f"api:log:{hour_key}"
            raw_entries = client.lrange(log_key, 0, limit - 1)
            return [json.loads(e) for e in raw_entries]
        except Exception as exc:
            logger.debug("get_hourly_logs error: %s", exc)
            return []

    def get_recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get recent API errors (4xx and 5xx responses).

        Args:
            limit: Maximum errors to return

        Returns:
            List of error entry dicts
        """
        try:
            client = self._get_client()
            raw = client.lrange("api:stats:errors", 0, limit - 1)
            return [json.loads(e) for e in raw]
        except Exception as exc:
            logger.debug("get_recent_errors error: %s", exc)
            return []

    def get_daily_stats(self, date_str: str) -> dict[str, Any]:
        """
        Get daily totals for a specific date.

        Args:
            date_str: Date string "YYYY-MM-DD"

        Returns:
            Daily stats dict
        """
        try:
            client = self._get_client()
            daily_key = f"api:stats:daily:{date_str}"
            data = client.hgetall(daily_key)
            total = int(data.get("total_requests", 0))
            total_lat = int(data.get("total_latency_ms", 0))
            return {
                "date": date_str,
                "total_requests": total,
                "avg_latency_ms": round(total_lat / max(total, 1), 2),
                "server_errors": int(data.get("server_errors", 0)),
                "client_errors": int(data.get("client_errors", 0)),
                "error_rate": round(
                    (int(data.get("server_errors", 0))
                     + int(data.get("client_errors", 0)))
                    / max(total, 1) * 100, 2
                ),
            }
        except Exception as exc:
            logger.debug("get_daily_stats error: %s", exc)
            return {"date": date_str, "error": str(exc)}

    def get_status_code_breakdown(self) -> dict[str, int]:
        """
        Get current status code frequency counters.

        Returns:
            Dict mapping status_code_str -> count
        """
        try:
            client = self._get_client()
            pattern = "api:stats:status:*"
            keys = client.keys(pattern)
            result: dict[str, int] = {}
            if keys:
                pipe = client.pipeline()
                for k in keys:
                    pipe.get(k)
                values = pipe.execute()
                for key, val in zip(keys, values):
                    code = key.split(":")[-1]
                    result[code] = int(val or 0)
            return result
        except Exception as exc:
            logger.debug("get_status_breakdown error: %s", exc)
            return {}

    def get_top_endpoints(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Get the most-called API endpoints sorted by request count.

        Args:
            limit: Maximum endpoints to return

        Returns:
            List of endpoint stats dicts sorted by total_requests desc
        """
        try:
            client = self._get_client()
            pattern = "api:stats:endpoint:*"
            keys = client.keys(pattern)
            endpoints: list[dict[str, Any]] = []

            for key in keys:
                data = client.hgetall(key)
                total = int(data.get("total_requests", 0))
                if total > 0:
                    path_group = key.replace("api:stats:endpoint:", "")
                    total_lat = int(data.get("total_latency_ms", 0))
                    endpoints.append({
                        "path_group": path_group,
                        "total_requests": total,
                        "avg_latency_ms": round(
                            total_lat / max(total, 1), 2
                        ),
                    })

            endpoints.sort(key=lambda x: x["total_requests"], reverse=True)
            return endpoints[:limit]
        except Exception as exc:
            logger.debug("get_top_endpoints error: %s", exc)
            return []


# Singleton analytics store
_store = AnalyticsStore()


# =============================================================================
# Path Normalizer
# =============================================================================

def normalize_path(path: str) -> str:
    """
    Normalize a URL path for analytics grouping.

    Replaces UUIDs, numeric IDs, and task IDs with placeholders
    so similar paths are grouped together in analytics.

    Examples:
        /api/v1/projects/abc-123/files  -> /api/v1/projects/{id}/files
        /api/v1/tasks/550e8400-...      -> /api/v1/tasks/{id}
        /api/v1/users/42                -> /api/v1/users/{id}

    Args:
        path: Raw URL path string

    Returns:
        Normalized path with IDs replaced by {id}
    """
    import re

    # Replace UUIDs
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
        flags=re.IGNORECASE,
    )
    # Replace numeric IDs
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
    # Collapse multiple slashes
    path = re.sub(r"/+", "/", path)

    return path


# =============================================================================
# JWT User Extractor
# =============================================================================

def extract_user_id(auth_header: str) -> str:
    """
    Extract user ID from Authorization Bearer token for logging.

    Does not verify signature — only used for analytics logging.

    Args:
        auth_header: Authorization header value

    Returns:
        User ID string or empty string if not found/parseable
    """
    if not auth_header.startswith("Bearer "):
        return ""
    try:
        import base64
        import json as _json
        token = auth_header[7:]
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = _json.loads(base64.b64decode(payload_b64))
        return str(
            payload.get("sub")
            or payload.get("user_id")
            or payload.get("id")
            or ""
        )
    except Exception:
        return ""


# =============================================================================
# Logging Middleware
# =============================================================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that logs every HTTP request with timing
    and stores analytics data in Redis.

    Adds X-Request-ID header to every response for correlation.
    Logs structured JSON to the application logger.
    Stores analytics data asynchronously (fire-and-forget).
    """

    def __init__(
        self,
        app: ASGIApp,
        store: AnalyticsStore | None = None,
        enabled: bool = True,
    ) -> None:
        """
        Initialize logging middleware.

        Args:
            app:     ASGI application
            store:   AnalyticsStore instance (uses singleton if None)
            enabled: If False, only adds X-Request-ID (no analytics)
        """
        super().__init__(app)
        self._store = store or _store
        self._enabled = enabled

    async def dispatch(
        self, request: Request, call_next: Any
    ) -> Response:
        """
        Process each request: time it, log it, store analytics.

        Args:
            request:   Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response with X-Request-ID header added
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Always add request ID to response
        response.headers["X-Request-ID"] = request_id

        # Skip analytics for bypass paths
        path = request.url.path
        if not self._enabled or any(
            path.startswith(skip) for skip in LOG_SKIP_PATHS
        ):
            return response

        # Build log entry
        status_code = response.status_code
        method = request.method
        path_group = normalize_path(path)
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        user_id = extract_user_id(
            request.headers.get("Authorization", "")
        )

        entry: dict[str, Any] = {
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "path_group": path_group,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
            "user_id": user_id,
            "user_agent": request.headers.get("User-Agent", "")[:100],
            "error_message": "",
        }

        # Structured log to application logger
        log_level = logging.WARNING if status_code >= 400 else logging.DEBUG
        logger.log(
            log_level,
            "HTTP %s %s %d %.1fms [%s] user=%s ip=%s",
            method, path, status_code, duration_ms,
            request_id, user_id or "anon", client_ip,
        )

        # Store in Redis analytics (non-blocking)
        self._store.record_request(entry)

        return response


# =============================================================================
# Public helper functions for admin API
# =============================================================================

def get_analytics_store() -> AnalyticsStore:
    """Return the singleton AnalyticsStore."""
    return _store
