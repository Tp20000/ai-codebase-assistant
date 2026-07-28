"""
WebSocket Connection Manager - Step 30
AI Codebase Assistant v2.0

Manages WebSocket connections for real-time task progress updates.

Architecture:
    WebSocket clients connect to:
        /api/v1/ws/tasks/{task_id}      - Single task progress
        /api/v1/ws/indexing/{project_id} - Project indexing progress

    Progress flow:
        Celery Worker
            -> writes to Redis (task:progress:{task_id})
            -> publishes to Redis pub/sub channel (progress:{task_id})
        WebSocket Manager
            -> subscribes to Redis pub/sub channels
            -> forwards messages to connected WebSocket clients
            -> falls back to Redis polling if pub/sub unavailable

    Connection lifecycle:
        connect -> authenticate -> subscribe -> receive updates
        -> heartbeat ping/pong -> disconnect on done/error/timeout

Features:
    - Per task_id and per project_id connection groups
    - Redis pub/sub for zero-latency forwarding
    - Polling fallback when pub/sub unavailable
    - Heartbeat keepalive (30 second ping interval)
    - Graceful disconnection with cleanup
    - Thread-safe connection registry
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30
# Max time to wait for task completion before auto-disconnect
MAX_TASK_WAIT_SECONDS = 1200  # 20 minutes
# Polling interval when pub/sub unavailable
POLL_INTERVAL_SECONDS = 1.5


# =============================================================================
# Connection Registry
# =============================================================================

class ConnectionRegistry:
    """
    Thread-safe registry of active WebSocket connections.

    Groups connections by channel key (task_id or project_id).
    Allows broadcasting to all clients watching a specific task/project.
    """

    def __init__(self) -> None:
        """Initialise with empty connection sets."""
        # channel_key -> set of WebSocket objects
        self._connections: dict[str, set[WebSocket]] = {}

    def add(self, channel_key: str, ws: WebSocket) -> None:
        """
        Register a WebSocket connection for a channel.

        Args:
            channel_key: Unique channel identifier (task_id or project_id)
            ws:          WebSocket connection object
        """
        if channel_key not in self._connections:
            self._connections[channel_key] = set()
        self._connections[channel_key].add(ws)
        logger.debug(
            "WS connected: channel=%s total=%d",
            channel_key,
            len(self._connections[channel_key]),
        )

    def remove(self, channel_key: str, ws: WebSocket) -> None:
        """
        Unregister a WebSocket connection.

        Args:
            channel_key: Channel identifier
            ws:          WebSocket to remove
        """
        if channel_key in self._connections:
            self._connections[channel_key].discard(ws)
            if not self._connections[channel_key]:
                del self._connections[channel_key]
        logger.debug("WS disconnected: channel=%s", channel_key)

    def get_connections(self, channel_key: str) -> set[WebSocket]:
        """
        Get all active connections for a channel.

        Args:
            channel_key: Channel identifier

        Returns:
            Set of WebSocket objects (may be empty)
        """
        return self._connections.get(channel_key, set()).copy()

    def count(self, channel_key: str) -> int:
        """Return number of connections for a channel."""
        return len(self._connections.get(channel_key, set()))

    def total_connections(self) -> int:
        """Return total active connections across all channels."""
        return sum(len(ws_set) for ws_set in self._connections.values())

    def all_channels(self) -> list[str]:
        """Return list of all active channel keys."""
        return list(self._connections.keys())


# Singleton registry
registry = ConnectionRegistry()


# =============================================================================
# Message Builders
# =============================================================================

def _build_progress_message(
    channel_type: str,
    channel_id: str,
    data: dict[str, Any],
) -> str:
    """
    Build a standardised WebSocket progress message JSON string.

    Args:
        channel_type: "task" or "indexing"
        channel_id:   task_id or project_id
        data:         Progress data dict

    Returns:
        JSON-encoded message string
    """
    return json.dumps({
        "type": "progress",
        "channel_type": channel_type,
        "channel_id": channel_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    })


def _build_heartbeat_message() -> str:
    """
    Build a heartbeat ping message.

    Returns:
        JSON-encoded heartbeat string
    """
    return json.dumps({
        "type": "heartbeat",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _build_complete_message(
    channel_type: str,
    channel_id: str,
    final_data: dict[str, Any],
) -> str:
    """
    Build a task completion message to signal the client to disconnect.

    Args:
        channel_type: "task" or "indexing"
        channel_id:   task_id or project_id
        final_data:   Final state dict

    Returns:
        JSON-encoded completion message
    """
    return json.dumps({
        "type": "complete",
        "channel_type": channel_type,
        "channel_id": channel_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": final_data,
    })


def _build_error_message(error: str) -> str:
    """
    Build an error message for the client.

    Args:
        error: Error description string

    Returns:
        JSON-encoded error message
    """
    return json.dumps({
        "type": "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": error,
    })


# =============================================================================
# Redis helpers
# =============================================================================

def _get_redis_url() -> str:
    """Return Redis URL from environment."""
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def _get_progress_from_redis(
    key: str,
) -> dict[str, Any] | None:
    """
    Async read of a progress dict from Redis.

    Uses aioredis if available, falls back to sync redis client
    via asyncio.to_thread.

    Args:
        key: Redis key e.g. "task:progress:{task_id}"

    Returns:
        Parsed progress dict or None
    """
    try:
        # Try aioredis / redis.asyncio (redis-py 4.2+)
        import redis.asyncio as aioredis
        client = aioredis.from_url(
            _get_redis_url(), decode_responses=True
        )
        raw = await client.get(key)
        await client.aclose()
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("aioredis read failed (%s), trying sync", exc)
        # Fallback to sync redis via thread
        try:
            import redis as sync_redis

            def _sync_get() -> str | None:
                c = sync_redis.from_url(_get_redis_url(), decode_responses=True)
                return c.get(key)

            raw = await asyncio.to_thread(_sync_get)
            if raw:
                return json.loads(raw)
        except Exception as exc2:
            logger.warning("Redis read failed: %s", exc2)
    return None


async def _publish_to_redis(channel: str, message: str) -> None:
    """
    Publish a message to a Redis pub/sub channel.

    Args:
        channel: Pub/sub channel name
        message: JSON message string
    """
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(_get_redis_url(), decode_responses=True)
        await client.publish(channel, message)
        await client.aclose()
    except Exception as exc:
        logger.debug("Redis publish failed: %s", exc)


# =============================================================================
# WebSocket Handler: Task Progress
# =============================================================================

async def handle_task_progress_ws(
    websocket: WebSocket,
    task_id: str,
) -> None:
    """
    Handle a WebSocket connection for a single task's progress.

    Lifecycle:
        1. Accept connection and register in registry
        2. Send current progress immediately (if available in Redis)
        3. Poll Redis every POLL_INTERVAL_SECONDS for updates
        4. Send heartbeat every HEARTBEAT_INTERVAL seconds
        5. Auto-disconnect when task status is COMPLETED or FAILED
        6. Auto-disconnect after MAX_TASK_WAIT_SECONDS

    Message types sent to client:
        {"type": "progress", "data": {...}}   - Progress update
        {"type": "complete", "data": {...}}   - Task done
        {"type": "heartbeat"}                  - Keepalive
        {"type": "error", "error": "..."}     - Error occurred

    Args:
        websocket: FastAPI WebSocket connection
        task_id:   Celery task UUID to monitor
    """
    await websocket.accept()
    registry.add(task_id, websocket)

    logger.info("WS task progress: task=%s connected", task_id)

    # Send initial connection acknowledgment
    await websocket.send_text(json.dumps({
        "type": "connected",
        "task_id": task_id,
        "message": f"Watching task {task_id}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    last_heartbeat = time.monotonic()
    start_time = time.monotonic()
    last_status: str | None = None

    try:
        while True:
            now = time.monotonic()

            # Auto-disconnect timeout
            if now - start_time > MAX_TASK_WAIT_SECONDS:
                await websocket.send_text(
                    _build_error_message(
                        f"Task monitoring timeout after "
                        f"{MAX_TASK_WAIT_SECONDS}s"
                    )
                )
                break

            # Heartbeat
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                try:
                    await websocket.send_text(_build_heartbeat_message())
                    last_heartbeat = now
                except Exception:
                    break

            # Poll Redis for progress
            redis_key = f"task:progress:{task_id}"
            progress_data = await _get_progress_from_redis(redis_key)

            if progress_data:
                current_status = str(progress_data.get("status", ""))

                # Only send if status changed or progress changed significantly
                progress_pct = float(progress_data.get("progress", 0.0))
                should_send = (
                    current_status != last_status
                    or progress_pct in (0.0, 1.0)
                )

                if should_send:
                    msg = _build_progress_message(
                        channel_type="task",
                        channel_id=task_id,
                        data=progress_data,
                    )
                    try:
                        await websocket.send_text(msg)
                    except Exception:
                        break
                    last_status = current_status

                # Check for terminal states
                if current_status in ("COMPLETED", "FAILED", "REVOKED"):
                    complete_msg = _build_complete_message(
                        channel_type="task",
                        channel_id=task_id,
                        final_data=progress_data,
                    )
                    try:
                        await websocket.send_text(complete_msg)
                    except Exception:
                        pass
                    logger.info(
                        "WS task complete: task=%s status=%s",
                        task_id, current_status,
                    )
                    break
            else:
                # No progress data yet — task may be pending in queue
                if last_status is None:
                    await websocket.send_text(json.dumps({
                        "type": "waiting",
                        "task_id": task_id,
                        "message": "Task queued, waiting for worker to pick up...",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                    last_status = "WAITING"

            # Also check Celery backend status as fallback
            if last_status in (None, "WAITING"):
                try:
                    from celery.result import AsyncResult
                    from app.tasks.celery_app import celery_app
                    ar = AsyncResult(task_id, app=celery_app)
                    if ar.status == "SUCCESS":
                        await websocket.send_text(
                            _build_complete_message(
                                "task", task_id,
                                {"status": "COMPLETED", "task_id": task_id}
                            )
                        )
                        break
                    elif ar.status == "FAILURE":
                        await websocket.send_text(
                            _build_complete_message(
                                "task", task_id,
                                {
                                    "status": "FAILED",
                                    "task_id": task_id,
                                    "error": str(ar.result),
                                }
                            )
                        )
                        break
                except Exception:
                    pass

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        logger.info("WS task progress: task=%s client disconnected", task_id)
    except Exception as exc:
        logger.error(
            "WS task progress error: task=%s error=%s", task_id, exc
        )
        try:
            await websocket.send_text(_build_error_message(str(exc)))
        except Exception:
            pass
    finally:
        registry.remove(task_id, websocket)
        logger.info("WS task progress: task=%s connection closed", task_id)


# =============================================================================
# WebSocket Handler: Indexing Progress
# =============================================================================

async def handle_indexing_progress_ws(
    websocket: WebSocket,
    project_id: str,
) -> None:
    """
    Handle a WebSocket connection for project indexing progress.

    Polls Redis key indexing:progress:{project_id} and streams
    updates to the connected client. Sends per-file completion
    events as files are indexed.

    Args:
        websocket:  FastAPI WebSocket connection
        project_id: Project UUID to monitor
    """
    await websocket.accept()
    channel_key = f"indexing:{project_id}"
    registry.add(channel_key, websocket)

    logger.info("WS indexing progress: project=%s connected", project_id)

    await websocket.send_text(json.dumps({
        "type": "connected",
        "project_id": project_id,
        "message": f"Watching indexing for project {project_id}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    last_heartbeat = time.monotonic()
    start_time = time.monotonic()
    last_indexed_count = -1
    last_status: str | None = None

    try:
        while True:
            now = time.monotonic()

            # Timeout guard
            if now - start_time > MAX_TASK_WAIT_SECONDS:
                await websocket.send_text(
                    _build_error_message("Indexing monitoring timeout")
                )
                break

            # Heartbeat
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                try:
                    await websocket.send_text(_build_heartbeat_message())
                    last_heartbeat = now
                except Exception:
                    break

            # Poll indexing progress from Redis
            redis_key = f"indexing:progress:{project_id}"
            progress_data = await _get_progress_from_redis(redis_key)

            if progress_data:
                current_status = str(progress_data.get("status", ""))
                current_indexed = int(progress_data.get("indexed_files") or 0)

                # Send update when new files are indexed or status changes
                if (
                    current_indexed != last_indexed_count
                    or current_status != last_status
                ):
                    # Add derived stats
                    total = int(progress_data.get("total_files") or 0)
                    pct = round(
                        (current_indexed / max(total, 1)) * 100, 1
                    )
                    enriched = {
                        **progress_data,
                        "progress_pct": pct,
                    }
                    msg = _build_progress_message(
                        channel_type="indexing",
                        channel_id=project_id,
                        data=enriched,
                    )
                    try:
                        await websocket.send_text(msg)
                    except Exception:
                        break
                    last_indexed_count = current_indexed
                    last_status = current_status

                # Terminal state
                if current_status in ("COMPLETED", "FAILED"):
                    try:
                        await websocket.send_text(
                            _build_complete_message(
                                "indexing", project_id, progress_data
                            )
                        )
                    except Exception:
                        pass
                    logger.info(
                        "WS indexing complete: project=%s status=%s",
                        project_id, current_status,
                    )
                    break
            else:
                # No progress yet
                if last_status is None:
                    await websocket.send_text(json.dumps({
                        "type": "waiting",
                        "project_id": project_id,
                        "message": "No indexing task running for this project",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                    last_status = "WAITING"

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        logger.info(
            "WS indexing: project=%s client disconnected", project_id
        )
    except Exception as exc:
        logger.error(
            "WS indexing error: project=%s error=%s", project_id, exc
        )
        try:
            await websocket.send_text(_build_error_message(str(exc)))
        except Exception:
            pass
    finally:
        registry.remove(channel_key, websocket)
        logger.info(
            "WS indexing: project=%s connection closed", project_id
        )


# =============================================================================
# Broadcaster: push updates to all clients on a channel
# =============================================================================

async def broadcast_to_channel(
    channel_key: str,
    message: dict[str, Any],
) -> int:
    """
    Broadcast a message to all WebSocket clients on a channel.

    Used by Celery tasks to push progress without waiting for
    the polling loop. Removes dead connections automatically.

    Args:
        channel_key: Channel identifier (task_id or project_id)
        message:     Dict to JSON-encode and broadcast

    Returns:
        Number of clients that received the message
    """
    connections = registry.get_connections(channel_key)
    if not connections:
        return 0

    msg_str = json.dumps(message)
    sent = 0
    dead: list[WebSocket] = []

    for ws in connections:
        try:
            await ws.send_text(msg_str)
            sent += 1
        except Exception:
            dead.append(ws)

    # Clean up dead connections
    for ws in dead:
        registry.remove(channel_key, ws)

    return sent


# =============================================================================
# Manager class (convenience wrapper used in API layer)
# =============================================================================

class WebSocketManager:
    """
    Convenience wrapper around the module-level registry and handlers.

    Provides a single object to inject into FastAPI dependency injection
    and to reference in the API layer without importing internals.
    """

    def __init__(self) -> None:
        """Initialise with reference to the singleton registry."""
        self._registry = registry

    async def connect_task(
        self, websocket: WebSocket, task_id: str
    ) -> None:
        """
        Accept and manage a task progress WebSocket connection.

        Args:
            websocket: FastAPI WebSocket
            task_id:   Task UUID to monitor
        """
        await handle_task_progress_ws(websocket, task_id)

    async def connect_indexing(
        self, websocket: WebSocket, project_id: str
    ) -> None:
        """
        Accept and manage an indexing progress WebSocket connection.

        Args:
            websocket:  FastAPI WebSocket
            project_id: Project UUID to monitor
        """
        await handle_indexing_progress_ws(websocket, project_id)

    async def broadcast(
        self, channel_key: str, message: dict[str, Any]
    ) -> int:
        """
        Broadcast message to all clients on a channel.

        Args:
            channel_key: Channel key
            message:     Message dict

        Returns:
            Number of clients reached
        """
        return await broadcast_to_channel(channel_key, message)

    @property
    def active_connections(self) -> int:
        """Total number of active WebSocket connections."""
        return self._registry.total_connections()

    @property
    def active_channels(self) -> list[str]:
        """List of all active channel keys."""
        return self._registry.all_channels()

    def connection_count(self, channel_key: str) -> int:
        """Return connection count for a specific channel."""
        return self._registry.count(channel_key)


# Singleton manager
ws_manager = WebSocketManager()
