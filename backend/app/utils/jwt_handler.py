"""
JWT Handler — RS256 Asymmetric JWT Authentication
Handles key generation, token creation, verification, and claims management.
Uses RS256 (RSA + SHA-256) — private key signs, public key verifies.
Pattern: Amazon/Google internal auth services use asymmetric JWTs so
         public key can be shared with microservices without exposing signing secret.
"""

import uuid
import logging
import base64
import binascii
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidTokenError,
    DecodeError,
)

from app.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# RSA Key Management
# ─────────────────────────────────────────────

KEYS_DIR = Path(__file__).parent.parent.parent / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "private.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "public.pem"


def generate_rsa_keypair() -> tuple[bytes, bytes]:
    """
    Generate a 2048-bit RSA key pair.
    Returns (private_key_pem, public_key_pem) as bytes.
    Called once on first startup if keys don't exist.
    """
    logger.info("Generating new RSA-2048 key pair...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    logger.info("RSA key pair generated successfully.")
    return private_pem, public_pem


def ensure_keys_exist() -> None:
    """
    Ensure RSA key files exist on disk.
    Creates them if they do not exist (first-time setup).
    In production, keys should be injected via environment or secrets manager.
    """
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    if not PRIVATE_KEY_PATH.exists() or not PUBLIC_KEY_PATH.exists():
        private_pem, public_pem = generate_rsa_keypair()
        PRIVATE_KEY_PATH.write_bytes(private_pem)
        PUBLIC_KEY_PATH.write_bytes(public_pem)
        logger.info(f"Keys written to {KEYS_DIR}")
    else:
        logger.debug("RSA keys already exist — skipping generation.")


def load_private_key() -> bytes:
    """Load private key PEM bytes from disk or environment variable."""
    if settings.JWT_PRIVATE_KEY:
        return _normalize_env_pem(settings.JWT_PRIVATE_KEY)
    ensure_keys_exist()
    return PRIVATE_KEY_PATH.read_bytes()


def load_public_key() -> bytes:
    """Load public key PEM bytes from disk or environment variable."""
    if settings.JWT_PUBLIC_KEY:
        return _normalize_env_pem(settings.JWT_PUBLIC_KEY)
    ensure_keys_exist()
    return PUBLIC_KEY_PATH.read_bytes()


def _normalize_env_pem(value: str) -> bytes:
    """Support PEM text and base64-encoded PEM values from environment variables."""
    key_text = value.strip()
    if "-----BEGIN" in key_text:
        return key_text.encode()

    try:
        decoded = base64.b64decode(key_text, validate=True)
        if b"-----BEGIN" in decoded:
            return decoded
    except (ValueError, binascii.Error):
        pass

    return key_text.encode()


# ─────────────────────────────────────────────
# Token Models
# ─────────────────────────────────────────────

class TokenType:
    """Enum-like class for token type constants."""
    ACCESS = "access"
    REFRESH = "refresh"


class TokenClaims:
    """
    Standard JWT claim keys used throughout the application.
    Follows RFC 7519 registered claim names.
    """
    SUBJECT = "sub"          # user_id
    JWT_ID = "jti"           # unique token ID (for revocation)
    TOKEN_TYPE = "type"      # 'access' or 'refresh'
    EMAIL = "email"
    USERNAME = "username"
    ROLES = "roles"
    ISSUED_AT = "iat"
    EXPIRY = "exp"
    ISSUER = "iss"


# ─────────────────────────────────────────────
# Token Creation
# ─────────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    username: str,
    roles: list[str] | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """
    Create a signed RS256 JWT access token.

    Args:
        user_id: UUID string of the authenticated user
        email: User email address (included in claims)
        username: Username (included in claims)
        roles: List of role strings (e.g. ['user', 'admin'])
        expires_delta: Custom expiry; defaults to settings value

    Returns:
        Tuple of (encoded_jwt_string, jti) where jti is the unique token ID.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    jti = str(uuid.uuid4())

    payload = {
        TokenClaims.SUBJECT: user_id,
        TokenClaims.JWT_ID: jti,
        TokenClaims.TOKEN_TYPE: TokenType.ACCESS,
        TokenClaims.EMAIL: email,
        TokenClaims.USERNAME: username,
        TokenClaims.ROLES: roles or ["user"],
        TokenClaims.ISSUED_AT: now,
        TokenClaims.EXPIRY: expire,
        TokenClaims.ISSUER: settings.JWT_ISSUER,
    }

    private_key = load_private_key()
    encoded = jwt.encode(payload, private_key, algorithm="RS256")
    logger.debug(f"Access token created for user_id={user_id}, jti={jti}")
    return encoded, jti


def create_refresh_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """
    Create a signed RS256 JWT refresh token.
    Refresh tokens carry minimal claims — only sub, jti, type, iat, exp.
    This limits exposure if a refresh token is somehow leaked.

    Args:
        user_id: UUID string of the user
        expires_delta: Custom expiry; defaults to settings value

    Returns:
        Tuple of (encoded_jwt_string, jti)
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    jti = str(uuid.uuid4())

    payload = {
        TokenClaims.SUBJECT: user_id,
        TokenClaims.JWT_ID: jti,
        TokenClaims.TOKEN_TYPE: TokenType.REFRESH,
        TokenClaims.ISSUED_AT: now,
        TokenClaims.EXPIRY: expire,
        TokenClaims.ISSUER: settings.JWT_ISSUER,
    }

    private_key = load_private_key()
    encoded = jwt.encode(payload, private_key, algorithm="RS256")
    logger.debug(f"Refresh token created for user_id={user_id}, jti={jti}")
    return encoded, jti


# ─────────────────────────────────────────────
# Token Verification
# ─────────────────────────────────────────────

class JWTError(Exception):
    """Base exception for all JWT errors raised by this module."""
    pass


class TokenExpiredError(JWTError):
    """Raised when a JWT has passed its expiry time."""
    pass


class TokenInvalidError(JWTError):
    """Raised when a JWT fails signature verification or has malformed claims."""
    pass


class TokenTypeMismatchError(JWTError):
    """Raised when the token type claim does not match the expected type."""
    pass


def verify_token(token: str, expected_type: str) -> dict:
    """
    Verify and decode a JWT token using the RS256 public key.

    Validates:
    - Signature (RS256 with public key)
    - Expiry (exp claim)
    - Issuer (iss claim)
    - Token type (type claim must match expected_type)

    Args:
        token: Encoded JWT string
        expected_type: 'access' or 'refresh'

    Returns:
        Decoded payload dictionary

    Raises:
        TokenExpiredError: Token has expired
        TokenInvalidError: Token signature or claims invalid
        TokenTypeMismatchError: Token type does not match expected
    """
    public_key = load_public_key()
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"require": ["exp", "iat", "sub", "jti"]},
            issuer=settings.JWT_ISSUER,
        )
    except ExpiredSignatureError as exc:
        logger.warning(f"Token expired: {exc}")
        raise TokenExpiredError("Token has expired. Please log in again.") from exc
    except DecodeError as exc:
        logger.warning(f"Token decode error: {exc}")
        raise TokenInvalidError("Token is malformed or tampered.") from exc
    except InvalidTokenError as exc:
        logger.warning(f"Token invalid: {exc}")
        raise TokenInvalidError(f"Token is invalid: {exc}") from exc

    token_type = payload.get(TokenClaims.TOKEN_TYPE)
    if token_type != expected_type:
        raise TokenTypeMismatchError(
            f"Expected token type '{expected_type}', got '{token_type}'."
        )

    return payload


