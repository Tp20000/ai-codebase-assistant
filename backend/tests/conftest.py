"""
Shared pytest fixtures for AI Codebase Assistant backend tests.
Key design decisions:
- Creates tables directly via SQLAlchemy metadata (not alembic) for CI reliability
- NullPool: prevents asyncpg "attached to different loop" errors
- Function-scoped fixtures: avoids event_loop scope mismatch
"""

from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

# ── Import all models so metadata is populated ──────────────────────────────
from app.database import Base
import app.models.user      # noqa: F401
import app.models.project   # noqa: F401
import app.models.file      # noqa: F401
import app.models.chat      # noqa: F401
import app.models.task      # noqa: F401

from app.main import app
from app.database import get_db
from app.utils.password import hash_password
from app.utils.jwt_handler import create_access_token

# ── Database URL ─────────────────────────────────────────────────────────────
TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_codebase_test",
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_token(result) -> str:
    """Handle both str and (str, jti) return types from create_access_token."""
    if isinstance(result, tuple):
        return result[0]
    return str(result)


def _build_token(user) -> str:
    """Try all known create_access_token signatures gracefully."""
    for args in [
        (str(user.id), user.email, user.username),
        ({"sub": str(user.id), "email": user.email},),
        (str(user.id),),
    ]:
        try:
            return _extract_token(create_access_token(*args))
        except TypeError:
            continue
    raise RuntimeError("Could not build token — check create_access_token signature")


# ── Session-scoped engine (created once per test session) ────────────────────

@pytest.fixture(scope="session")
def engine():
    """Create async engine once for the whole test session."""
    return create_async_engine(TEST_DB_URL, poolclass=NullPool, echo=False)


@pytest.fixture(scope="session")
def session_factory(engine):
    """Create session factory once for the whole test session."""
    return async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )


# ── Create ALL tables before any test runs ───────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables(engine):
    """
    Drop and recreate all tables using SQLAlchemy metadata.
    This is more reliable than alembic in CI because:
    - No dependency on alembic version file state
    - No schema mismatch between alembic versions
    - Tables always match current model definitions
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Cleanup after all tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Per-test DB session ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Fresh DB session per test with automatic rollback."""
    async with session_factory() as session:
        yield session
        await session.rollback()


# ── Override FastAPI dependency ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient with DB dependency overridden to use test database.
    Tables are guaranteed to exist (created by create_tables fixture).
    """
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Auth fixtures ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a unique test user directly in the database."""
    from app.models.user import User

    uid = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        email=f"pytest_{uid}@test.com",
        username=f"pytest_{uid}",
        hashed_password=hash_password("TestPass123!"),
        full_name="Pytest User",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict:
    """Return Authorization headers for the test user."""
    token = _build_token(test_user)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, auth_headers: dict) -> AsyncClient:
    """AsyncClient with Authorization header pre-set."""
    client.headers.update(auth_headers)
    return client


# ── Project fixture ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_project(db_session: AsyncSession, test_user):
    """Create a test project owned by test_user."""
    from app.models.project import Project

    project = Project(
        id=uuid.uuid4(),
        name=f"Test Project {uuid.uuid4().hex[:6]}",
        description="A project created for testing",
        owner_id=test_user.id,
        status="active",
        language="python",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project