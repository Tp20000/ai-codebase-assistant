"""
Notification endpoint integration tests.
Tests: CRUD, mark-read, unread count, clear-all.
"""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

from app.models.user import User


pytestmark = pytest.mark.integration


VALID_NOTIF = {
    "type": "success",
    "title": "Test Notification",
    "message": "This is a test notification",
    "priority": "low",
}


class TestListNotifications:
    """Tests for GET /api/v1/notifications/."""

    async def test_list_returns_200(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """GET notifications should return 200."""
        response = await client.get("/api/v1/notifications/", headers=auth_headers)
        assert response.status_code == 200

    async def test_list_returns_notifications_key(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Response must have notifications list and total."""
        response = await client.get("/api/v1/notifications/", headers=auth_headers)
        data = response.json()
        assert "notifications" in data
        assert "total" in data
        assert isinstance(data["notifications"], list)

    async def test_list_requires_auth(self, client: AsyncClient) -> None:
        """GET notifications without auth must return 401."""
        response = await client.get("/api/v1/notifications/")
        assert response.status_code == 401

    async def test_list_pagination_fields(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Response must include page and per_page."""
        response = await client.get("/api/v1/notifications/", headers=auth_headers)
        data = response.json()
        assert "page" in data
        assert "per_page" in data

    async def test_list_unread_only_filter(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """unread_only=true must return only unread notifications."""
        await client.post("/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers)
        response = await client.get(
            "/api/v1/notifications/?unread_only=true", headers=auth_headers
        )
        data = response.json()
        assert all(not n["read"] for n in data["notifications"])


class TestCreateNotification:
    """Tests for POST /api/v1/notifications/."""

    async def test_create_returns_201(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """POST notifications should return 201."""
        response = await client.post(
            "/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers
        )
        assert response.status_code == 201

    async def test_create_returns_id(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Created notification must have a UUID id."""
        response = await client.post(
            "/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers
        )
        data = response.json()
        assert "id" in data
        assert len(data["id"]) == 36

    async def test_create_sets_read_false(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """New notification must have read=False."""
        response = await client.post(
            "/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers
        )
        assert response.json()["read"] is False

    async def test_create_preserves_title(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Created notification must preserve the title."""
        payload = {**VALID_NOTIF, "title": "Unique Title XYZ"}
        response = await client.post(
            "/api/v1/notifications/", json=payload, headers=auth_headers
        )
        assert response.json()["title"] == "Unique Title XYZ"

    async def test_create_all_types(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """All valid notification types should be accepted."""
        valid_types = [
            "success", "error", "warning", "info",
            "agent_complete", "upload_complete", "indexing_complete", "chat_response",
        ]
        for notif_type in valid_types:
            payload = {**VALID_NOTIF, "type": notif_type}
            response = await client.post(
                "/api/v1/notifications/", json=payload, headers=auth_headers
            )
            assert response.status_code == 201, f"Type {notif_type} failed"

    async def test_create_requires_auth(self, client: AsyncClient) -> None:
        """POST without auth must return 401."""
        response = await client.post("/api/v1/notifications/", json=VALID_NOTIF)
        assert response.status_code == 401

    async def test_create_with_project_metadata(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Notification with project_name must preserve it."""
        payload = {**VALID_NOTIF, "project_name": "My Project", "agent_type": "bug_finder"}
        response = await client.post(
            "/api/v1/notifications/", json=payload, headers=auth_headers
        )
        data = response.json()
        assert data["project_name"] == "My Project"
        assert data["agent_type"] == "bug_finder"


class TestUnreadCount:
    """Tests for GET /api/v1/notifications/unread-count."""

    async def test_unread_count_returns_200(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Unread count endpoint should return 200."""
        response = await client.get(
            "/api/v1/notifications/unread-count", headers=auth_headers
        )
        assert response.status_code == 200

    async def test_unread_count_has_field(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Response must have unread_count field."""
        response = await client.get(
            "/api/v1/notifications/unread-count", headers=auth_headers
        )
        data = response.json()
        assert "unread_count" in data
        assert isinstance(data["unread_count"], int)

    async def test_unread_count_increases_after_create(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Creating a notification must increase unread count by 1."""
        before = (
            await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
        ).json()["unread_count"]
        await client.post("/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers)
        after = (
            await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
        ).json()["unread_count"]
        assert after == before + 1

    async def test_unread_count_zero_after_mark_all_read(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """After mark-all-read, unread count must be 0."""
        await client.post("/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers)
        await client.patch(
            "/api/v1/notifications/mark-all-read", headers=auth_headers
        )
        count = (
            await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
        ).json()["unread_count"]
        assert count == 0


class TestMarkRead:
    """Tests for PATCH /api/v1/notifications/mark-read and mark-all-read."""

    async def test_mark_all_read_returns_200(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """PATCH mark-all-read must return 200."""
        response = await client.patch(
            "/api/v1/notifications/mark-all-read", headers=auth_headers
        )
        assert response.status_code == 200

    async def test_mark_all_read_response_has_updated(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """mark-all-read response must include updated count."""
        response = await client.patch(
            "/api/v1/notifications/mark-all-read", headers=auth_headers
        )
        assert "updated" in response.json()

    async def test_mark_specific_ids_as_read(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """mark-read with specific IDs must mark them read."""
        create_resp = await client.post(
            "/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers
        )
        notif_id = create_resp.json()["id"]
        response = await client.patch(
            "/api/v1/notifications/mark-read",
            json={"notification_ids": [notif_id]},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["updated"] >= 1


class TestClearNotifications:
    """Tests for DELETE /api/v1/notifications/clear-all."""

    async def test_clear_all_returns_200(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """DELETE clear-all must return 200."""
        response = await client.delete(
            "/api/v1/notifications/clear-all", headers=auth_headers
        )
        assert response.status_code == 200

    async def test_clear_all_empties_list(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """After clear-all, notification list must be empty."""
        await client.post("/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers)
        await client.delete("/api/v1/notifications/clear-all", headers=auth_headers)
        list_resp = await client.get("/api/v1/notifications/", headers=auth_headers)
        assert list_resp.json()["total"] == 0

    async def test_clear_all_requires_auth(self, client: AsyncClient) -> None:
        """DELETE clear-all without auth must return 401."""
        response = await client.delete("/api/v1/notifications/clear-all")
        assert response.status_code == 401


class TestDeleteNotification:
    """Tests for DELETE /api/v1/notifications/{id}."""

    async def test_delete_by_id_returns_204(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """DELETE single notification must return 204."""
        create_resp = await client.post(
            "/api/v1/notifications/", json=VALID_NOTIF, headers=auth_headers
        )
        notif_id = create_resp.json()["id"]
        response = await client.delete(
            f"/api/v1/notifications/{notif_id}", headers=auth_headers
        )
        assert response.status_code == 204

    async def test_delete_nonexistent_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """DELETE non-existent notification must return 404."""
        response = await client.delete(
            f"/api/v1/notifications/{uuid.uuid4()}", headers=auth_headers
        )
        assert response.status_code == 404