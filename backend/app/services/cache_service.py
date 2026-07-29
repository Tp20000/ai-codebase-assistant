"""
Cache Service - Redis with SSL support for Upstash (rediss://)

Compatibility exports:
- cache_service              -> singleton instance
- CacheService               -> main service class
- RedisService               -> alias for CacheService
- get_redis()                -> compatibility function
- RedisHealthMonitor         -> compatibility health helper

This file is intentionally backward-compatible with older imports used in:
- app.main
- app.api.v1.health
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from redis import asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore[assignment]
    REDIS_AVAILABLE = False
    logger.warning("redis package not installed; caching disabled")


class CacheService:
    """Redis cache service with graceful degradation."""

    def __init__(self) -> None:
        self._redis: Optional[Any] = None
        self._connected: bool = False

    async def connect(self) -> bool:
        """
        Connect to Redis.

        Returns:
            bool: True if connected, False otherwise.
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis package unavailable - caching disabled")
            self._connected = False
            return False

        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            logger.warning("REDIS_URL not set - caching disabled")
            self._connected = False
            return False

        try:
            if redis_url.startswith("rediss://"):
                self._redis = aioredis.from_url(
                    redis_url,
                    socket_connect_timeout=10,
                    socket_timeout=10,
                    ssl=True,
                    ssl_cert_reqs=None,
                    decode_responses=True,
                )
            elif redis_url.startswith("redis://") or redis_url.startswith("unix://"):
                self._redis = aioredis.from_url(
                    redis_url,
                    socket_connect_timeout=10,
                    socket_timeout=10,
                    decode_responses=True,
                )
            else:
                logger.warning(
                    "Redis URL must specify one of the following schemes "
                    "(redis://, rediss://, unix://)"
                )
                self._redis = None
                self._connected = False
                return False

            await self._redis.ping()
            self._connected = True
            logger.info("Redis connected successfully")
            return True

        except Exception as exc:
            logger.warning(f"Redis connection failed (caching disabled): {exc}")
            self._redis = None
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception as exc:
                logger.debug(f"Redis close warning: {exc}")
            finally:
                self._redis = None
                self._connected = False

    async def init(self) -> bool:
        """Backward-compatible alias for connect()."""
        return await self.connect()

    async def close(self) -> None:
        """Backward-compatible alias for disconnect()."""
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Return whether Redis is connected."""
        return self._connected and self._redis is not None

    async def get_client(self) -> Optional[Any]:
        """Return the Redis client, connecting first if needed."""
        if self._redis is None:
            await self.connect()
        return self._redis

    async def get(self, key: str) -> Optional[Any]:
        """Get JSON value from cache."""
        if not self.is_connected:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug(f"Cache get error for key '{key}': {exc}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set JSON value in cache with TTL in seconds."""
        if not self.is_connected:
            return False
        try:
            payload = json.dumps(value, default=str)
            await self._redis.setex(key, ttl, payload)
            return True
        except Exception as exc:
            logger.debug(f"Cache set error for key '{key}': {exc}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a cache key."""
        if not self.is_connected:
            return False
        try:
            await self._redis.delete(key)
            return True
        except Exception as exc:
            logger.debug(f"Cache delete error for key '{key}': {exc}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching a pattern."""
        if not self.is_connected:
            return 0
        try:
            keys = await self._redis.keys(pattern)
            if not keys:
                return 0
            await self._redis.delete(*keys)
            return len(keys)
        except Exception as exc:
            logger.debug(f"Cache delete_pattern error for '{pattern}': {exc}")
            return 0

    async def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        if not self.is_connected:
            return False
        try:
            return bool(await self._redis.exists(key))
        except Exception as exc:
            logger.debug(f"Cache exists error for key '{key}': {exc}")
            return False

    async def health_check(self) -> dict[str, Any]:
        """Return Redis health status."""
        if not self.is_connected:
            return {
                "status": "unavailable",
                "connected": False,
                "message": "Redis not connected",
            }

        try:
            pong = await self._redis.ping()
            return {
                "status": "healthy" if pong else "unhealthy",
                "connected": bool(pong),
                "message": "Redis reachable" if pong else "Redis ping failed",
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "connected": False,
                "message": str(exc),
            }


class RedisHealthMonitor:
    """Compatibility helper used by health endpoint."""

    @staticmethod
    async def check() -> dict[str, Any]:
        """Return Redis health payload."""
        return await cache_service.health_check()

    @staticmethod
    async def get_status() -> dict[str, Any]:
        """Alias for check()."""
        return await cache_service.health_check()

    @staticmethod
    async def health() -> dict[str, Any]:
        """Alias for check()."""
        return await cache_service.health_check()


async def get_redis() -> Optional[Any]:
    """
    Compatibility function used by older imports.

    Returns:
        Redis client if available, otherwise None.
    """
    client = await cache_service.get_client()
    return client


# Singleton instance used across the app
cache_service = CacheService()

# Alias kept for compatibility with previous code
RedisService = CacheService