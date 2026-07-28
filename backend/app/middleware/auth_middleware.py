"""
Auth Middleware - FastAPI dependency injection for JWT authentication.
Provides get_current_user() and require_admin() FastAPI Depends() callables.

Redis is optional - if unavailable, token blacklist check is skipped gracefully.
"""

from __future__ import annotations

import logging
from typing import Optional, Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.utils.jwt_handler import (
    verify_token,
    TokenType,
    TokenExpiredError,
    TokenInvalidError,
    TokenTypeMismatchError,
)

logger = logging.getLogger(__name__)

# Blacklist prefix (for future Redis-based logout)
ACCESS_BLACKLIST_PREFIX = "auth:blacklist:"

# HTTPBearer extracts "Bearer <token>" from Authorization header
bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)

TOKEN_EXPIRED_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Access token has expired. Use /auth/refresh to get a new one.",
    headers={"WWW-Authenticate": "Bearer"},
)

INACTIVE_USER_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="User account is deactivated.",
)

ADMIN_REQUIRED_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Administrator privileges required.",
)


async def _get_optional_redis() -> Optional[aioredis.Redis]:
    """
    Optional Redis dependency - returns None if Redis unavailable.
    Never raises - allows endpoints to work without Redis.
    """
    try:
        from app.services.cache_service import cache_service
        if cache_service.is_connected and cache_service._redis is not None:
            return cache_service._redis
        connected = await cache_service.connect()
        if connected:
            return cache_service._redis
    except Exception as exc:
        logger.debug("Redis unavailable for auth middleware: %s", exc)
    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency: Extract, verify, and return the authenticated user.

    Flow:
    1. Extract Bearer token from Authorization header
    2. Verify RS256 JWT signature and claims
    3. Optionally check token blacklist in Redis (skipped if Redis unavailable)
    4. Load user from database
    5. Verify user is active

    Args:
        credentials: Bearer token from Authorization header
        db: Injected async database session

    Returns:
        Authenticated User model instance

    Raises:
        HTTP 401: Missing/invalid/expired token
        HTTP 403: Inactive user account
    """
    if not credentials:
        logger.debug("Request missing Authorization header")
        raise CREDENTIALS_EXCEPTION

    import sys; print(f"DEBUG AUTH: got credentials, token_prefix={credentials.credentials[:20] if credentials else None}", file=sys.stderr, flush=True)
    token = credentials.credentials

    # Verify JWT signature, expiry, and type
    try:
        payload = verify_token(token, expected_type=TokenType.ACCESS)
    except TokenExpiredError:
        raise TOKEN_EXPIRED_EXCEPTION
    except (TokenInvalidError, TokenTypeMismatchError, Exception) as exc:
        logger.warning("Token validation failed: %s", exc)
        raise CREDENTIALS_EXCEPTION

    # Optional: Check blacklist in Redis (skip if Redis unavailable)
    try:
        redis_client = await _get_optional_redis()
        if redis_client is not None:
            jti = payload.get("jti")
            if jti:
                is_blacklisted = await redis_client.exists(
                    f"{ACCESS_BLACKLIST_PREFIX}{jti}"
                )
                if is_blacklisted:
                    logger.warning("Blacklisted token used: jti=%s", jti)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token has been revoked. Please log in again.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Redis blacklist check skipped: %s", exc)

    # Load user from database
    user_id = payload.get("sub")
    if not user_id:
        
        raise CREDENTIALS_EXCEPTION

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        logger.warning("Token references non-existent user_id=%s", user_id)
        raise CREDENTIALS_EXCEPTION

    if not user.is_active:
        logger.warning("Inactive user attempted access: user_id=%s", user_id)
        raise INACTIVE_USER_EXCEPTION

    logger.debug("Authenticated user: %s (id=%s)", user.email, user.id)
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    FastAPI dependency: Return authenticated user or None (for optional auth).
    Does NOT raise exceptions - returns None for unauthenticated requests.
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except HTTPException:
        return None


def require_roles(*required_roles: str):
    """
    FastAPI dependency factory: Enforce role-based access control.

    Usage:
        @router.delete("/users/{id}")
        async def delete_user(
            current_user: User = Depends(require_roles("admin"))
        ):
    """
    async def _require_roles(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_roles = getattr(current_user, "roles", []) or []
        if not any(role in user_roles for role in required_roles):
            logger.warning(
                "User %s lacks required roles %s (has: %s)",
                current_user.id, required_roles, user_roles,
            )
            raise ADMIN_REQUIRED_EXCEPTION
        return current_user

    return _require_roles


# Shorthand dependency for admin-only endpoints
require_admin = require_roles("admin")

# Type aliases for cleaner endpoint signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[Optional[User], Depends(get_current_user_optional)]
