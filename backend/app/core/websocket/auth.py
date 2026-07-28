"""
WebSocket Authentication.

WebSockets cannot use HTTP Authorization headers — authentication
must be passed as a query parameter or in the first message.

This module handles JWT validation for WebSocket connections
using the same RS256 tokens as the REST API.

Two strategies supported:
  1. Token as query param: ws://host/ws/chat?token=<jwt>  (simpler)
  2. Token in first message: {"type": "auth", "token": "<jwt>"} (more secure)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import WebSocket, status

from app.utils.jwt_handler import verify_token, TokenType, TokenExpiredError, TokenInvalidError

logger = logging.getLogger(__name__)


class WebSocketAuthError(Exception):
    """Raised when WebSocket authentication fails."""

    def __init__(self, message: str, code: str = "AUTH_FAILED") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


async def authenticate_websocket(
    websocket: WebSocket,
    token: Optional[str] = None,
) -> dict:
    """
    Authenticate a WebSocket connection using a JWT token.

    The token can be provided as:
    1. Query parameter: ?token=<jwt>
    2. Passed directly (extracted by caller from first message)

    Args:
        websocket: The WebSocket connection instance
        token: JWT access token string

    Returns:
        Decoded token payload dict containing user_id, email, etc.

    Raises:
        WebSocketAuthError: If token is missing, expired, or invalid
    """
    if not token:
        # Try to get token from query params
        token = websocket.query_params.get("token")

    if not token:
        raise WebSocketAuthError(
            message="Authentication required. Pass JWT as ?token=<jwt> query parameter.",
            code="TOKEN_MISSING",
        )

    try:
        payload = verify_token(token, expected_type=TokenType.ACCESS)
        user_id = payload.get("sub")
        logger.info("WebSocket authenticated: user_id=%s", user_id)
        return payload

    except TokenExpiredError:
        raise WebSocketAuthError(
            message="Token has expired. Reconnect with a fresh token.",
            code="TOKEN_EXPIRED",
        )
    except (TokenInvalidError, Exception) as exc:
        raise WebSocketAuthError(
            message=f"Invalid token: {exc}",
            code="TOKEN_INVALID",
        )


async def reject_websocket(
    websocket: WebSocket,
    reason: str,
    code: str = "AUTH_FAILED",
) -> None:
    """
    Send an error message and close the WebSocket with 4001 code.

    WebSocket close codes:
    4000 - Generic application error
    4001 - Unauthorized (authentication failed)
    4002 - Forbidden (insufficient permissions)
    4003 - Rate limited

    Args:
        websocket: WebSocket to reject
        reason: Human-readable rejection reason
        code: Application error code string
    """
    try:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "code": code,
            "message": reason,
        })
        await websocket.close(code=4001)
    except Exception as exc:
        logger.warning("Error while rejecting WebSocket: %s", exc)
