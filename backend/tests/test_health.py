"""
Health endpoint unit tests.
Tests: GET /api/v1/health/ returns correct structure.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.unit


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Health endpoint should return HTTP 200."""
        response = await client.get("/api/v1/health/")
        assert response.status_code == 200

    async def test_health_has_status_field(self, client: AsyncClient) -> None:
        """Health response must include a status field."""
        response = await client.get("/api/v1/health/")
        data = response.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    async def test_health_has_version(self, client: AsyncClient) -> None:
        """Health response must include version."""
        response = await client.get("/api/v1/health/")
        data = response.json()
        assert "version" in data
        assert data["version"] == "2.0.0"

    async def test_health_has_services(self, client: AsyncClient) -> None:
        """Health response must include services dict."""
        response = await client.get("/api/v1/health/")
        data = response.json()
        assert "services" in data
        assert isinstance(data["services"], dict)

    async def test_root_endpoint(self, client: AsyncClient) -> None:
        """Root endpoint should return API info."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "version" in data

    async def test_openapi_schema(self, client: AsyncClient) -> None:
        """OpenAPI schema should be available."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data