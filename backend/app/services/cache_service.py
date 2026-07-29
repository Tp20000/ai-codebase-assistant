"""
Cache Service - Redis with SSL support for Upstash (rediss://)
Exports both cache_service instance and RedisService class for compatibility.
"""

import os
import logging
from typing import Optional, Any
import json

logger = logging.getLogger(__name__)

# Try to import redis
try:
    from redis import asyncio as aioredis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis package not installed")


class CacheService:
    """
    Redis cache service with Upstash SSL support.
    Gracefully degrades when Redis is unavailable.
    """

    def __init__(self) -> None:
        self._redis: Optional[Any] = None
        self._connected: bool = False

    async def init(self) -> None:
        """Initialize Redis connection."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis package not available - caching disabled")
            return

        redis_url = os.getenv("REDIS_URL", "")
        if not redis_url:
            logger.warning("REDIS_URL not set - caching disabled")
            return

        try:
            # Handle rediss:// (SSL) for Upstash
            if redis_url.startswith("rediss://"):
                self._redis = aioredis.from_url(
                    redis_url,
                    socket_connect_timeout=10,
                    socket_timeout=10,
                    ssl=True,
                    ssl_cert_reqs=None,
                )
            else:
                self._redis = aioredis.from_url(
                    redis_url,
                    socket_connect_timeout=10,
                    socket_timeout=10,
                )

            await self._redis.ping()
            self._connected = True
            logger.info("Redis connected successfully")

        except Exception as e:
            logger.warning(f"Redis connection failed (caching disabled): {e}")
            self._redis = None
            self._connected = False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._redis:
            return None
        try:
            val = await self._redis.get(key)
            if val is None:
                return None
            return json.loads(val)
        except Exception as e:
            logger.debug(f"Cache get error for {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300,
    ) -> bool:
        """Set value in cache with TTL."""
        if not self._redis:
            return False
        try:
            serialized = json.dumps(value, default=str)
            await self._redis.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.debug(f"Cache set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self._redis:
            return False
        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Cache delete error for {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        if not self._redis:
            return 0
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                await self._redis.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.debug(f"Cache delete_pattern error for {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self._redis:
            return False
        try:
            return bool(await self._redis.exists(key))
        except Exception:
            return False

    async def health_check(self) -> dict:
        """Return Redis health status."""
        if not self._redis:
            return {"status": "unavailable", "connected": False}
        try:
            await self._redis.ping()
            return {"status": "healthy", "connected": True}
        except Exception as e:
            return {"status": "unhealthy", "connected": False, "error": str(e)}


# ── Singleton instance ────────────────────────────────────────────────────────
# Exported as 'cache_service' for backward compatibility with main.py
cache_service = CacheService()

# Also export class alias for any code using RedisService
RedisService = CacheService