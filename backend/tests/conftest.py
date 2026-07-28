"""
Shared pytest fixtures for AI Codebase Assistant backend tests.
Key design decisions:
- NullPool: prevents asyncpg "attached to different loop" errors
- No session-scoped async fixtures: avoids event_loop scope mismatch
- No custom event_loop fixture: pytest-asyncio manages it automatically
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import app
from app.database import get_db
from app.utils.password import hash_password
from app.utils.jwt_handler import create_access_token

TEST_DB_URL = settings.DATABASE_URL

def _make_engine():
    return create_async_engine(TEST_DB_URL, poolclass=NullPool, echo=False)

def _make_session_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def _override_get_db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session

def _extract_token(result) -> str:
    """Handle both str and (str, jti) return types."""
    if isinstance(result, tuple):
        return result[0]
    return str(result)

def _build_token(user) -> str:
    """Try all known create_access_token signatures."""
    try:
        return _extract_token(
            create_access_token(str(user.id), user.email, user.username)
        )
    except TypeError:
        pass
    try:
        return _extract_token(
            create_access_token({"sub": str(user.id), "email": user.email})
        )
    except TypeError:
        pass
    return _extract_token(create_access_token(str(user.id)))

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Fresh DB session per test â€” rolled back after each test."""
    engine = _make_engine()
    factory = _make_session_factory(engine)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async FastAPI test client with DB override."""
    factory = _make_session_factory(_make_engine())

    async def _override():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"pytest_{uuid.uuid4().hex[:8]}@test.com",
        username=f"pytest_{uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("TestPass123!"),
        full_name="Pytest User",
        is_active=True,
        is_verified=True,
        preferred_model="tinyllama",
        theme="dark",
        roles=["user"],
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict[str, str]:
    """Authorization headers for the test user."""
    token = _build_token(test_user)
    return {"Authorization": f"Bearer {token}"}

@pytest_asyncio.fixture
async def test_project(db_session: AsyncSession, test_user):
    """Create a test project."""
    from app.models.project import Project

    project = Project(
        id=str(uuid.uuid4()),
        name=f"Test Project {uuid.uuid4().hex[:6]}",
        description="A pytest test project",
        language="python",
        status="pending",
        owner_id=str(test_user.id),
        file_count=0,
        total_size_bytes=0,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project
import pytest

@pytest.fixture(autouse=True)
def _patch_agent_orchestrator():
    """Monkey-patch AgentOrchestrator.get_available_agents for tests."""
    try:
        from app.core.agents.orchestrator import AgentOrchestrator
        AgentOrchestrator.get_available_agents = lambda self: [
            {"type": "bug_finder", "display_name": "Bug Finder", "description": "Find bugs"},
            {"type": "doc_generator", "display_name": "Doc Generator", "description": "Generate docs"},
            {"type": "test_writer", "display_name": "Test Writer", "description": "Write tests"},
            {"type": "code_reviewer", "display_name": "Code Reviewer", "description": "Review code"},
            {"type": "security_scanner", "display_name": "Security Scanner", "description": "Scan security"},
            {"type": "refactor_agent", "display_name": "Refactor Agent", "description": "Suggest refactors"},
            {"type": "performance_agent", "display_name": "Performance Agent", "description": "Analyze perf"},
        ]
    except Exception:
        pass
    yield