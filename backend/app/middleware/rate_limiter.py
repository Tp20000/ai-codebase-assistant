"""
Rate Limiting Middleware - Step 36
AI Codebase Assistant v2.0

Production-grade sliding window rate limiter using Redis.

Algorithm: Sliding Window Counter
    - Redis ZADD + ZREMRANGEBYSCORE for O(log n) per request
    - Window slides continuously (not fixed 1-minute buckets)
    - No "burst at boundary" problem of fixed windows

Rate Limit Tiers:
    auth        - 10 req/min per IP  (login/register protection)
    agents      - 20 req/min per user (expensive AI operations)
    analytics   - 60 req/min per user (read-heavy analytics)
    uploads     - 5  req/min per user (file upload protection)
    api_default - 100 req/min per IP  (general API endpoints)
    websocket   - 30 connections/min per IP

Headers returned on every response:
    X-RateLimit-Limit:     requests allowed per window
    X-RateLimit-Remaining: requests left in current window
    X-RateLimit-Reset:     Unix timestamp when window resets
    Retry-After:           seconds to wait (only on 429)

Graceful degradation:
    If Redis is unavailable, rate limiting is SKIPPED (fail open).
    This ensures the API stays available even if Redis goes down.
    A warning is logged on every Redis failure.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


# =============================================================================
# Rate Limit Tiers
# =============================================================================

@dataclass(frozen=True)
class RateLimitTier:
    """
    Configuration for a rate limit tier.

    Attributes:
        name:          Human-readable tier name
        requests:      Maximum requests allowed per window
        window_seconds: Sliding window size in seconds
        by_user:       If True, limit per user_id; else per IP
    """
    name: str
    requests: int
    window_seconds: int
    by_user: bool = False

    @property
    def window_ms(self) -> int:
        """Window size in milliseconds (for Redis ZADD timestamps)."""
        return self.window_seconds * 1000


# Default tiers
TIERS: dict[str, RateLimitTier] = {
    "auth": RateLimitTier(
        name="auth",
        requests=10,
        window_seconds=60,
        by_user=False,
    ),
    "agents": RateLimitTier(
        name="agents",
        requests=20,
        window_seconds=60,
        by_user=True,
    ),
    "tasks": RateLimitTier(
        name="tasks",
        requests=30,
        window_seconds=60,
        by_user=True,
    ),
    "analytics": RateLimitTier(
        name="analytics",
        requests=60,
        window_seconds=60,
        by_user=True,
    ),
    "uploads": RateLimitTier(
        name="uploads",
        requests=5,
        window_seconds=60,
        by_user=True,
    ),
    "indexing": RateLimitTier(
        name="indexing",
        requests=10,
        window_seconds=60,
        by_user=True,
    ),
    "websocket": RateLimitTier(
        name="websocket",
        requests=30,
        window_seconds=60,
        by_user=False,
    ),
    "api_default": RateLimitTier(
        name="api_default",
        requests=100,
        window_seconds=60,
        by_user=False,
    ),
}

# URL path prefix -> tier name mapping
PATH_TIER_MAP: list[tuple[str, str]] = [
    # Order matters: more specific paths first
    ("/api/v1/auth/",         "auth"),
    ("/api/v1/agents",        "agents"),
    ("/api/v1/tasks",         "tasks"),
    ("/api/v1/indexing",      "indexing"),
    ("/api/v1/analytics",     "analytics"),
    ("/api/v1/files",         "uploads"),
    ("/api/v1/ws/",           "websocket"),
    ("/api/v1/",              "api_default"),
]

# Paths to completely bypass rate limiting
BYPASS_PATHS: frozenset[str] = frozenset([
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
])


# =============================================================================
# Sliding Window Counter
# =============================================================================

class SlidingWindowCounter:
    """
    Redis-backed sliding window rate limit counter.

    Uses a Redis sorted set per (tier, identifier) key:
        - Score = timestamp in milliseconds
        - Member = unique request ID (timestamp + random suffix)
        - ZREMRANGEBYSCORE removes expired entries on each check
        - ZADD + ZCARD gives current window count

    This is O(log n) per request where n is requests in window.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        """
        Initialize the counter with Redis connection.

        Args:
            redis_url: Redis URL string. If None, reads from
                       REDIS_URL environment variable.
        """
        self._url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Any = None

    def _get_client(self) -> Any:
        """
        Get or create Redis client (lazy initialization).

        Returns:
            Redis client instance
        """
        if self._client is None:
            import redis
            self._client = redis.from_url(self._url, decode_responses=True)
        return self._client

    def check_and_increment(
        self,
        tier: RateLimitTier,
        identifier: str,
    ) -> dict[str, Any]:
        """
        Check rate limit and increment counter atomically.

        Uses a Redis pipeline to ensure atomicity:
            1. Remove entries older than window_ms
            2. Count current entries
            3. Add new entry if under limit
            4. Set key TTL to window_seconds + 1 buffer

        Args:
            tier:       RateLimitTier configuration
            identifier: Unique key (IP or user_id)

        Returns:
            Dict with:
                allowed   (bool)  True if request is permitted
                remaining (int)   Requests remaining this window
                reset_at  (float) Unix timestamp when window resets
                count     (int)   Current request count
                limit     (int)   Maximum allowed per window
        """
        key = f"rl:{tier.name}:{identifier}"
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - tier.window_ms
        reset_at = (now_ms + tier.window_ms) / 1000  # Unix timestamp

        try:
            client = self._get_client()
            pipe = client.pipeline()

            # Remove expired entries (older than window start)
            pipe.zremrangebyscore(key, 0, window_start_ms)
            # Get current count (before adding new entry)
            pipe.zcard(key)
            # Add new entry with current timestamp as score
            member = f"{now_ms}:{identifier[:8]}"
            pipe.zadd(key, {member: now_ms})
            # Set TTL so key auto-expires
            pipe.expire(key, tier.window_seconds + 1)

            results = pipe.execute()
            current_count = int(results[1])  # count BEFORE this request

            allowed = current_count < tier.requests
            remaining = max(0, tier.requests - current_count - 1)

            if not allowed:
                # Remove the entry we just added (request is rejected)
                pipe2 = client.pipeline()
                pipe2.zrem(key, member)
                pipe2.execute()
                remaining = 0

            return {
                "allowed": allowed,
                "remaining": remaining,
                "reset_at": reset_at,
                "count": current_count + (1 if allowed else 0),
                "limit": tier.requests,
                "window_seconds": tier.window_seconds,
            }

        except Exception as exc:
            logger.warning(
                "Rate limiter Redis error (failing open): %s", exc
            )
            # Fail open: allow request when Redis is down
            return {
                "allowed": True,
                "remaining": tier.requests,
                "reset_at": reset_at,
                "count": 0,
                "limit": tier.requests,
                "window_seconds": tier.window_seconds,
                "redis_error": str(exc),
            }

    def get_status(
        self,
        tier: RateLimitTier,
        identifier: str,
    ) -> dict[str, Any]:
        """
        Get current rate limit status without incrementing.

        Args:
            tier:       RateLimitTier configuration
            identifier: Key (IP or user_id)

        Returns:
            Status dict with count, remaining, reset_at
        """
        key = f"rl:{tier.name}:{identifier}"
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - tier.window_ms
        reset_at = (now_ms + tier.window_ms) / 1000

        try:
            client = self._get_client()
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start_ms)
            pipe.zcard(key)
            results = pipe.execute()
            count = int(results[1])

            return {
                "tier": tier.name,
                "identifier": identifier,
                "count": count,
                "limit": tier.requests,
                "remaining": max(0, tier.requests - count),
                "reset_at": reset_at,
                "window_seconds": tier.window_seconds,
            }

        except Exception as exc:
            logger.warning("Rate limiter status error: %s", exc)
            return {
                "tier": tier.name,
                "identifier": identifier,
                "count": 0,
                "limit": tier.requests,
                "remaining": tier.requests,
                "reset_at": reset_at,
                "window_seconds": tier.window_seconds,
                "error": str(exc),
            }

    def reset(self, tier_name: str, identifier: str) -> bool:
        """
        Reset the rate limit counter for a specific identifier.

        Used by admin endpoints to unblock specific IPs or users.

        Args:
            tier_name:  Tier name e.g. "auth"
            identifier: IP or user_id to reset

        Returns:
            True if reset succeeded, False on error
        """
        key = f"rl:{tier_name}:{identifier}"
        try:
            client = self._get_client()
            client.delete(key)
            logger.info(
                "Rate limit reset: tier=%s identifier=%s",
                tier_name, identifier
            )
            return True
        except Exception as exc:
            logger.error("Rate limit reset failed: %s", exc)
            return False


