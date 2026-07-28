"""
Rate Limiter — Sliding Window Algorithm using Redis Sorted Sets.

Algorithm:
  1. Use a sorted set where score = timestamp and member = unique request ID
  2. On each request: remove entries older than window, count remaining, add new
  3. If count >= limit: reject request
  4. Set TTL on the sorted set to auto-cleanup

Why sliding window over fixed window:
  - Fixed window: 100 req at 0:59 + 100 req at 1:01 = 200 req in 2 seconds (burst!)
  - Sliding window: always enforces exactly N requests per window period
  - Used by: Stripe, GitHub, Google Cloud APIs

This implementation uses a Lua script for atomic operations
(prevents race conditions in multi-worker deployments).
"""

import logging
import time
import uuid
from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.services.cache_service import RedisKeys

logger = logging.getLogger(__name__)

# Lua script for atomic sliding window rate limit check
# Returns: [current_count, limit, window_seconds, allowed(1/0)]
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local request_id = ARGV[4]

-- Remove requests outside the sliding window
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window * 1000)

-- Count requests in current window
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add this request with current timestamp as score
    redis.call('ZADD', key, now, request_id)
    -- Set TTL to auto-cleanup the sorted set
    redis.call('PEXPIRE', key, window * 1000)
    return {count + 1, limit, window, 1}
else
    return {count, limit, window, 0}
end
"""


class RateLimiter:
    """
    Sliding window rate limiter using Redis sorted sets.
    Thread-safe via atomic Lua script execution.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        limit: int = 60,
        window: int = 60,
        key_prefix: str = "default",
    ) -> None:
        """
        Initialize rate limiter.

        Args:
            redis: Async Redis client
            limit: Maximum requests allowed per window
            window: Time window in seconds
            key_prefix: Namespace prefix for Redis keys
        """
        self.redis = redis
        self.limit = limit
        self.window = window
        self.key_prefix = key_prefix

    async def check(self, identifier: str) -> dict:
        """
        Check if a request is allowed under the rate limit.

        Args:
            identifier: Unique identifier (IP address, user_id, API key)

        Returns:
            Dictionary with: allowed, count, limit, window, retry_after_seconds
        """
        now_ms = int(time.time() * 1000)
        window_key = RedisKeys.format(
            RedisKeys.RATE_LIMIT,
            identifier=f"{self.key_prefix}:{identifier}",
            window=str(self.window),
        )
        request_id = str(uuid.uuid4())

        try:
            result = await self.redis.eval(
                SLIDING_WINDOW_LUA,
                1,
                window_key,
                now_ms,
                self.window,
                self.limit,
                request_id,
            )
            count, limit, window, allowed = result
            remaining = max(0, int(limit) - int(count))

            return {
                "allowed": bool(allowed),
                "count": int(count),
                "limit": int(limit),
                "remaining": remaining,
                "window_seconds": int(window),
                "retry_after_seconds": int(window) if not allowed else 0,
            }
        except Exception as exc:
            # Fail open — allow request if Redis is unavailable
            # Log error but don't block legitimate traffic
            logger.error(f"Rate limiter error (failing open): {exc}")
            return {
                "allowed": True,
                "count": 0,
                "limit": self.limit,
                "remaining": self.limit,
                "window_seconds": self.window,
                "retry_after_seconds": 0,
            }

    async def reset(self, identifier: str) -> bool:
        """
        Reset rate limit for an identifier (admin use).

        Args:
            identifier: The identifier to reset

        Returns:
            True if key was deleted
        """
        window_key = RedisKeys.format(
            RedisKeys.RATE_LIMIT,
            identifier=f"{self.key_prefix}:{identifier}",
            window=str(self.window),
        )
        result = await self.redis.delete(window_key)
        return result > 0


class RateLimitMiddleware:
    """
    FastAPI dependency factory for rate limiting endpoints.

    Usage:
        @router.post("/login")
        async def login(
            request: Request,
            _: None = Depends(RateLimitMiddleware.auth_limit()),
        ):
    """

    @staticmethod
    def create(limit: int = 60, window: int = 60, key_prefix: str = "api"):
        """
        Create a FastAPI Depends()-compatible rate limit checker.

        Args:
            limit: Max requests per window
            window: Window size in seconds
            key_prefix: Redis key namespace

        Returns:
            Async dependency function
        """
        async def _check_rate_limit(request: Request) -> None:
            """Check rate limit and raise 429 if exceeded."""
            from app.services.cache_service import get_redis
            redis = await get_redis()
            limiter = RateLimiter(redis, limit=limit, window=window, key_prefix=key_prefix)

            # Use IP address as identifier (use user_id for authenticated endpoints)
            client_ip = (
                request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or request.client.host
                or "unknown"
            )

            result = await limiter.check(identifier=client_ip)

            # Always add rate limit headers to response
            request.state.rate_limit = result

            if not result["allowed"]:
                logger.warning(
                    f"Rate limit exceeded: ip={client_ip}, "
                    f"count={result['count']}, limit={result['limit']}"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Rate limit exceeded.",
                        "limit": result["limit"],
                        "window_seconds": result["window_seconds"],
                        "retry_after_seconds": result["retry_after_seconds"],
                    },
                    headers={
                        "X-RateLimit-Limit": str(result["limit"]),
                        "X-RateLimit-Remaining": str(result["remaining"]),
                        "X-RateLimit-Window": str(result["window_seconds"]),
                        "Retry-After": str(result["retry_after_seconds"]),
                    },
                )

        return _check_rate_limit

    # Pre-configured limiters for common use cases
    @staticmethod
    def auth_limit():
        """Strict limit for auth endpoints: 10 requests per minute."""
        return RateLimitMiddleware.create(limit=10, window=60, key_prefix="auth")

    @staticmethod
    def api_limit():
        """Standard API limit: 60 requests per minute."""
        return RateLimitMiddleware.create(limit=60, window=60, key_prefix="api")

    @staticmethod
    def upload_limit():
        """Strict limit for file uploads: 5 per minute."""
        return RateLimitMiddleware.create(limit=5, window=60, key_prefix="upload")
