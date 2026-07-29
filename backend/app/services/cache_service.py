"""
Redis Service with proper SSL support for rediss:// URLs (Upstash)
"""

import os
import logging
from typing import Optional
from redis import asyncio as aioredis
from redis.exceptions import RedisError, ConnectionError

logger = logging.getLogger(__name__)

class RedisService:
    """Redis service with robust connection handling."""

    _redis: Optional[aioredis.Redis] = None

    @classmethod
    async def get_redis(cls) -> aioredis.Redis:
        """Get or create Redis connection with proper SSL handling."""
        if cls._redis is None:
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                logger.warning("REDIS_URL not set. Redis disabled.")
                raise ConnectionError("Redis URL not configured")

            try:
                # Handle both redis:// and rediss:// URLs
                if redis_url.startswith("rediss://"):
                    cls._redis = aioredis.from_url(
                        redis_url,
                        socket_connect_timeout=10,
                        socket_timeout=10,
                        ssl=True,
                        ssl_cert_reqs=None,  # Upstash uses self-signed certs
                    )
                else:
                    cls._redis = aioredis.from_url(
                        redis_url,
                        socket_connect_timeout=10,
                        socket_timeout=10,
                    )

                # Test connection
                await cls._redis.ping()
                logger.info("✅ Redis connected successfully")
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                cls._redis = None
                raise

        return cls._redis

    @classmethod
    async def close(cls):
        """Close Redis connection."""
        if cls._redis:
            await cls._redis.close()
            cls._redis = None