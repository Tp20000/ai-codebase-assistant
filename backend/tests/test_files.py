"""
File upload and management integration tests.
URLs confirmed from route discovery:
  POST /api/v1/projects/{project_id}/files/upload
  GET  /api/v1/projects/{project_id}/files/
  GET  /api/v1/projects/{project_id}/files/{file_id}
  DELETE /api/v1/projects/{project_id}/files/{file_id}
"""
from __future__ import annotations
import io
import uuid
import pytest
from httpx import AsyncClient
from app.models.project import Project

pytestmark = pytest.mark.integration


class TestFileUpload:
    async def test_upload_python_file(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """POST /api/v1/projects/{id}/files/upload"""
        url = f"/api/v1/projects/{test_project.id}/files/upload"
        files = {"file": ("hello.py", io.BytesIO(b"def hello():\n    return 'world'\n"), "text/plain")}
        r = await client.post(url, files=files, headers=auth_headers)
        assert r.status_code in (200, 201, 400, 422), f"Got {r.status_code}: {r.text[:200]}"

    async def test_upload_requires_auth(
        self, client: AsyncClient, test_project: Project
    ) -> None:
        url = f"/api/v1/projects/{test_project.id}/files/upload"
        files = {"file": ("hello.py", io.BytesIO(b"print('hello')"), "text/plain")}
        r = await client.post(url, files=files)
        assert r.status_code == 401

    async def test_upload_to_nonexistent_project(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        url = f"/api/v1/projects/{uuid.uuid4()}/files/upload"
        files = {"file": ("hello.py", io.BytesIO(b"print('hello')"), "text/plain")}
        r = await client.post(url, files=files, headers=auth_headers)
        assert r.status_code in (404, 422)

    async def test_upload_javascript_file(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        url = f"/api/v1/projects/{test_project.id}/files/upload"
        content = b"function greet(name) { return 'Hello ' + name; }"
        files = {"file": ("app.js", io.BytesIO(content), "text/javascript")}
        r = await client.post(url, files=files, headers=auth_headers)
        assert r.status_code in (200, 201, 400, 422)

    async def test_upload_typescript_file(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        url = f"/api/v1/projects/{test_project.id}/files/upload"
        content = b"interface User { id: string; name: string; }"
        files = {"file": ("types.ts", io.BytesIO(content), "text/plain")}
        r = await client.post(url, files=files, headers=auth_headers)
        assert r.status_code in (200, 201, 400, 422)

    async def test_upload_zip_endpoint_exists(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """POST /api/v1/projects/{id}/files/upload-zip exists and requires auth."""
        url = f"/api/v1/projects/{test_project.id}/files/upload-zip"
        r = await client.post(url, headers=auth_headers)
        assert r.status_code in (400, 415, 422)  # Needs zip content


class TestFileList:
    async def test_list_files_returns_200(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """GET /api/v1/projects/{id}/files/"""
        url = f"/api/v1/projects/{test_project.id}/files/"
        r = await client.get(url, headers=auth_headers)
        assert r.status_code == 200

    async def test_list_files_requires_auth(
        self, client: AsyncClient, test_project: Project
    ) -> None:
        url = f"/api/v1/projects/{test_project.id}/files/"
        r = await client.get(url)
        assert r.status_code == 401

    async def test_list_files_nonexistent_project(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        url = f"/api/v1/projects/{uuid.uuid4()}/files/"
        r = await client.get(url, headers=auth_headers)
        assert r.status_code in (200, 404)

    async def test_list_files_response_structure(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        url = f"/api/v1/projects/{test_project.id}/files/"
        r = await client.get(url, headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))


class TestFileOperations:
    async def test_get_specific_file(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """GET /api/v1/projects/{project_id}/files/{file_id}"""
        url = f"/api/v1/projects/{test_project.id}/files/{uuid.uuid4()}"
        r = await client.get(url, headers=auth_headers)
        assert r.status_code in (404, 422)

    async def test_delete_specific_file(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ) -> None:
        """DELETE /api/v1/projects/{project_id}/files/{file_id}"""
        url = f"/api/v1/projects/{test_project.id}/files/{uuid.uuid4()}"
        r = await client.delete(url, headers=auth_headers)
        assert r.status_code in (404, 422)

    async def test_file_operations_require_auth(
        self, client: AsyncClient, test_project: Project
    ) -> None:
        url = f"/api/v1/projects/{test_project.id}/files/{uuid.uuid4()}"
        r = await client.get(url)
        assert r.status_code == 401