def decode_token_unverified(token: str) -> dict:
    """
    Decode JWT without verification — used ONLY for extracting jti
    from an already-expired token during logout cleanup.
    Never use this for authentication decisions.
    """
    return jwt.decode(token, options={"verify_signature": False})


# ─────────────────────────────────────────────────────────────────
# FastAPI Dependency: get_current_user
# Used in route handlers: current_user = Depends(get_current_user)
# ─────────────────────────────────────────────────────────────────

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

_bearer_scheme = HTTPBearer(auto_error=False)

# ================================================================
# FastAPI Authentication Dependencies
# ================================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

_http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency — validates Bearer token and returns the current User.

    Uses RS256 verify_token() with expected_type='access' to validate
    the token signature, expiry, issuer, and token type.

    Usage in route handler:
        current_user = Depends(get_current_user)

    Returns:
        User ORM object for the authenticated user

    Raises:
        HTTPException 401: Token missing, invalid, or expired
        HTTPException 403: Account is disabled
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Verify the RS256 access token — raises TokenExpiredError / TokenInvalidError
    try:
        payload = verify_token(token, expected_type=TokenType.ACCESS)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (TokenInvalidError, TokenTypeMismatchError, JWTError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user_id from 'sub' claim
    user_id = payload.get(TokenClaims.SUBJECT)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject (user ID) claim",
        )

    # Load the user from database
    try:
        from app.repositories.user_repo import UserRepository
        repo = UserRepository(db)
        user = await repo.get_by_id(user_id)
    except Exception as exc:
        logger.error("Database error in get_current_user: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found — token may be stale",
        )

    if hasattr(user, "is_active") and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact support.",
        )

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Same as get_current_user but returns None for unauthenticated requests.
    Use for endpoints that work for both authed and anonymous users.
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except HTTPException:
        return None