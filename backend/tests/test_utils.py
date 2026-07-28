"""
Unit tests for utility functions.
Matches the ACTUAL signatures of jwt_handler.py and password.py.
Pure unit tests — no database or network required.
"""

from __future__ import annotations

import pytest

from app.utils.password import hash_password, verify_password
from app.utils.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
    TokenType,
    TokenInvalidError,
)


pytestmark = pytest.mark.unit


# ── Password Tests ─────────────────────────────────────────────────────────

class TestPasswordHashing:
    """Tests for bcrypt password hashing utilities."""

    def test_hash_password_returns_string(self) -> None:
        result = hash_password("MySecretPassword123!")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_is_not_plaintext(self) -> None:
        password = "MySecretPassword123!"
        assert hash_password(password) != password

    def test_verify_correct_password(self) -> None:
        password = "CorrectPassword123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("CorrectPassword123!")
        assert verify_password("WrongPassword999!", hashed) is False

    def test_two_hashes_are_different(self) -> None:
        password = "SamePassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2

    def test_verify_empty_password_fails(self) -> None:
        hashed = hash_password("RealPassword123!")
        assert verify_password("", hashed) is False

    def test_hash_long_password(self) -> None:
        long_password = "A" * 72
        hashed = hash_password(long_password)
        assert verify_password(long_password, hashed) is True


# ── JWT Tests ──────────────────────────────────────────────────────────────

def _make_access_token(user_id: str = "user-123",
                       email: str = "test@example.com",
                       username: str = "testuser") -> str:
    """
    Helper that calls create_access_token with the correct signature.
    Returns just the token string (handles tuple return if any).
    """
    result = create_access_token(user_id, email, username)
    # Some implementations return (token, jti) tuple
    if isinstance(result, tuple):
        return result[0]
    return result


def _make_refresh_token(user_id: str = "user-123") -> str:
    """
    Helper that calls create_refresh_token with the correct signature.
    Returns just the token string (handles tuple return if any).
    """
    result = create_refresh_token(user_id)
    if isinstance(result, tuple):
        return result[0]
    return result


class TestJWTHandler:
    """Tests for JWT token creation and verification."""

    def test_create_access_token_returns_string(self) -> None:
        token = _make_access_token()
        assert isinstance(token, str)
        assert len(token) > 50

    def test_access_token_has_three_parts(self) -> None:
        token = _make_access_token()
        assert len(token.split(".")) == 3

    def test_verify_valid_access_token(self) -> None:
        token = _make_access_token(user_id="user-abc", email="abc@test.com")
        decoded = verify_token(token, TokenType.ACCESS)
        assert decoded is not None
        # sub should be the user_id
        assert "user-abc" in str(decoded.get("sub", ""))

    def test_create_refresh_token_returns_string(self) -> None:
        token = _make_refresh_token()
        assert isinstance(token, str)
        assert len(token) > 50

    def test_refresh_token_has_three_parts(self) -> None:
        token = _make_refresh_token()
        assert len(token.split(".")) == 3

    def test_verify_refresh_token(self) -> None:
        token = _make_refresh_token(user_id="user-xyz")
        decoded = verify_token(token, TokenType.REFRESH)
        assert decoded is not None

    def test_invalid_token_raises_error(self) -> None:
        with pytest.raises((TokenInvalidError, Exception)):
            verify_token("this.is.garbage", TokenType.ACCESS)

    def test_token_contains_exp_claim(self) -> None:
        token = _make_access_token()
        decoded = verify_token(token, TokenType.ACCESS)
        assert "exp" in decoded

    def test_different_users_get_different_tokens(self) -> None:
        token1 = _make_access_token(user_id="user-001")
        token2 = _make_access_token(user_id="user-002")
        assert token1 != token2

    def test_token_sub_preserved(self) -> None:
        user_id = "550e8400-e29b-41d4-a716-446655440000"
        token = _make_access_token(user_id=user_id)
        decoded = verify_token(token, TokenType.ACCESS)
        assert user_id in str(decoded.get("sub", ""))

    def test_wrong_token_type_raises_error(self) -> None:
        """Using access token where refresh is expected should fail."""
        access_token = _make_access_token()
        with pytest.raises((TokenInvalidError, Exception)):
            verify_token(access_token, TokenType.REFRESH)