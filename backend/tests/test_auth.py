"""
Authentication endpoint integration tests.
Tests: register, login, /me, token validation, edge cases.
"""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

from app.models.user import User


pytestmark = pytest.mark.integration


class TestRegister:
    """Tests for POST /api/v1/auth/register."""

    async def test_register_new_user_returns_201(self, client: AsyncClient) -> None:
        """Registering a new user should return HTTP 201."""
        payload = {
            "email": f"newuser_{uuid.uuid4().hex[:8]}@example.com",
            "username": f"user_{uuid.uuid4().hex[:8]}",
            "password": "SecurePass123!",
            "full_name": "New User",
        }
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201

    async def test_register_returns_user_data(self, client: AsyncClient) -> None:
        """Register response must include email and username."""
        email = f"data_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": email,
            "username": f"datauser_{uuid.uuid4().hex[:8]}",
            "password": "SecurePass123!",
        }
        response = await client.post("/api/v1/auth/register", json=payload)
        data = response.json()
        assert data["email"] == email
        assert "id" in data
        assert "hashed_password" not in data

    async def test_register_duplicate_email_returns_409(self, client: AsyncClient, test_user: User) -> None:
        """Registering with an existing email must return 409 Conflict."""
        payload = {
            "email": test_user.email,
            "username": f"dup_{uuid.uuid4().hex[:8]}",
            "password": "SecurePass123!",
        }
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409

    async def test_register_invalid_email_returns_422(self, client: AsyncClient) -> None:
        """Invalid email format should return 422 Unprocessable Entity."""
        payload = {
            "email": "not-an-email",
            "username": "someuser",
            "password": "SecurePass123!",
        }
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422

    async def test_register_short_password_returns_422(self, client: AsyncClient) -> None:
        """Password shorter than 8 chars should return 422."""
        payload = {
            "email": f"short_{uuid.uuid4().hex[:8]}@example.com",
            "username": f"shortpass_{uuid.uuid4().hex[:6]}",
            "password": "abc",
        }
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422

    async def test_register_missing_email_returns_422(self, client: AsyncClient) -> None:
        """Missing email field should return 422."""
        payload = {"username": "noemail", "password": "SecurePass123!"}
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    async def test_login_valid_credentials_returns_200(
        self, client: AsyncClient, test_user: User
    ) -> None:
        """Login with correct credentials should return 200."""
        payload = {"email": test_user.email, "password": "TestPass123!"}
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 200

    async def test_login_returns_access_token(
        self, client: AsyncClient, test_user: User
    ) -> None:
        """Login response must include access_token."""
        payload = {"email": test_user.email, "password": "TestPass123!"}
        response = await client.post("/api/v1/auth/login", json=payload)
        data = response.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 50

    async def test_login_returns_refresh_token(
        self, client: AsyncClient, test_user: User
    ) -> None:
        """Login response must include refresh_token."""
        payload = {"email": test_user.email, "password": "TestPass123!"}
        response = await client.post("/api/v1/auth/login", json=payload)
        data = response.json()
        assert "refresh_token" in data

    async def test_login_token_type_is_bearer(
        self, client: AsyncClient, test_user: User
    ) -> None:
        """Token type must be bearer."""
        payload = {"email": test_user.email, "password": "TestPass123!"}
        response = await client.post("/api/v1/auth/login", json=payload)
        data = response.json()
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password_returns_401(
        self, client: AsyncClient, test_user: User
    ) -> None:
        """Wrong password must return 401 Unauthorized."""
        payload = {"email": test_user.email, "password": "WrongPassword999!"}
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401

    async def test_login_unknown_email_returns_401(self, client: AsyncClient) -> None:
        """Login with unknown email must return 401."""
        payload = {"email": "nobody@nowhere.com", "password": "SomePassword123!"}
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401

    async def test_login_missing_password_returns_422(
        self, client: AsyncClient, test_user: User
    ) -> None:
        """Missing password field should return 422."""
        payload = {"email": test_user.email}
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 422

    async def test_login_empty_body_returns_422(self, client: AsyncClient) -> None:
        """Empty request body must return 422."""
        response = await client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422


class TestGetMe:
    """Tests for GET /api/v1/auth/me."""

    async def test_get_me_with_valid_token(
        self, client: AsyncClient, test_user: User, auth_headers: dict
    ) -> None:
        """GET /me with valid token should return user data."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_me_returns_correct_email(
        self, client: AsyncClient, test_user: User, auth_headers: dict
    ) -> None:
        """GET /me should return the authenticated user's email."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        data = response.json()
        assert data["email"] == test_user.email

    async def test_get_me_no_token_returns_401(self, client: AsyncClient) -> None:
        """GET /me without token must return 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_get_me_invalid_token_returns_401(self, client: AsyncClient) -> None:
        """GET /me with invalid token must return 401."""
        headers = {"Authorization": "Bearer completely.invalid.token"}
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401

    async def test_get_me_malformed_header_returns_401(self, client: AsyncClient) -> None:
        """GET /me with malformed Authorization header returns 401."""
        headers = {"Authorization": "NotBearer sometoken"}
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401

    async def test_get_me_does_not_expose_password(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """GET /me must never return hashed_password in response."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        data = response.json()
        assert "hashed_password" not in data
        assert "password" not in data