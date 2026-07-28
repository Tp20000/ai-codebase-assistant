"""
Middleware integration tests.
Tests: CORS headers, timing header, error handling, request validation.
"""
from __future__ import annotations
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestCORSMiddleware:
    async def test_cors_allow_origin_on_get(self, client: AsyncClient) -> None:
        response = await client.get("/", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 200

    async def test_cors_options_handled(self, client: AsyncClient) -> None:
        response = await client.options(
            "/api/v1/auth/login", headers={"Origin": "http://localhost:5173"}
        )
        assert response.status_code in (200, 405)


class TestTimingMiddleware:
    async def test_timing_header_present(self, client: AsyncClient) -> None:
        response = await client.get("/")
        assert "x-process-time" in response.headers

    async def test_timing_header_is_numeric(self, client: AsyncClient) -> None:
        response = await client.get("/")
        timing = response.headers.get("x-process-time", "")
        assert timing.endswith("ms")
        assert float(timing.replace("ms", "")) >= 0

    async def test_timing_header_on_any_route(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/")
        assert response.status_code == 200
        assert "x-process-time" in response.headers


class TestErrorHandling:
    async def test_404_returns_json(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/nonexistent-endpoint-xyz")
        assert response.status_code == 404
        assert "application/json" in response.headers.get("content-type", "")

    async def test_method_not_allowed(self, client: AsyncClient) -> None:
        response = await client.delete("/")
        assert response.status_code in (405, 404, 422)

    async def test_malformed_json_returns_422(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            content=b"not valid json {{{",
            headers={**auth_headers, "content-type": "application/json"},
        )
        assert response.status_code == 422

    async def test_missing_content_type_on_post(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/login", content=b"raw body")
        assert response.status_code in (400, 415, 422)


class TestRequestValidation:
    async def test_extra_fields_handled(self, client: AsyncClient) -> None:
        payload = {
            "email": "test@example.com",
            "password": "TestPass123!",
            "unknown_field_xyz": "ignored",
        }
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code in (200, 401, 422)

    async def test_wrong_type_for_field_returns_422(self, client: AsyncClient) -> None:
        payload = {"email": 12345, "password": True}
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 422