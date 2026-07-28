"""
WebSocket Progress API - Step 30
AI Codebase Assistant v2.0

WebSocket endpoints for real-time task and indexing progress:

    WS  /api/v1/ws/tasks/{task_id}
        Real-time progress for a Celery agent task

    WS  /api/v1/ws/indexing/{project_id}
        Real-time progress for project indexing

    GET /api/v1/ws/status
        Current WebSocket connection stats (for monitoring)

    POST /api/v1/ws/broadcast/{channel_key}
        Broadcast a message to all clients on a channel
        (internal use by Celery workers)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


# =============================================================================
# WebSocket Endpoints
# =============================================================================

@router.websocket("/tasks/{task_id}")
async def task_progress_websocket(
    websocket: WebSocket,
    task_id: str,
) -> None:
    """
    WebSocket endpoint for real-time task progress updates.

    Connect to this endpoint to receive live progress for a
    Celery task. The connection stays open until:
        - Task reaches COMPLETED or FAILED state
        - Client disconnects
        - 20-minute timeout

    Message protocol:
        Server -> Client:
            {"type": "connected", "task_id": "...", ...}
            {"type": "waiting", "message": "..."}
            {"type": "progress", "data": {
                "status": "RUNNING",
                "progress": 0.45,
                "current_step": "analyzed",
                "agent_id": "security_scanner"
            }}
            {"type": "heartbeat", "timestamp": "..."}
            {"type": "complete", "data": {...}}
            {"type": "error", "error": "..."}

    Args:
        websocket: FastAPI WebSocket connection
        task_id:   Celery task UUID from POST /api/v1/tasks/agent
    """
    logger.info("WS task connection: task_id=%s", task_id)
    try:
        await ws_manager.connect_task(websocket, task_id)
    except WebSocketDisconnect:
        logger.info("WS task disconnected: task_id=%s", task_id)
    except Exception as exc:
        logger.error(
            "WS task error: task_id=%s error=%s", task_id, exc
        )


@router.websocket("/indexing/{project_id}")
async def indexing_progress_websocket(
    websocket: WebSocket,
    project_id: str,
) -> None:
    """
    WebSocket endpoint for real-time indexing progress.

    Connect to this endpoint to receive live progress as files
    are indexed into ChromaDB. The connection stays open until:
        - Indexing reaches COMPLETED or FAILED state
        - Client disconnects
        - 20-minute timeout

    Message protocol (same structure as task progress):
        Server -> Client:
            {"type": "connected", "project_id": "...", ...}
            {"type": "progress", "data": {
                "status": "RUNNING",
                "progress": 0.35,
                "indexed_files": 35,
                "total_files": 100,
                "current_file": "src/auth/login.py",
                "indexed_chunks": 284,
                "progress_pct": 35.0
            }}
            {"type": "complete", "data": {...}}

    Args:
        websocket:  FastAPI WebSocket connection
        project_id: Project UUID from the indexing start response
    """
    logger.info("WS indexing connection: project_id=%s", project_id)
    try:
        await ws_manager.connect_indexing(websocket, project_id)
    except WebSocketDisconnect:
        logger.info("WS indexing disconnected: project_id=%s", project_id)
    except Exception as exc:
        logger.error(
            "WS indexing error: project_id=%s error=%s",
            project_id, exc,
        )


# =============================================================================
# REST Endpoints (monitoring + internal)
# =============================================================================

@router.get(
    "/status",
    summary="WebSocket connection statistics",
    description="Returns current active connections for monitoring.",
)
async def websocket_status() -> dict[str, Any]:
    """
    Return current WebSocket connection statistics.

    Returns:
        Dict with total connections, active channels, per-channel counts
    """
    channels = ws_manager.active_channels
    return {
        "total_connections": ws_manager.active_connections,
        "active_channels": len(channels),
        "channels": {
            ch: ws_manager.connection_count(ch)
            for ch in channels
        },
        "config": {
            "poll_interval_seconds": 1.5,
            "heartbeat_interval_seconds": 30,
            "max_wait_seconds": 1200,
        },
    }


class BroadcastRequest(BaseModel):
    """Request body for the internal broadcast endpoint."""

    message: dict[str, Any]


@router.post(
    "/broadcast/{channel_key}",
    summary="Broadcast to WebSocket channel (internal)",
    description=(
        "Send a message to all WebSocket clients on a channel. "
        "Used internally by Celery workers to push updates."
    ),
)
async def broadcast_to_channel(
    channel_key: str,
    request: BroadcastRequest,
) -> dict[str, Any]:
    """
    Broadcast a message to all WebSocket clients on a channel.

    Args:
        channel_key: Channel identifier (task_id or project_id)
        request:     BroadcastRequest with message dict

    Returns:
        Dict with clients_reached count
    """
    clients_reached = await ws_manager.broadcast(
        channel_key, request.message
    )
    logger.info(
        "WS broadcast: channel=%s reached=%d",
        channel_key, clients_reached,
    )
    return {
        "channel_key": channel_key,
        "clients_reached": clients_reached,
        "status": "sent",
    }
