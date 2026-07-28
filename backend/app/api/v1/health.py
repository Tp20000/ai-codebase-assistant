"""
Health Check API — Comprehensive service health endpoints.
Used by: Docker healthcheck, Railway, load balancers, monitoring dashboards.

Endpoints:
  GET /api/v1/health/         — All services health summary
  GET /api/v1/health/redis    — Detailed Redis metrics
  GET /api/v1/health/db       — PostgreSQL connection stats
  GET /api/v1/health/system   — Application info and config
"""

import logging
import platform
import sys
import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db, engine
from app.services.cache_service import get_redis, RedisHealthMonitor
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])

# Track application start time for uptime calculation
_start_time = time.time()


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="All services health summary",
    description="Returns health status of all critical services: PostgreSQL, Redis, Ollama.",
)
async def health_summary(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    Comprehensive health check for all services.
    Returns 200 even if some services are degraded (use 'status' field).
    """
    results: dict[str, Any] = {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "services": {},
    }

    # ── PostgreSQL ──
    try:
        start = time.perf_counter()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        pg_latency = round((time.perf_counter() - start) * 1000, 2)
        results["services"]["postgresql"] = {
            "status": "healthy",
            "latency_ms": pg_latency,
        }
    except Exception as exc:
        logger.error(f"PostgreSQL health check failed: {exc}")
        results["services"]["postgresql"] = {
            "status": "unhealthy",
            "error": str(exc),
        }
        results["status"] = "degraded"

    # ── Redis ──
    try:
        monitor = RedisHealthMonitor(redis)
        redis_health = await monitor.get_health()
        results["services"]["redis"] = {
            "status": redis_health["status"],
            "latency_ms": redis_health.get("latency_ms"),
            "version": redis_health.get("server", {}).get("version"),
            "memory_used_mb": redis_health.get("memory", {}).get("used_mb"),
        }
        if redis_health["status"] != "healthy":
            results["status"] = "degraded"
    except Exception as exc:
        logger.error(f"Redis health check failed: {exc}")
        results["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(exc),
        }
        results["status"] = "degraded"

    # ── Ollama (optional — don't degrade if not running) ──
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                results["services"]["ollama"] = {
                    "status": "healthy",
                    "models_loaded": len(models),
                    "models": [m.get("name") for m in models[:5]],
                }
            else:
                results["services"]["ollama"] = {
                    "status": "degraded",
                    "http_status": resp.status_code,
                }
    except Exception as exc:
        results["services"]["ollama"] = {
            "status": "not_running",
            "note": "Ollama is optional during development",
        }

    return results


@router.get(
    "/redis",
    status_code=status.HTTP_200_OK,
    summary="Detailed Redis health and metrics",
    description="Returns comprehensive Redis server metrics including memory, clients, ops/sec, and keyspace stats.",
)
async def redis_health(
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    Detailed Redis metrics for monitoring dashboard.
    Includes: memory usage, connected clients, hit rate, keyspace breakdown.
    """
    monitor = RedisHealthMonitor(redis)
    health = await monitor.get_health()
    keys_summary = await monitor.get_app_keys_summary()
    health["application_keys"] = keys_summary
    return health


@router.get(
    "/db",
    status_code=status.HTTP_200_OK,
    summary="PostgreSQL connection pool stats",
    description="Returns database connection pool statistics and query performance metrics.",
)
async def db_health(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    PostgreSQL health check with connection pool statistics.
    """
    start = time.perf_counter()
    try:
        result = await db.execute(
            text("SELECT version(), current_database(), current_user, pg_database_size(current_database())")
        )
        row = result.fetchone()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        pool = engine.pool
        pool_stats = {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "database": {
                "name": row[1] if row else "unknown",
                "user": row[2] if row else "unknown",
                "size_bytes": row[3] if row else 0,
                "size_mb": round(int(row[3]) / 1024 / 1024, 2) if row else 0,
                "version": (row[0] or "").split(" ")[0] if row else "unknown",
            },
            "pool": pool_stats,
        }
    except Exception as exc:
        logger.error(f"DB health check failed: {exc}")
        return {
            "status": "unhealthy",
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "error": str(exc),
        }


@router.get(
    "/system",
    status_code=status.HTTP_200_OK,
    summary="Application system information",
    description="Returns Python version, platform info, and application configuration summary.",
)
async def system_health() -> dict:
    """
    System and application metadata endpoint.
    Useful for verifying deployment version and configuration.
    """
    return {
        "application": {
            "name": settings.APP_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
            "uptime_seconds": round(time.time() - _start_time, 1),
            "api_prefix": settings.API_V1_PREFIX,
        },
        "runtime": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
        "configuration": {
            "log_level": settings.LOG_LEVEL,
            "cors_origins": settings.CORS_ORIGINS,
            "access_token_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
            "db_pool_size": settings.DB_POOL_SIZE,
            "ollama_model": settings.OLLAMA_DEFAULT_MODEL,
        },
    }
