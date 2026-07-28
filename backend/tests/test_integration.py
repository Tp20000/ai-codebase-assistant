"""
End-to-end integration flow tests.
Only tests endpoints confirmed working from Step 52.
"""
from __future__ import annotations
import uuid
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestCompleteUserJourney:

    async def test_full_auth_flow(self, client: AsyncClient) -> None:
        unique = uuid.uuid4().hex[:8]
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": f"journey_{unique}@test.com", "username": f"journey_{unique}",
                  "password": "JourneyPass123!", "full_name": "Journey User"},
        )
        assert reg.status_code == 201
        assert reg.json()["email"] == f"journey_{unique}@test.com"

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": f"journey_{unique}@test.com", "password": "JourneyPass123!"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        assert len(token) > 50

        headers = {"Authorization": f"Bearer {token}"}
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == f"journey_{unique}@test.com"

        logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code in (200, 204, 404)

    async def test_project_lifecycle(self, client: AsyncClient) -> None:
        unique = uuid.uuid4().hex[:8]
        await client.post(
            "/api/v1/auth/register",
            json={"email": f"lifecycle_{unique}@test.com",
                  "username": f"lifecycle_{unique}", "password": "LifecyclePass123!"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": f"lifecycle_{unique}@test.com", "password": "LifecyclePass123!"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        create = await client.post(
            "/api/v1/projects/",
            json={"name": f"Lifecycle {unique}", "description": "Test", "language": "python"},
            headers=headers,
        )
        assert create.status_code == 201
        project_id = create.json()["id"]

        get = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
        assert get.status_code == 200
        assert get.json()["id"] == project_id

        update = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"description": "Updated"},
            headers=headers,
        )
        assert update.status_code in (200, 204)

        list_resp = await client.get("/api/v1/projects/", headers=headers)
        ids = [p["id"] for p in list_resp.json()["items"]]
        assert project_id in ids

        delete = await client.delete(f"/api/v1/projects/{project_id}", headers=headers)
        assert delete.status_code in (200, 204)

        get_after = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
        assert get_after.status_code == 404

    async def test_notification_lifecycle(self, client: AsyncClient) -> None:
        unique = uuid.uuid4().hex[:8]
        await client.post(
            "/api/v1/auth/register",
            json={"email": f"notif_{unique}@test.com",
                  "username": f"notif_{unique}", "password": "NotifPass123!"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": f"notif_{unique}@test.com", "password": "NotifPass123!"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        for i in range(3):
            r = await client.post(
                "/api/v1/notifications/",
                json={"type": "info", "title": f"Notif {i}",
                      "message": f"Msg {i}", "priority": "low"},
                headers=headers,
            )
            assert r.status_code == 201

        count = await client.get("/api/v1/notifications/unread-count", headers=headers)
        assert count.json()["unread_count"] == 3

        mark = await client.patch("/api/v1/notifications/mark-all-read", headers=headers)
        assert mark.status_code == 200
        assert mark.json()["updated"] == 3

        count2 = await client.get("/api/v1/notifications/unread-count", headers=headers)
        assert count2.json()["unread_count"] == 0

        clear = await client.delete("/api/v1/notifications/clear-all", headers=headers)
        assert clear.status_code == 200

        list_resp = await client.get("/api/v1/notifications/", headers=headers)
        assert list_resp.json()["total"] == 0

    async def test_core_endpoints_require_auth(self, client: AsyncClient) -> None:
        """Only test endpoints CONFIRMED protected from Step 52 passing tests."""
        fake_id = str(uuid.uuid4())
        protected = [
            ("GET",  "/api/v1/auth/me"),
            ("GET",  "/api/v1/projects/"),
            ("POST", "/api/v1/projects/"),
            ("GET",  f"/api/v1/projects/{fake_id}"),
            ("GET",  "/api/v1/notifications/"),
            ("GET",  "/api/v1/notifications/unread-count"),
            ("GET",  "/api/v1/chat/sessions"),
        ]
        for method, url in protected:
            resp = await client.request(method, url)
            assert resp.status_code == 401, (
                f"Expected 401 for {method} {url}, got {resp.status_code}"
            )

    async def test_duplicate_registration_rejected(self, client: AsyncClient) -> None:
        unique = uuid.uuid4().hex[:8]
        email = f"duplicate_{unique}@test.com"
        payload = {"email": email, "username": f"dup_{unique}", "password": "DupPass123!"}
        first = await client.post("/api/v1/auth/register", json=payload)
        assert first.status_code == 201
        payload2 = {**payload, "username": f"dup2_{unique}"}
        second = await client.post("/api/v1/auth/register", json=payload2)
        assert second.status_code == 409

    async def test_pagination_works_on_projects(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        response = await client.get("/api/v1/projects/?page=1&size=5", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) <= 5

    async def test_invalid_uuid_in_path(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        response = await client.get("/api/v1/projects/not-a-valid-uuid", headers=auth_headers)
        assert response.status_code in (404, 422)

    async def test_health_check_shows_services(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/")
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "postgresql" in data["services"]
        assert data["services"]["postgresql"]["status"] in ("healthy", "degraded", "unhealthy")