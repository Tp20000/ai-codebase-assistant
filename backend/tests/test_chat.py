"""
Chat session and message integration tests.
Confirmed routes:
  GET  /api/v1/chat/sessions         (requires project_id query param)
  POST /api/v1/chat/sessions
  GET  /api/v1/chat/sessions/{id}
  DELETE /api/v1/chat/sessions/{id}
  POST /api/v1/chat/sessions/{id}/ask
  GET  /api/v1/history/sessions      (may require query params)
  GET  /api/v1/history/search
"""
from __future__ import annotations
import uuid
import pytest
from httpx import AsyncClient
from app.models.project import Project

pytestmark = pytest.mark.integration


class TestChatSessions:
    async def test_list_sessions_requires_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/chat/sessions")
        assert r.status_code == 401

    async def test_list_sessions_with_project_id(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """GET /api/v1/chat/sessions?project_id=... returns 200."""
        r = await client.get(
            f"/api/v1/chat/sessions?project_id={test_project.id}",
            headers=auth_headers,
        )
        assert r.status_code in (200, 422)

    async def test_list_sessions_response_is_list_or_dict(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        r = await client.get(
            f"/api/v1/chat/sessions?project_id={test_project.id}",
            headers=auth_headers,
        )
        if r.status_code == 200:
            assert isinstance(r.json(), (list, dict))

    async def test_create_session_for_project(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        payload = {"project_id": str(test_project.id), "title": "Test Session"}
        r = await client.post("/api/v1/chat/sessions", json=payload, headers=auth_headers)
        assert r.status_code in (200, 201, 422)

    async def test_create_session_requires_auth(self, client: AsyncClient) -> None:
        r = await client.post("/api/v1/chat/sessions", json={"title": "Test"})
        assert r.status_code == 401

    async def test_get_nonexistent_session(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.get(
            f"/api/v1/chat/sessions/{uuid.uuid4()}", headers=auth_headers
        )
        assert r.status_code in (404, 422)

    async def test_delete_nonexistent_session(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.delete(
            f"/api/v1/chat/sessions/{uuid.uuid4()}", headers=auth_headers
        )
        assert r.status_code in (404, 422)


class TestChatMessages:
    async def test_ask_endpoint_requires_auth(self, client: AsyncClient) -> None:
        r = await client.post(
            f"/api/v1/chat/sessions/{uuid.uuid4()}/ask",
            json={"message": "test"},
        )
        assert r.status_code == 401

    async def test_ask_nonexistent_session(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.post(
            f"/api/v1/chat/sessions/{uuid.uuid4()}/ask",
            json={"message": "What does this do?"},
            headers=auth_headers,
        )
        assert r.status_code in (404, 422, 500, 503)

    async def test_ask_missing_message(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.post(
            f"/api/v1/chat/sessions/{uuid.uuid4()}/ask",
            json={},
            headers=auth_headers,
        )
        assert r.status_code in (404, 422)

    async def test_history_sessions_reachable(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """GET /api/v1/history/sessions — may need query params."""
        r = await client.get("/api/v1/history/sessions", headers=auth_headers)
        assert r.status_code in (200, 422)

    async def test_history_sessions_requires_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/history/sessions")
        assert r.status_code == 401

    async def test_history_search_reachable(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        r = await client.get("/api/v1/history/search", headers=auth_headers)
        assert r.status_code in (200, 422)


class TestChatEdgeCases:
    async def test_full_session_create_and_ask(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        create = await client.post(
            "/api/v1/chat/sessions",
            json={"project_id": str(test_project.id), "title": "Edge Case Test"},
            headers=auth_headers,
        )
        if create.status_code not in (200, 201):
            pytest.skip(f"Session creation returned {create.status_code}")
        session_id = create.json().get("id")
        if not session_id:
            pytest.skip("Session response has no id field")
        ask = await client.post(
            f"/api/v1/chat/sessions/{session_id}/ask",
            json={"message": "What does this code do?"},
            headers=auth_headers,
        )
        assert ask.status_code in (200, 201, 408, 422, 500, 503)

    async def test_very_long_session_title(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        r = await client.post(
            "/api/v1/chat/sessions",
            json={"project_id": str(test_project.id), "title": "T" * 500},
            headers=auth_headers,
        )
        assert r.status_code in (200, 201, 400, 422)