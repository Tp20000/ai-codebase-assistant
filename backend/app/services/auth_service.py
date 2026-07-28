"""
Auth Service — Business logic for authentication.
"""

import logging
from datetime import timedelta, datetime, timezone
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.utils.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
    decode_token_unverified,
    TokenType,
    TokenExpiredError,
    TokenInvalidError,
    TokenTypeMismatchError,
)
from app.utils.password import hash_password, verify_password, is_password_strong
from app.utils.validators import validate_email, validate_username

logger = logging.getLogger(__name__)

REFRESH_TOKEN_PREFIX = "auth:refresh:"
ACCESS_BLACKLIST_PREFIX = "auth:blacklist:"


class AuthError(Exception):
    """Authentication error — HTTP 401."""
    pass


class RegistrationError(Exception):
    """Registration error — HTTP 400."""
    pass


class AuthService:
    """Stateless authentication service."""

    def __init__(self, db: AsyncSession, redis: aioredis.Redis) -> None:
        self.db = db
        self.redis = redis
        self.user_repo = UserRepository(db)

    async def register(
        self,
        email: str,
        username: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> User:
        """Register new user account."""
        try:
            email = validate_email(email)
            username = validate_username(username)
        except ValueError as exc:
            raise RegistrationError(str(exc)) from exc

        is_strong, reason = is_password_strong(password)
        if not is_strong:
            raise RegistrationError(reason)

        if await self.user_repo.email_exists(email):
            raise RegistrationError(f"Email '{email}' is already registered.")
        if await self.user_repo.username_exists(username):
            raise RegistrationError(f"Username '{username}' is already taken.")

        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
            is_verified=False,
        )
        user = await self.user_repo.create(user)
        logger.info(f"New user registered: {email} (id={user.id})")
        return user

    async def login(self, email: str, password: str) -> dict:
        """Authenticate user and issue JWT token pair."""
        email = email.strip().lower()

        user = await self.user_repo.get_by_email(email)
        if not user:
            logger.warning(f"Login attempt for non-existent email: {email}")
            raise AuthError("Invalid email or password.")

        if not verify_password(password, user.hashed_password):
            logger.warning(f"Failed login for: {email}")
            raise AuthError("Invalid email or password.")

        if not user.is_active:
            raise AuthError("Account is deactivated.")

        access_token, _ = create_access_token(
            user_id=str(user.id),
            email=user.email,
            username=user.username,
        )
        refresh_token, refresh_jti = create_refresh_token(user_id=str(user.id))
        await self._store_refresh_token(refresh_jti, str(user.id))

        # Non-fatal last login update
        try:
            await self.user_repo.update_last_login(user.id)
        except Exception as exc:
            logger.warning(f"Non-fatal: last_login update failed: {exc}")

        logger.info(f"User logged in: {email}")
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def refresh_tokens(self, refresh_token: str) -> dict:
        """Rotate JWT tokens using refresh token."""
        try:
            payload = verify_token(refresh_token, expected_type=TokenType.REFRESH)
        except TokenExpiredError:
            raise AuthError("Refresh token expired. Please log in again.")
        except (TokenInvalidError, TokenTypeMismatchError) as exc:
            raise AuthError(str(exc))

        refresh_jti = payload["jti"]
        user_id = payload["sub"]

        stored = await self.redis.get(f"{REFRESH_TOKEN_PREFIX}{refresh_jti}")
        if not stored:
            raise AuthError("Refresh token revoked. Please log in again.")

        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthError("User not found or deactivated.")

        await self.redis.delete(f"{REFRESH_TOKEN_PREFIX}{refresh_jti}")

        new_access, _ = create_access_token(
            user_id=str(user.id),
            email=user.email,
            username=user.username,
        )
        new_refresh, new_jti = create_refresh_token(user_id=str(user.id))
        await self._store_refresh_token(new_jti, str(user.id))

        logger.info(f"Tokens rotated for user_id={user_id}")
        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def logout(self, access_token: str, refresh_token: Optional[str] = None) -> None:
        """Revoke tokens on logout."""
        try:
            payload = decode_token_unverified(access_token)
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                ttl = max(0, int(exp - datetime.now(timezone.utc).timestamp()))
                if ttl > 0:
                    await self.redis.setex(f"{ACCESS_BLACKLIST_PREFIX}{jti}", ttl, "1")
        except Exception as exc:
            logger.warning(f"Could not blacklist access token: {exc}")

        if refresh_token:
            try:
                payload = decode_token_unverified(refresh_token)
                jti = payload.get("jti")
                if jti:
                    await self.redis.delete(f"{REFRESH_TOKEN_PREFIX}{jti}")
            except Exception as exc:
                logger.warning(f"Could not revoke refresh token: {exc}")

    async def is_token_blacklisted(self, jti: str) -> bool:
        """Check if access token JTI is blacklisted."""
        return await self.redis.exists(f"{ACCESS_BLACKLIST_PREFIX}{jti}") > 0

    async def _store_refresh_token(self, jti: str, user_id: str) -> None:
        """Store refresh token in Redis with TTL."""
        ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        await self.redis.setex(f"{REFRESH_TOKEN_PREFIX}{jti}", ttl, user_id)