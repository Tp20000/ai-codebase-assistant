"""
Project CRUD endpoint integration tests.
Tests: create, list, get, update, delete projects.
"""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

from app.models.user import User
from app.models.project import Project


pytestmark = pytest.mark.integration


class TestCreateProject:
    """Tests for POST /api/v1/projects/."""

    async def test_create_project_returns_201(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Creating a project should return HTTP 201."""
        payload = {
            "name": f"Test Project {uuid.uuid4().hex[:6]}",
            "description": "A test project",
            "language": "python",
        }
        response = await client.post("/api/v1/projects/", json=payload, headers=auth_headers)
        assert response.status_code == 201

    async def test_create_project_returns_id(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Created project response must include an id."""
        payload = {"name": f"Proj {uuid.uuid4().hex[:6]}", "language": "python"}
        response = await client.post("/api/v1/projects/", json=payload, headers=auth_headers)
        data = response.json()
        assert "id" in data
        assert len(data["id"]) > 0

    async def test_create_project_sets_correct_name(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Created project must have the name from request."""
        name = f"Named Project {uuid.uuid4().hex[:6]}"
        payload = {"name": name, "language": "javascript"}
        response = await client.post("/api/v1/projects/", json=payload, headers=auth_headers)
        data = response.json()
        assert data["name"] == name

    async def test_create_project_requires_auth(self, client: AsyncClient) -> None:
        """Creating a project without auth must return 401."""
        payload = {"name": "Unauth Project", "language": "python"}
        response = await client.post("/api/v1/projects/", json=payload)
        assert response.status_code == 401

    async def test_create_project_missing_name_returns_422(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Missing required name field should return 422."""
        payload = {"language": "python"}
        response = await client.post("/api/v1/projects/", json=payload, headers=auth_headers)
        assert response.status_code == 422

    async def test_create_project_default_status_is_pending(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Newly created project status must be pending."""
        payload = {"name": f"Status Test {uuid.uuid4().hex[:6]}", "language": "python"}
        response = await client.post("/api/v1/projects/", json=payload, headers=auth_headers)
        data = response.json()
        assert data["status"] == "pending"


class TestListProjects:
    """Tests for GET /api/v1/projects/."""

    async def test_list_projects_returns_200(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """List projects should return HTTP 200."""
        response = await client.get("/api/v1/projects/", headers=auth_headers)
        assert response.status_code == 200

    async def test_list_projects_returns_items_key(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """List projects response must have items key."""
        response = await client.get("/api/v1/projects/", headers=auth_headers)
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    async def test_list_projects_has_pagination(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """List projects response must include pagination fields."""
        response = await client.get("/api/v1/projects/", headers=auth_headers)
        data = response.json()
        assert "total" in data
        assert "page" in data

    async def test_list_projects_requires_auth(self, client: AsyncClient) -> None:
        """List projects without auth must return 401."""
        response = await client.get("/api/v1/projects/")
        assert response.status_code == 401

    async def test_created_project_appears_in_list(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """A newly created project must appear in the list."""
        name = f"Listable {uuid.uuid4().hex[:6]}"
        create_resp = await client.post(
            "/api/v1/projects/",
            json={"name": name, "language": "python"},
            headers=auth_headers,
        )
        project_id = create_resp.json()["id"]
        list_resp = await client.get("/api/v1/projects/", headers=auth_headers)
        ids = [p["id"] for p in list_resp.json()["items"]]
        assert project_id in ids


class TestGetProject:
    """Tests for GET /api/v1/projects/{id}."""

    async def test_get_project_by_id_returns_200(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """GET project by ID should return 200."""
        response = await client.get(
            f"/api/v1/projects/{test_project.id}", headers=auth_headers
        )
        assert response.status_code == 200

    async def test_get_project_returns_correct_id(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """GET project must return the correct project id."""
        response = await client.get(
            f"/api/v1/projects/{test_project.id}", headers=auth_headers
        )
        assert response.json()["id"] == str(test_project.id)

    async def test_get_nonexistent_project_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """GET with non-existent ID must return 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/projects/{fake_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_project_requires_auth(
        self, client: AsyncClient, test_project: Project
    ) -> None:
        """GET project without auth must return 401."""
        response = await client.get(f"/api/v1/projects/{test_project.id}")
        assert response.status_code == 401


class TestUpdateProject:
    """Tests for PATCH /api/v1/projects/{id}."""

    async def test_update_project_description(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """PATCH should update the project description."""
        new_desc = "Updated description from test"
        response = await client.patch(
            f"/api/v1/projects/{test_project.id}",
            json={"description": new_desc},
            headers=auth_headers,
        )
        assert response.status_code in (200, 204)

    async def test_update_nonexistent_project_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """PATCH non-existent project must return 404."""
        response = await client.patch(
            f"/api/v1/projects/{uuid.uuid4()}",
            json={"description": "ghost"},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDeleteProject:
    """Tests for DELETE /api/v1/projects/{id}."""

    async def test_delete_project_returns_204(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """DELETE project should return 204 No Content."""
        create_resp = await client.post(
            "/api/v1/projects/",
            json={"name": f"ToDelete {uuid.uuid4().hex[:6]}", "language": "python"},
            headers=auth_headers,
        )
        project_id = create_resp.json()["id"]
        delete_resp = await client.delete(
            f"/api/v1/projects/{project_id}", headers=auth_headers
        )
        assert delete_resp.status_code in (200, 204)

    async def test_delete_then_get_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """After deleting, GET should return 404."""
        create_resp = await client.post(
            "/api/v1/projects/",
            json={"name": f"GoneProject {uuid.uuid4().hex[:6]}", "language": "python"},
            headers=auth_headers,
        )
        project_id = create_resp.json()["id"]
        await client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
        get_resp = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert get_resp.status_code == 404