"""
Dedicated WebSocket API Endpoint for Real-Time Chat Streaming.

Provides a production-grade WebSocket endpoint with:
- JWT authentication via query parameter
- Connection lifecycle management via WebSocketManager
- Heartbeat/keepalive support
- Typed message protocol with validation
- Graceful error handling and reconnection support
- Full RAG pipeline integration with token streaming

Endpoint: ws://host/api/v1/ws/chat?token=<jwt>&session_id=<uuid>

Reconnection Protocol (client-side):
  1. Connect with fresh JWT token
  2. Receive 'connected' message with connection_id
  3. Send queries, receive metadata → tokens → done
  4. On disconnect: wait exponential backoff, reconnect
  5. Resume by sending same session_id to restore context
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.websocket.manager import ws_manager
from app.core.websocket.auth import authenticate_websocket, WebSocketAuthError
from app.core.websocket.protocols import (
    ClientMessage, ClientMessageType,
    ConnectedMessage, MetadataMessage, TokenMessage,
    DoneMessage, ErrorMessage, PongMessage,
)
from app.database import get_db
from app.repositories.chat_repo import ChatRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])


def _get_rag_service():
    """Lazily build RAGService to avoid startup import errors."""
    try:
        from app.core.llm.streaming import OllamaStreamingClient
        from app.core.rag.embeddings import EmbeddingService
        from app.core.rag.retriever import CodeRetriever
        from app.core.rag.vector_store import VectorStoreService
        from app.services.rag_service import RAGService
        from app.core.llm.prompt_templates import PromptType

        embedding_svc = EmbeddingService()
        vector_store  = VectorStoreService()
        retriever = CodeRetriever(
            embedding_service=embedding_svc,
            vector_store=vector_store,
        )
        streaming_client = OllamaStreamingClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout_seconds=float(settings.OLLAMA_TIMEOUT),
        )
        return RAGService(
            retriever=retriever,
            streaming_client=streaming_client,
        )
    except Exception as exc:
        logger.error("RAGService build failed: %s", exc)
        raise


def _parse_prompt_type(value: str):
    """Safely parse prompt type string."""
    try:
        from app.core.llm.prompt_templates import PromptType
        return PromptType(value)
    except (ValueError, ImportError):
        from app.core.llm.prompt_templates import PromptType
        return PromptType.CODE_QA


@router.websocket("/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: Optional[str] = None,
    session_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Production WebSocket endpoint for real-time AI chat streaming.

    Authentication: Pass JWT as ?token=<jwt> query parameter.
    Session: Pass ?session_id=<uuid> to restore conversation history.

    ── Client → Server Messages ──────────────────────────────────
    Query:
      {"type": "query", "query": str, "project_id": str,
       "prompt_type": str, "model": str, "top_k": int}

    Ping:
      {"type": "ping"}

    ── Server → Client Messages ──────────────────────────────────
    Connected (on open):
      {"type": "connected", "connection_id": str, "server_time": str}

    Metadata (before streaming):
      {"type": "metadata", "message_id": str, "sources": [...],
       "context_tokens": int, "retrieval_time_ms": float}

    Token (repeated during streaming):
      {"type": "token", "token": str, "message_id": str}

    Done (stream complete):
      {"type": "done", "message_id": str, "full_text": str,
       "model": str, "total_tokens": int, "elapsed_ms": float}

    Error:
      {"type": "error", "code": str, "message": str}

    Heartbeat (server-initiated every 30s):
      {"type": "heartbeat", "server_time": str}

    Pong (response to ping):
      {"type": "pong", "server_time": str}

    ── Reconnection Protocol ─────────────────────────────────────
    Clients should implement exponential backoff:
      attempt 1: wait 1s
      attempt 2: wait 2s
      attempt 3: wait 4s
      attempt N: wait min(2^N, 60)s
    Pass the same session_id on reconnect to restore history.
    """
    # ── Step 1: Authenticate before accepting ────────────────────
    # Get token from query params
    token = token or websocket.query_params.get("token")
    session_id = session_id or websocket.query_params.get("session_id")

    try:
        payload = await authenticate_websocket(websocket, token)
    except WebSocketAuthError as exc:
        # Must accept before we can send the error message
        await websocket.accept()
        await websocket.send_json(
            ErrorMessage(message=exc.message, code=exc.code).to_dict()
        )
        await websocket.close(code=4001)
        return

    user_id = payload.get("sub")

    # ── Step 2: Accept and register connection ───────────────────
    await websocket.accept()
    conn = await ws_manager.connect(
        websocket=websocket,
        user_id=user_id,
        session_id=session_id,
    )

    # ── Step 3: Send connected confirmation ─────────────────────
    connected_msg = ConnectedMessage(connection_id=conn.connection_id)
    await websocket.send_json(connected_msg.to_dict())
    logger.info(
        "WebSocket session started: conn=%s user=%s session=%s",
        conn.connection_id[:8],
        user_id,
        session_id,
    )

    # ── Step 4: Message processing loop ─────────────────────────
    chat_repo = ChatRepository(db)

    try:
        while True:
            # Receive next client message with timeout
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=CONNECTION_TIMEOUT_SECONDS,
                )
                conn.touch()
            except asyncio.TimeoutError:
                logger.warning(
                    "WebSocket receive timeout: conn=%s", conn.connection_id[:8]
                )
                break
            except WebSocketDisconnect:
                logger.info(
                    "Client disconnected: conn=%s", conn.connection_id[:8]
                )
                break

            # Parse JSON
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    ErrorMessage(
                        message="Invalid JSON format",
                        code="INVALID_JSON",
                    ).to_dict()
                )
                continue

            msg_type = data.get("type", "")

            # ── Handle PING ──────────────────────────────────────
            if msg_type == ClientMessageType.PING:
                await websocket.send_json(PongMessage().to_dict())
                continue

            # ── Handle DISCONNECT ────────────────────────────────
            if msg_type == ClientMessageType.DISCONNECT:
                logger.info("Client requested disconnect: conn=%s", conn.connection_id[:8])
                break

            # ── Handle QUERY ─────────────────────────────────────
            if msg_type == ClientMessageType.QUERY:
                is_valid, error_msg, query_data = ClientMessage.validate_query(data)
                if not is_valid:
                    await websocket.send_json(
                        ErrorMessage(message=error_msg, code="INVALID_QUERY").to_dict()
                    )
                    continue

                await _handle_query(
                    websocket=websocket,
                    conn=conn,
                    query_data=query_data,
                    chat_repo=chat_repo,
                    session_id=session_id,
                )
                continue

            # Unknown message type
            await websocket.send_json(
                ErrorMessage(
                    message=f"Unknown message type: {msg_type}",
                    code="UNKNOWN_TYPE",
                ).to_dict()
            )

    except Exception as exc:
        logger.error(
            "WebSocket fatal error: conn=%s error=%s",
            conn.connection_id[:8],
            exc,
            exc_info=True,
        )
        try:
            await websocket.send_json(
                ErrorMessage(message=str(exc), code="FATAL_ERROR").to_dict()
            )
        except Exception:
            pass

    finally:
        await ws_manager.disconnect(conn.connection_id)
        logger.info(
            "WebSocket closed: conn=%s total_remaining=%d",
            conn.connection_id[:8],
            ws_manager.active_count,
        )


