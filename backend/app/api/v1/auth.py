"""
Authentication API endpoints.

Provides:
- POST /auth/register — Create new user account
- POST /auth/login    — Login and get JWT tokens
- POST /auth/refresh  — Refresh access token
- POST /auth/logout   — Invalidate tokens
- GET  /auth/me       — Get current user profile
- GET  /auth/health   — Auth service health check
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.middleware.auth_middleware import get_current_user
from app.utils.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
    TokenType,
    TokenExpiredError,
    TokenInvalidError,
)
from app.utils.password import hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """Request body for user registration."""
    email: EmailStr = Field(..., description="User email address")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    """Request body for login."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


class RefreshRequest(BaseModel):
    """Request body for token refresh."""
    refresh_token: str


class UserResponse(BaseModel):
    """Public user profile response."""
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    preferred_model: str
    theme: str


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user account."""
    repo = UserRepository(db)

    if await repo.email_exists(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    if await repo.username_exists(body.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken",
        )

    try:
        hashed = hash_password(body.password)
    except Exception as exc:
        logger.error("Password hashing failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not process password")

    try:
        user = User(
            email=body.email.lower().strip(),
            username=body.username.strip(),
            hashed_password=hashed,
            full_name=body.full_name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("Registered: %s", user.email)
    except Exception as exc:
        await db.rollback()
        logger.error("Registration DB error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Registration failed: {type(exc).__name__}: {exc}",
        )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        preferred_model=user.preferred_model,
        theme=user.theme,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email and password."""
    repo = UserRepository(db)

    user = await repo.get_by_email(body.email.lower().strip())
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    try:
        access_token, _ = create_access_token(
            user_id=str(user.id),
            email=user.email,
            username=user.username,
        )
        refresh_token, _ = create_refresh_token(user_id=str(user.id))
    except Exception as exc:
        logger.error("Token generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not generate tokens")

    try:
        await repo.update_last_login(user.id)
    except Exception as exc:
        logger.warning("last_login update failed: %s", exc)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange refresh token for new token pair."""
    try:
        payload = verify_token(body.refresh_token, expected_type=TokenType.REFRESH)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid refresh token: {exc}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token claims")

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access_token, _ = create_access_token(
        user_id=str(user.id), email=user.email, username=user.username
    )
    new_refresh, _ = create_refresh_token(user_id=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", summary="Logout current user")
async def logout(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Logout the current user."""
    logger.info("User logged out: %s", current_user.email)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the currently authenticated user's profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        preferred_model=current_user.preferred_model,
        theme=current_user.theme,
    )


@router.get("/health", summary="Auth service health check")
async def auth_health() -> dict:
    """Check auth service is operational."""
    return {"status": "ok", "service": "auth", "algorithm": "RS256"}
