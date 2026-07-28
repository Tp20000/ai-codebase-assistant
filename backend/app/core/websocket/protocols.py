"""
WebSocket Message Protocol Definitions.

Defines all message types, schemas, and validators for the
WebSocket communication protocol between client and server.

Protocol flow:
  Client → Server:  CONNECT, QUERY, PING, DISCONNECT
  Server → Client:  CONNECTED, METADATA, TOKEN, DONE, ERROR, PONG, HEARTBEAT

All messages are JSON objects with a mandatory 'type' field.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid


# ─────────────────────────────────────────────────────────────────
# Message Type Enums
# ─────────────────────────────────────────────────────────────────

class ClientMessageType(str, Enum):
    """Message types that clients send to the server."""
    QUERY     = "query"       # Start a RAG query (streaming response)
    PING      = "ping"        # Keepalive ping
    DISCONNECT = "disconnect" # Graceful client disconnect


class ServerMessageType(str, Enum):
    """Message types that the server sends to clients."""
    CONNECTED  = "connected"  # Sent immediately after WebSocket accept
    METADATA   = "metadata"   # RAG retrieval metadata (sources, message_id)
    TOKEN      = "token"      # Single LLM output token
    DONE       = "done"       # Stream complete, full_text included
    ERROR      = "error"      # Error occurred
    PONG       = "pong"       # Response to client ping
    HEARTBEAT  = "heartbeat"  # Server-initiated keepalive


# ─────────────────────────────────────────────────────────────────
# Server → Client Message Builders
# ─────────────────────────────────────────────────────────────────

@dataclass
class ConnectedMessage:
    """Sent to client immediately after WebSocket connection is established."""
    type: str = field(default=ServerMessageType.CONNECTED, init=False)
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    server_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    protocol_version: str = "2.0"
    message: str = "Connected to AI Codebase Assistant WebSocket"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MetadataMessage:
    """
    Sent before streaming begins. Contains retrieval metadata
    so the UI can show sources before the answer arrives.
    """
    message_id: str
    sources: list[dict[str, Any]]
    context_tokens: int
    retrieval_time_ms: float
    type: str = field(default=ServerMessageType.METADATA, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message_id": self.message_id,
            "sources": self.sources,
            "context_tokens": self.context_tokens,
            "retrieval_time_ms": round(self.retrieval_time_ms, 2),
        }


@dataclass
class TokenMessage:
    """
    A single token from the LLM stream.
    Sent repeatedly during generation, one per token.
    """
    token: str
    message_id: str
    type: str = field(default=ServerMessageType.TOKEN, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "token": self.token,
            "message_id": self.message_id,
        }


@dataclass
class DoneMessage:
    """
    Sent when token streaming is complete.
    Contains the full assembled text and generation metrics.
    """
    message_id: str
    full_text: str
    model: str
    total_tokens: int
    elapsed_ms: float
    cached: bool = False
    type: str = field(default=ServerMessageType.DONE, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message_id": self.message_id,
            "full_text": self.full_text,
            "model": self.model,
            "total_tokens": self.total_tokens,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "cached": self.cached,
        }


@dataclass
class ErrorMessage:
    """Sent when an error occurs during processing."""
    message: str
    code: str = "INTERNAL_ERROR"
    message_id: Optional[str] = None
    type: str = field(default=ServerMessageType.ERROR, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "code": self.code,
            "message": self.message,
            "message_id": self.message_id,
        }


@dataclass
class PongMessage:
    """Response to client ping for keepalive."""
    server_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    type: str = field(default=ServerMessageType.PONG, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "server_time": self.server_time}


@dataclass
class HeartbeatMessage:
    """Server-initiated keepalive message."""
    server_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    type: str = field(default=ServerMessageType.HEARTBEAT, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "server_time": self.server_time}


# ─────────────────────────────────────────────────────────────────
# Client Message Validator
# ─────────────────────────────────────────────────────────────────

class ClientMessage:
    """
    Validates and parses incoming client WebSocket messages.

    All client messages must be JSON with a 'type' field.
    This class validates structure and extracts typed payloads.
    """

    @staticmethod
    def validate_query(data: dict[str, Any]) -> tuple[bool, str, dict]:
        """
        Validate a QUERY message from the client.

        Expected format:
        {
            "type": "query",
            "query": str,           # required, 1-4000 chars
            "project_id": str,      # required UUID
            "prompt_type": str,     # optional, default "code_qa"
            "model": str,           # optional model override
            "top_k": int,           # optional, 1-20
            "session_id": str       # optional for history
        }

        Returns:
            (is_valid, error_message, validated_payload)
        """
        query = data.get("query", "").strip()
        if not query:
            return False, "query field is required and cannot be empty", {}
        if len(query) > 4000:
            return False, "query exceeds 4000 character limit", {}

        project_id = data.get("project_id", "").strip()
        if not project_id:
            return False, "project_id is required", {}

        # Validate top_k range
        top_k = data.get("top_k", 8)
        try:
            top_k = int(top_k)
            top_k = max(1, min(top_k, 20))
        except (ValueError, TypeError):
            top_k = 8

        return True, "", {
            "query": query,
            "project_id": project_id,
            "prompt_type": data.get("prompt_type", "code_qa"),
            "model": data.get("model"),
            "top_k": top_k,
            "session_id": data.get("session_id"),
        }
