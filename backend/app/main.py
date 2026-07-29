from __future__ import annotations

"""
Main FastAPI application entry point.
AI Codebase Assistant v2.0
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.security import SecurityHeadersMiddleware, RequestIDMiddleware, InputSanitizationMiddleware
from app.middleware.security_config import get_security_config
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.services.cache_service import cache_service

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.projects import router as projects_router
from app.api.v1.files import router as files_router
from app.api.v1.llm import router as llm_router
from app.api.v1.chat import router as chat_router
from app.api.v1.prompts import router as prompts_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.history import router as history_router
from app.api.v1.cache import router as cache_router
from app.api.v1.parser import router as parser_router
from app.api.v1.agents import router as agents_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.indexing import router as indexing_router
from app.api.v1.progress_ws import router as progress_ws_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.admin import router as admin_router
from app.api.v1.analytics import router as analytics_router

logger = logging.getLogger(__name__)



SECURITY_CONFIG = get_security_config()
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting AI Codebase Assistant v%s...", settings.VERSION)
    await init_db()
    redis_ok = await cache_service.connect()
    if redis_ok:
        logger.info("Redis cache connected")
    else:
        logger.warning("Redis unavailable - running without cache")
    yield
    await cache_service.disconnect()
    logger.info("Shutdown complete")


app = FastAPI(
    redirect_slashes=False,
    title="AI Codebase Assistant",
    description="AI-powered codebase analysis and question answering",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SECURITY_CONFIG["cors"]["allow_origins"],
    allow_credentials=SECURITY_CONFIG["cors"]["allow_credentials"],
    allow_methods=SECURITY_CONFIG["cors"]["allow_methods"],
    allow_headers=SECURITY_CONFIG["cors"]["allow_headers"],
    expose_headers=SECURITY_CONFIG["cors"]["expose_headers"],
    max_age=SECURITY_CONFIG["cors"]["max_age"],
)
async def root() -> dict:
    """Root endpoint - API info."""
    return {
        "name": "AI Codebase Assistant",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
    }