# Singleton counter instance
_counter = SlidingWindowCounter()


# =============================================================================
# Helper: extract identifier from request
# =============================================================================

def _get_identifier(request: Request, tier: RateLimitTier) -> str:
    """
    Extract the rate limit identifier from a request.

    For user-based tiers: extract user_id from Authorization header.
    For IP-based tiers: use client IP address.

    Args:
        request: FastAPI Request object
        tier:    RateLimitTier configuration

    Returns:
        Identifier string (IP address or user_id)
    """
    if tier.by_user:
        # Try to extract user ID from JWT Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                # Decode JWT without verification for rate limiting
                # (signature verification happens in auth middleware)
                import base64
                import json as _json
                payload_b64 = token.split(".")[1]
                # Add padding if needed
                padding = 4 - len(payload_b64) % 4
                if padding != 4:
                    payload_b64 += "=" * padding
                payload = _json.loads(base64.b64decode(payload_b64))
                user_id = str(payload.get("sub") or payload.get("user_id") or "")
                if user_id:
                    return f"user:{user_id}"
            except Exception:
                pass  # Fall through to IP-based

    # IP-based: check X-Forwarded-For (behind proxy) then client host
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        # Take the first IP (client IP, not proxy IPs)
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = (
            request.client.host if request.client else "unknown"
        )

    return f"ip:{client_ip}"


def _get_tier_for_path(path: str) -> RateLimitTier:
    """
    Look up the rate limit tier for a URL path.

    Iterates PATH_TIER_MAP in order (most specific first).

    Args:
        path: URL path string e.g. "/api/v1/agents/run"

    Returns:
        RateLimitTier for this path
    """
    for prefix, tier_name in PATH_TIER_MAP:
        if path.startswith(prefix):
            return TIERS[tier_name]
    return TIERS["api_default"]


def _should_bypass(path: str, method: str) -> bool:
    """
    Check if a request should bypass rate limiting entirely.

    Args:
        path:   URL path
        method: HTTP method

    Returns:
        True if request should skip rate limit check
    """
    # Bypass static paths
    for bypass_path in BYPASS_PATHS:
        if path.startswith(bypass_path):
            return True

    # Bypass OPTIONS (CORS preflight)
    if method == "OPTIONS":
        return True

    # Only rate-limit API paths
    if not path.startswith("/api/"):
        return True

    return False


# =============================================================================
# FastAPI Middleware
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enforces sliding window rate limits.

    Intercepts every request, checks rate limits, and either:
        - Passes through with rate limit headers on the response
        - Returns 429 Too Many Requests with Retry-After header

    Fails open: if Redis is unavailable, all requests are allowed.
    """

    def __init__(
        self,
        app: ASGIApp,
        counter: SlidingWindowCounter | None = None,
        enabled: bool = True,
    ) -> None:
        """
        Initialize the middleware.

        Args:
            app:     ASGI application
            counter: SlidingWindowCounter instance (uses singleton if None)
            enabled: If False, middleware is a no-op (useful for testing)
        """
        super().__init__(app)
        self._counter = counter or _counter
        self._enabled = enabled

    async def dispatch(
        self, request: Request, call_next: Any
    ) -> Response:
        """
        Process each HTTP request through the rate limiter.

        Args:
            request:   Incoming HTTP request
            call_next: Next middleware/handler in the chain

        Returns:
            HTTP response with rate limit headers
        """
        path = request.url.path
        method = request.method

        # Skip rate limiting for bypass paths
        if not self._enabled or _should_bypass(path, method):
            return await call_next(request)

        # Determine tier and identifier
        tier = _get_tier_for_path(path)
        identifier = _get_identifier(request, tier)

        # Check + increment counter
        result = self._counter.check_and_increment(tier, identifier)

        # Build standard rate limit headers
        headers = {
            "X-RateLimit-Limit": str(result["limit"]),
            "X-RateLimit-Remaining": str(result["remaining"]),
            "X-RateLimit-Reset": str(int(result["reset_at"])),
            "X-RateLimit-Window": str(result["window_seconds"]) + "s",
            "X-RateLimit-Tier": tier.name,
        }

        if not result["allowed"]:
            retry_after = int(result["reset_at"] - time.time()) + 1
            headers["Retry-After"] = str(max(1, retry_after))

            logger.warning(
                "Rate limit exceeded: tier=%s identifier=%s path=%s",
                tier.name, identifier, path,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "error": "too_many_requests",
                    "tier": tier.name,
                    "limit": result["limit"],
                    "window_seconds": result["window_seconds"],
                    "retry_after_seconds": max(1, retry_after),
                    "message": (
                        f"Too many requests. Limit: {result['limit']} "
                        f"per {result['window_seconds']}s. "
                        f"Retry after {max(1, retry_after)}s."
                    ),
                },
                headers=headers,
            )

        # Request allowed — process and add headers to response
        response = await call_next(request)

        # Add rate limit headers to successful responses
        for key, value in headers.items():
            response.headers[key] = value

        return response


# =============================================================================
# Admin API helpers
# =============================================================================

def get_rate_limit_status(
    tier_name: str,
    identifier: str,
) -> dict[str, Any]:
    """
    Get current rate limit status for an identifier.

    Args:
        tier_name:  Tier name from TIERS dict
        identifier: IP or user_id string

    Returns:
        Status dict from SlidingWindowCounter.get_status()
    """
    if tier_name not in TIERS:
        return {"error": f"Unknown tier: {tier_name}"}
    return _counter.get_status(TIERS[tier_name], identifier)


def reset_rate_limit(
    tier_name: str,
    identifier: str,
) -> bool:
    """
    Reset rate limit counter for an identifier.

    Args:
        tier_name:  Tier name
        identifier: IP or user_id to reset

    Returns:
        True on success
    """
    return _counter.reset(tier_name, identifier)


def list_tiers() -> list[dict[str, Any]]:
    """
    Return all configured rate limit tiers.

    Returns:
        List of tier config dicts
    """
    return [
        {
            "name": tier.name,
            "requests": tier.requests,
            "window_seconds": tier.window_seconds,
            "by_user": tier.by_user,
            "description": f"{tier.requests} req/{tier.window_seconds}s per "
                           + ("user" if tier.by_user else "IP"),
        }
        for tier in TIERS.values()
    ]
