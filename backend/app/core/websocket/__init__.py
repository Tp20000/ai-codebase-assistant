"""WebSocket infrastructure module."""
from app.core.websocket.manager import WebSocketManager, WebSocketConnection, ws_manager
from app.core.websocket.protocols import (
    ClientMessageType, ServerMessageType,
    ConnectedMessage, MetadataMessage, TokenMessage,
    DoneMessage, ErrorMessage, PongMessage, HeartbeatMessage,
    ClientMessage,
)
from app.core.websocket.auth import authenticate_websocket, WebSocketAuthError

__all__ = [
    "WebSocketManager", "WebSocketConnection", "ws_manager",
    "ClientMessageType", "ServerMessageType",
    "ConnectedMessage", "MetadataMessage", "TokenMessage",
    "DoneMessage", "ErrorMessage", "PongMessage", "HeartbeatMessage",
    "ClientMessage",
    "authenticate_websocket", "WebSocketAuthError",
]