# Timeout for waiting on client messages (seconds)
CONNECTION_TIMEOUT_SECONDS = 120.0


async def _handle_query(
    websocket: WebSocket,
    conn,
    query_data: dict,
    chat_repo: ChatRepository,
    session_id: Optional[str],
) -> None:
    """
    Handle a QUERY message: retrieve → augment → stream → persist.

    This is the core streaming flow:
    1. Get conversation history from DB
    2. Run RAG retrieval
    3. Send METADATA to client (sources available immediately)
    4. Stream LLM tokens to client
    5. Send DONE message with full text
    6. Persist both user message and AI response to DB

    Args:
        websocket: Active WebSocket connection
        conn: WebSocketConnection with metadata
        query_data: Validated query payload
        chat_repo: Database repository for chat persistence
        session_id: Optional session UUID string
    """
    query       = query_data["query"]
    project_id  = query_data["project_id"]
    prompt_type = _parse_prompt_type(query_data["prompt_type"])
    model       = query_data.get("model") or settings.OLLAMA_DEFAULT_MODEL
    top_k       = query_data["top_k"]

    conn.is_streaming = True
    start_time = time.perf_counter()
    message_id = None

    try:
        # 1. Load conversation history
        history = ""
        if session_id:
            try:
                session_uuid = UUID(session_id)
                history = await chat_repo.get_conversation_history(
                    session_id=session_uuid, last_n=6
                )
            except (ValueError, Exception) as exc:
                logger.warning("Could not load history for session %s: %s", session_id, exc)

        # 2. Setup RAG streaming pipeline
        try:
            rag_service = _get_rag_service()
            message_id, metadata, token_stream = await rag_service.stream_ask(
                query=query,
                project_id=project_id,
                prompt_type=prompt_type,
                model=model,
                top_k=top_k,
                conversation_history=history or None,
            )
        except Exception as exc:
            logger.error("RAG setup failed: %s", exc)
            await websocket.send_json(
                ErrorMessage(
                    message=f"AI service error: {exc}",
                    code="RAG_ERROR",
                ).to_dict()
            )
            return

        # 3. Send METADATA immediately (sources available before streaming)
        meta_msg = MetadataMessage(
            message_id=message_id,
            sources=metadata.get("sources", []),
            context_tokens=metadata.get("context_tokens", 0),
            retrieval_time_ms=metadata.get(
                "retrieval", {}
            ).get("retrieval_time_ms", 0) if isinstance(metadata.get("retrieval"), dict)
            else 0,
        )
        await websocket.send_json(meta_msg.to_dict())

        # 4. Persist user message to DB
        if session_id:
            try:
                await chat_repo.add_message(
                    session_id=UUID(session_id),
                    role="user",
                    content=query,
                    prompt_type=prompt_type.value,
                )
            except Exception as exc:
                logger.warning("Failed to persist user message: %s", exc)

        # 5. Stream tokens to client
        tokens: list[str] = []
        final_model = model
        final_tokens = 0

        async for chunk in token_stream:
            if chunk.is_final:
                final_model = chunk.model or model
                final_tokens = chunk.total_tokens
                break

            tokens.append(chunk.token)
            token_msg = TokenMessage(token=chunk.token, message_id=message_id)
            try:
                await websocket.send_json(token_msg.to_dict())
            except Exception as exc:
                logger.warning("Token send failed: %s", exc)
                break

        full_text = "".join(tokens)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # 6. Send DONE message
        done_msg = DoneMessage(
            message_id=message_id,
            full_text=full_text,
            model=final_model,
            total_tokens=final_tokens,
            elapsed_ms=elapsed_ms,
        )
        await websocket.send_json(done_msg.to_dict())

        # 7. Persist AI response to DB
        if session_id and full_text:
            try:
                await chat_repo.add_message(
                    session_id=UUID(session_id),
                    role="assistant",
                    content=full_text,
                    model_used=final_model,
                    sources=metadata.get("sources", []),
                    context_tokens=metadata.get("context_tokens", 0),
                    llm_time_ms=elapsed_ms,
                    total_time_ms=elapsed_ms,
                    tokens_generated=final_tokens,
                )
            except Exception as exc:
                logger.warning("Failed to persist assistant message: %s", exc)

        logger.info(
            "Query complete: conn=%s tokens=%d elapsed=%.0fms",
            conn.connection_id[:8],
            final_tokens,
            elapsed_ms,
        )

    except Exception as exc:
        logger.error("Query handler error: %s", exc, exc_info=True)
        await websocket.send_json(
            ErrorMessage(
                message=str(exc),
                code="QUERY_ERROR",
                message_id=message_id,
            ).to_dict()
        )

    finally:
        conn.is_streaming = False


@router.get(
    "/stats",
    summary="WebSocket connection statistics",
    description="Returns current WebSocket connection count and metadata. Useful for monitoring.",
)
async def websocket_stats() -> dict:
    """Return current WebSocket connection statistics."""
    return ws_manager.get_stats()
