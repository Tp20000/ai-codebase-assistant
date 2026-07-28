"""
Database Configuration - Async SQLAlchemy 2.0
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base - all models inherit from this."""
    pass


engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database connection pool and verify connectivity."""
    logger.info("Initializing PostgreSQL connection pool...")
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("PostgreSQL connection pool ready")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency - provides a database session per request."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as exc:
            logger.error(f"Database session error - rolling back: {exc}", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()

# Alias for compatibility
AsyncSessionLocal = async_session_factory
