"""
Main FastAPI application entry point.
AI Codebase Assistant v2.0
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── CORS origins ──────────────────────────────────────────────────────────────
import json as _json

_raw_cors = os.getenv("CORS_ORIGINS", "")
if _raw_cors and _raw_cors not in ("*", '["*"]'):
    try:
        _cors_origins = _json.loads(_raw_cors)
    except Exception:
        _cors_origins = [o.strip() for o in _raw_cors.split(",") if o.strip()]
else:
    _cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "https://ai-codebase-assistant-git-main-tirths-projects-9c208144.vercel.app",
    ]

logger.info("CORS origins: %s", _cors_origins)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    logger.info("Starting AI Codebase Assistant v2.0...")

    # Redis (optional)
    try:
        from app.services.cache_service import cache_service
        ok = await cache_service.connect()
        if ok:
            logger.info("Redis connected")
        else:
            logger.warning("Redis unavailable - running without cache")
    except Exception as exc:
        logger.warning("Redis init skipped: %s", exc)

    yield

    # Shutdown
    try:
        from app.services.cache_service import cache_service
        await cache_service.disconnect()
    except Exception:
        pass
    logger.info("Shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Codebase Assistant",
    description="AI-powered codebase analysis and chat platform",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    redirect_slashes=False,
    lifespan=lifespan,
)

# ── CORS middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "Accept", "Origin"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
    max_age=3600,
)

# ── Security middleware (safe, non-blocking) ──────────────────────────────────
try:
    from app.middleware.security import (
        SecurityHeadersMiddleware,
        RequestIDMiddleware,
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware,
        environment=os.getenv("ENVIRONMENT", "production"),
    )
    logger.info("Security middleware loaded")
except Exception as exc:
    logger.warning("Security middleware skipped: %s", exc)

# ── Routers ───────────────────────────────────────────────────────────────────
PREFIX = "/api/v1"

# Import and register each router individually with error isolation
def _include(router, prefix: str, **kwargs) -> None:
    try:
        app.include_router(router, prefix=prefix, **kwargs)
    except Exception as exc:
        logger.error("Failed to register router %s: %s", prefix, exc)

try:
    from app.api.v1.health import router as health_router
    _include(health_router, PREFIX)
except Exception as exc:
    logger.error("health router: %s", exc)

try:
    from app.api.v1.auth import router as auth_router
    _include(auth_router, PREFIX)
except Exception as exc:
    logger.error("auth router: %s", exc)

try:
    from app.api.v1.projects import router as projects_router
    _include(projects_router, PREFIX)
except Exception as exc:
    logger.error("projects router: %s", exc)

try:
    from app.api.v1.files import router as files_router
    _include(files_router, PREFIX)
except Exception as exc:
    logger.error("files router: %s", exc)

try:
    from app.api.v1.chat import router as chat_router
    _include(chat_router, PREFIX)
except Exception as exc:
    logger.error("chat router: %s", exc)

try:
    from app.api.v1.llm import router as llm_router
    _include(llm_router, PREFIX)
except Exception as exc:
    logger.error("llm router: %s", exc)

try:
    from app.api.v1.agents import router as agents_router
    _include(agents_router, PREFIX)
except Exception as exc:
    logger.error("agents router: %s", exc)

try:
    from app.api.v1.analytics import router as analytics_router
    _include(analytics_router, PREFIX)
except Exception as exc:
    logger.error("analytics router: %s", exc)

try:
    from app.api.v1.websocket import router as websocket_router
    _include(websocket_router, PREFIX)
except Exception as exc:
    logger.error("websocket router: %s", exc)

# Load remaining routers silently
_optional_routers = [
    ("app.api.v1.prompts",       "prompts_router"),
    ("app.api.v1.history",       "history_router"),
    ("app.api.v1.cache",         "cache_router"),
    ("app.api.v1.parser",        "parser_router"),
    ("app.api.v1.tasks",         "tasks_router"),
    ("app.api.v1.indexing",      "indexing_router"),
    ("app.api.v1.progress_ws",   "progress_ws_router"),
    ("app.api.v1.notifications", "notifications_router"),
    ("app.api.v1.admin",         "admin_router"),
]

for module_path, attr_name in _optional_routers:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        router = getattr(mod, attr_name, None)
        if router is not None:
            _include(router, PREFIX)
    except Exception:
        pass


# ── Root endpoint ──────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    """Service info."""
    return {
        "name": "AI Codebase Assistant",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
    }


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )