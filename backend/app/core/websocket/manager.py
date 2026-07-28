"""
WebSocket Connection Manager.

Manages all active WebSocket connections across the application.
Provides:
- Connection registry with metadata
- Heartbeat/ping-pong keepalive
- Graceful disconnect handling
- Per-user and per-project connection tracking
- Broadcast utilities for future multi-user features

This is a singleton used by all WebSocket endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket

from app.core.websocket.protocols import HeartbeatMessage, ErrorMessage

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds — client must respond within 2x this value
HEARTBEAT_INTERVAL = 30
# Max seconds with no activity before considering connection dead
CONNECTION_TIMEOUT = 90


@dataclass
class WebSocketConnection:
    """
    Represents a single active WebSocket connection with metadata.

    Tracks connection state, timing, and associated user/project context
    for proper lifecycle management and debugging.
    """

    connection_id: str
    websocket: WebSocket
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    connected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_active: float = field(default_factory=time.monotonic)
    is_streaming: bool = False
    message_count: int = 0

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_active = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        """Seconds since last activity."""
        return time.monotonic() - self.last_active

    @property
    def is_stale(self) -> bool:
        """True if connection has been idle too long."""
        return self.idle_seconds > CONNECTION_TIMEOUT

    def to_dict(self) -> dict[str, Any]:
        """Serialize connection metadata for logging/monitoring."""
        return {
            "connection_id": self.connection_id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "connected_at": self.connected_at.isoformat(),
            "idle_seconds": round(self.idle_seconds, 1),
            "is_streaming": self.is_streaming,
            "message_count": self.message_count,
        }


class WebSocketManager:
    """
    Singleton manager for all active WebSocket connections.

    Handles:
    - Connection registration and deregistration
    - Heartbeat keepalive (prevents proxy timeouts)
    - Stale connection cleanup
    - Per-user connection tracking
    - Safe message sending with error handling

    Usage:
        manager = WebSocketManager()
        conn = await manager.connect(websocket, user_id="uuid")
        await manager.send(conn.connection_id, {"type": "token", ...})
        await manager.disconnect(conn.connection_id)
    """

    def __init__(self) -> None:
        """Initialize the connection registry."""
        self._connections: dict[str, WebSocketConnection] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        logger.info("WebSocketManager initialized")

    @property
    def active_count(self) -> int:
        """Number of currently active connections."""
        return len(self._connections)

    async def connect(
        self,
        websocket: WebSocket,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> WebSocketConnection:
        """
        Register a new WebSocket connection.

        Args:
            websocket: Accepted FastAPI WebSocket instance
            user_id: Authenticated user UUID
            project_id: Project this connection is for
            session_id: Chat session UUID for history tracking

        Returns:
            WebSocketConnection with unique connection_id
        """
        connection_id = str(uuid.uuid4())
        conn = WebSocketConnection(
            connection_id=connection_id,
            websocket=websocket,
            user_id=user_id,
            project_id=project_id,
            session_id=session_id,
        )
        self._connections[connection_id] = conn

        logger.info(
            "WebSocket connected: id=%s user=%s total=%d",
            connection_id[:8],
            user_id,
            self.active_count,
        )

        # Start heartbeat task if not running
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        return conn

    async def disconnect(self, connection_id: str) -> None:
        """
        Remove a connection from the registry.

        Safe to call multiple times — idempotent.

        Args:
            connection_id: ID of connection to remove
        """
        conn = self._connections.pop(connection_id, None)
        if conn:
            logger.info(
                "WebSocket disconnected: id=%s user=%s total=%d",
                connection_id[:8],
                conn.user_id,
                self.active_count,
            )

    async def send_json(
        self,
        connection_id: str,
        data: dict[str, Any],
    ) -> bool:
        """
        Send a JSON message to a specific connection.

        Args:
            connection_id: Target connection ID
            data: JSON-serializable dict to send

        Returns:
            True if sent successfully, False if connection is gone
        """
        conn = self._connections.get(connection_id)
        if not conn:
            return False

        try:
            await conn.websocket.send_json(data)
            conn.touch()
            conn.message_count += 1
            return True
        except Exception as exc:
            logger.warning(
                "Failed to send to connection %s: %s",
                connection_id[:8],
                exc,
            )
            await self.disconnect(connection_id)
            return False

    async def send_error(
        self,
        connection_id: str,
        message: str,
        code: str = "ERROR",
        message_id: Optional[str] = None,
    ) -> None:
        """
        Send an error message to a connection.

        Args:
            connection_id: Target connection
            message: Human-readable error description
            code: Machine-readable error code
            message_id: Optional message ID for correlation
        """
        error = ErrorMessage(message=message, code=code, message_id=message_id)
        await self.send_json(connection_id, error.to_dict())

    def get_connection(self, connection_id: str) -> Optional[WebSocketConnection]:
        """
        Get a connection by ID.

        Args:
            connection_id: Connection UUID

        Returns:
            WebSocketConnection or None if not found
        """
        return self._connections.get(connection_id)

    def get_user_connections(self, user_id: str) -> list[WebSocketConnection]:
        """
        Get all active connections for a user.

        Useful for sending notifications to all of a user's devices.

        Args:
            user_id: User UUID string

        Returns:
            List of active connections for this user
        """
        return [
            conn for conn in self._connections.values()
            if conn.user_id == user_id
        ]

    def get_stats(self) -> dict[str, Any]:
        """
        Return connection statistics for monitoring.

        Returns:
            Dict with connection counts and metadata
        """
        streaming_count = sum(
            1 for c in self._connections.values() if c.is_streaming
        )
        return {
            "total_connections": self.active_count,
            "streaming_connections": streaming_count,
            "connections": [
                c.to_dict() for c in self._connections.values()
            ],
        }

    async def _heartbeat_loop(self) -> None:
        """
        Background task that sends periodic heartbeats to all connections.

        Prevents proxy servers (nginx, ALB) from closing idle WebSocket
        connections due to timeout. Also cleans up stale connections.

        Runs every HEARTBEAT_INTERVAL seconds.
        """
        logger.info("WebSocket heartbeat loop started")
        while self._connections:
            await asyncio.sleep(HEARTBEAT_INTERVAL)

            stale_ids = []
            heartbeat = HeartbeatMessage()

            for conn_id, conn in list(self._connections.items()):
                if conn.is_stale:
                    logger.warning(
                        "Stale connection detected: id=%s idle=%.0fs",
                        conn_id[:8],
                        conn.idle_seconds,
                    )
                    stale_ids.append(conn_id)
                    continue

                # Send heartbeat
                sent = await self.send_json(conn_id, heartbeat.to_dict())
                if not sent:
                    stale_ids.append(conn_id)

            # Clean up stale connections
            for conn_id in stale_ids:
                conn = self._connections.get(conn_id)
                if conn:
                    try:
                        await conn.websocket.close(code=1001)
                    except Exception:
                        pass
                await self.disconnect(conn_id)

        logger.info("WebSocket heartbeat loop stopped (no active connections)")


# ── Global Singleton ──────────────────────────────────────────────
# Import this instance in all WebSocket endpoints
ws_manager = WebSocketManager()
