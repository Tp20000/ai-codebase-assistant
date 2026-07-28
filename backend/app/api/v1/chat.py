"""
Chat API endpoints with REST and WebSocket support.

Provides:
- POST   /chat/sessions               - Create conversation
- GET    /chat/sessions               - List conversations
- GET    /chat/sessions/{id}          - Get session + messages
- POST   /chat/sessions/{id}/ask      - Non-streaming query
- WS     /chat/sessions/{id}/stream   - Streaming WebSocket
- DELETE /chat/sessions/{id}          - Delete conversation
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories.chat_repo import ChatRepository
from app.utils.jwt_handler import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


# ─────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """Request body for creating a new chat session."""
    project_id: UUID = Field(..., description="Project to chat about")
    title: str = Field(default="New Conversation", max_length=255)


class CreateSessionResponse(BaseModel):
    """Response after creating a chat session."""
    session_id: str
    title: str
    project_id: str
    created_at: str


class AskRequest(BaseModel):
    """Request body for a non-streaming RAG query."""
    query: str = Field(..., min_length=1, max_length=4000)
    prompt_type: str = Field(default="code_qa")
    model: Optional[str] = Field(default=None)
    top_k: int = Field(default=8, ge=1, le=20)
    language_filter: Optional[str] = Field(default=None)
    use_cache: bool = Field(default=True)
    # Frontend sends these for direct file context injection
    content: Optional[str] = Field(default=None)
    file_context: Optional[str] = Field(default=None)
    code_context: Optional[str] = Field(default=None)
    message: Optional[str] = Field(default=None)


class AskResponse(BaseModel):
    """Response from a non-streaming RAG query."""

    # Suppress Pydantic protected namespace warning for 'model_' prefix
    model_config = ConfigDict(protected_namespaces=())

    message_id: str
    answer: str
    sources: list[dict[str, Any]]
    cached: bool
    timing: dict[str, Any]
    llm_model: str          # renamed from 'model' to avoid Pydantic conflict
    context_tokens: int
    tokens_generated: int


class SessionListItem(BaseModel):
    """Session summary for list responses."""
    session_id: str
    title: str
    project_id: str
    message_count: int
    created_at: str
    updated_at: str


class MessageItem(BaseModel):
    """A single message in a session detail response."""

    # Suppress protected namespace warning
    model_config = ConfigDict(protected_namespaces=())

    message_id: str
    role: str
    content: str
    prompt_type: Optional[str] = None
    llm_model: Optional[str] = None    # renamed from model_used
    sources: Optional[list[dict[str, Any]]] = None
    cached: bool = False
    created_at: str


# ─────────────────────────────────────────────────────────────────
# Lazy RAG service builder (avoids import errors at module load)
# ─────────────────────────────────────────────────────────────────

def _build_rag_service():
    """
    Lazily instantiate RAGService only when an endpoint is called.
    This prevents import failures from blocking the entire API at startup.
    """
    try:
        from app.core.llm.streaming import OllamaStreamingClient
        from app.core.rag.embeddings import EmbeddingService
        from app.core.rag.retriever import CodeRetriever
        from app.core.rag.vector_store import VectorStoreService
        from app.services.rag_service import RAGService

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
        logger.error("Failed to build RAGService: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service unavailable: {exc}",
        )


def _parse_prompt_type(prompt_type_str: str):
    """Safely parse prompt type string to PromptType enum."""
    try:
        from app.core.llm.prompt_templates import PromptType
        return PromptType(prompt_type_str)
    except (ValueError, ImportError):
        from app.core.llm.prompt_templates import PromptType
        return PromptType.CODE_QA


# ─────────────────────────────────────────────────────────────────
# REST Endpoints
# ─────────────────────────────────────────────────────────────────

@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
    description="Creates a conversation thread for a project. Each session maintains its own message history.",
)
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CreateSessionResponse:
    """Create a new conversation thread for a project."""
    chat_repo = ChatRepository(db)
    session = await chat_repo.create_session(
        project_id=body.project_id,
        user_id=current_user.id,
        title=body.title,
    )
    return CreateSessionResponse(
        session_id=str(session.id),
        title=session.title,
        project_id=str(session.project_id),
        created_at=session.created_at.isoformat(),
    )


@router.get(
    "/sessions",
    response_model=list[SessionListItem],
    summary="List chat sessions for a project",
)
async def list_sessions(
    project_id: UUID = Query(..., description="Project ID to list sessions for"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[SessionListItem]:
    """List all active chat sessions for a project owned by the current user."""
    chat_repo = ChatRepository(db)
    sessions = await chat_repo.list_sessions(
        project_id=project_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [
        SessionListItem(
            session_id=str(s.id),
            title=s.title,
            project_id=str(s.project_id),
            message_count=s.message_count,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    summary="Get session with full message history",
)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve a chat session with all messages eagerly loaded."""
    chat_repo = ChatRepository(db)
    session = await chat_repo.get_session_with_messages(
        session_id=session_id,
        user_id=current_user.id,
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found or access denied",
        )

    messages = [
        {
            "message_id": str(m.id),
            "role": m.role,
            "content": m.content,
            "prompt_type": m.prompt_type,
            "llm_model": m.model_used,
            "sources": m.sources or [],
            "cached": m.cached,
            "created_at": m.created_at.isoformat(),
        }
        for m in session.messages
    ]

    return {
        "session_id": str(session.id),
        "title": session.title,
        "project_id": str(session.project_id),
        "message_count": session.message_count,
        "messages": messages,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.post(
    "/sessions/{session_id}/ask",
    response_model=AskResponse,
    summary="Ask a question (non-streaming)",
    description="Submit a question and receive a complete RAG-powered response. Use the WebSocket /stream endpoint for real-time streaming.",
)
async def ask_question(
    session_id: UUID,
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AskResponse:
    """Ask a question and get a complete RAG response with source attribution."""
    chat_repo = ChatRepository(db)

    # Verify session ownership
    session = await chat_repo.get_session_with_messages(
        session_id=session_id,
        user_id=current_user.id,
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    # Get recent conversation for multi-turn context
    conversation_history = await chat_repo.get_conversation_history(
        session_id=session_id, last_n=6
    )

    prompt_type = _parse_prompt_type(body.prompt_type)
    rag_service = _build_rag_service()

    # Inject file content directly into query when frontend sends it
    # This bypasses ChromaDB when files are not yet indexed
    effective_query = body.query or body.content or body.message or ""
    if body.file_context or body.code_context:
        file_ref = body.file_context or ""
        extra = body.code_context or ""

        if file_ref:
            effective_query = (
                f"[Context: file {file_ref}]\n\n"
                f"{effective_query}"
            )

        if extra:
            effective_query = (
                f"{effective_query}\n\n"
                f"[Actual File Content]\n"
                f"```\n{extra}\n```\n\n"
                f"Please answer the user's question specifically based on the file content above."
            )

    # ── Direct Ollama path when file content is provided ─────────────
    # If the frontend sends code_context (actual file content), bypass
    # the RAG/ChromaDB pipeline and call Ollama directly with the file.
    # This guarantees the model sees the real code even when files are
    # not yet indexed into ChromaDB.
    if body.code_context and len(body.code_context.strip()) > 0:
        try:
            from app.core.llm.streaming import OllamaStreamingClient
            import uuid as _uuid

            direct_client = OllamaStreamingClient(
                base_url=settings.OLLAMA_BASE_URL,
                timeout_seconds=float(settings.OLLAMA_TIMEOUT),
            )

            file_ref = body.file_context or "the provided file"
            user_question = body.query or body.content or body.message or effective_query

            # Build a focused, file-aware prompt
            system_prompt = (
                "You are an expert software engineer analyzing source code. "
                "The user has provided actual file content. "
                "Answer ONLY based on the specific code shown. "
                "Be precise and reference the actual code in your answer."
            )
            user_message = (
                f"File: {file_ref}\n\n"
                f"```\n{body.code_context.strip()}\n```\n\n"
                f"Question: {user_question}\n\n"
                f"Answer based on the code above:"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ]

            use_model = body.model or settings.OLLAMA_DEFAULT_MODEL
            direct_result = await direct_client.collect_stream(
                model=use_model,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )

            answer        = direct_result.full_text or "No response generated."
            sources       = []
            timing        = {"total_ms": 0, "llm_ms": 0, "retrieval_ms": 0}
            model_used    = use_model
            context_tokens = len(body.code_context) // 4
            tokens_gen    = direct_result.total_tokens
            message_id    = str(_uuid.uuid4())
            cached        = False

        except Exception as exc:
            logger.error("Direct Ollama call failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI service unavailable: {exc}",
            )

    else:
        # ── Standard RAG pipeline path ─────────────────────────────────
        try:
            rag_response = await rag_service.ask(
                query=effective_query,
                project_id=str(session.project_id),
                prompt_type=prompt_type,
                model=body.model,
                top_k=body.top_k,
                language_filter=body.language_filter,
                conversation_history=conversation_history or None,
                use_cache=body.use_cache,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

        # Unpack RAG response
        if isinstance(rag_response, dict):
            answer         = rag_response.get("answer", "")
            sources        = rag_response.get("sources", [])
            timing         = rag_response.get("timing", {})
            model_used     = rag_response.get("model", settings.OLLAMA_DEFAULT_MODEL)
            context_tokens = rag_response.get("context_tokens", 0)
            tokens_gen     = rag_response.get("tokens_generated", 0)
            message_id     = rag_response.get("message_id", "cached")
            cached         = True
        else:
            answer         = rag_response.answer
            sources        = [c.to_dict() for c in rag_response.retrieval.chunks]
            timing         = {
                "total_ms":     round(rag_response.total_elapsed_ms, 2),
                "llm_ms":       round(rag_response.llm_elapsed_ms, 2),
                "retrieval_ms": round(rag_response.retrieval.retrieval_time_ms, 2),
            }
            model_used     = rag_response.model
            context_tokens = rag_response.context.estimated_tokens
            tokens_gen     = rag_response.tokens_generated
            message_id     = rag_response.message_id
            cached         = False

    # Handle cached response (returned as dict) vs live RAGResponse object
    # Persist both sides of the conversation
    await chat_repo.add_message(
        session_id=session_id, role="user",
        content=body.query, prompt_type=body.prompt_type,
    )
    await chat_repo.add_message(
        session_id=session_id, role="assistant",
        content=answer, prompt_type=body.prompt_type,
        model_used=model_used, sources=sources,
        retrieval_time_ms=timing.get("retrieval_ms"),
        llm_time_ms=timing.get("llm_ms"),
        total_time_ms=timing.get("total_ms"),
        tokens_generated=tokens_gen,
        context_tokens=context_tokens,
        cached=cached,
    )

    return AskResponse(
        message_id=message_id,
        answer=answer,
        sources=sources,
        cached=cached,
        timing=timing,
        llm_model=model_used,
        context_tokens=context_tokens,
        tokens_generated=tokens_gen,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session",
    description="Soft-deletes a chat session. Messages are retained in DB but session is marked inactive.",
    # NOTE: No response_model — 204 responses must have no body (FastAPI strict mode)
)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    """Soft-delete a chat session and mark it inactive."""
    chat_repo = ChatRepository(db)
    deleted = await chat_repo.delete_session(
        session_id=session_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found or access denied",
        )
    # Return empty 204 response — FastAPI requires Response object for 204
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────
# WebSocket Streaming Endpoint
# ─────────────────────────────────────────────────────────────────

@router.websocket("/sessions/{session_id}/stream")
async def stream_chat(
    websocket: WebSocket,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    WebSocket endpoint for real-time streaming chat responses.

    Protocol:
      Client sends:  {"query": str, "project_id": str, "prompt_type": str, "top_k": int}
      Server sends:  {"type": "metadata", "message_id": str, "sources": [...]}
                     {"type": "token",    "token": str, "message_id": str}   (many)
                     {"type": "done",     "full_text": str, "message_id": str}
                     {"type": "error",    "message": str}
    """
    await websocket.accept()
    logger.info("WebSocket connected: session=%s", session_id)

    chat_repo = ChatRepository(db)

    try:
        while True:
            # Receive message from client
            try:
                raw = await websocket.receive_text()
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue
            except WebSocketDisconnect:
                break

            query = data.get("query", "").strip()
            if not query:
                await websocket.send_json({"type": "error", "message": "Query cannot be empty"})
                continue

            project_id  = str(data.get("project_id", ""))
            prompt_type = _parse_prompt_type(data.get("prompt_type", "code_qa"))
            model       = data.get("model", settings.OLLAMA_DEFAULT_MODEL)
            top_k       = min(int(data.get("top_k", 8)), 20)

            if not project_id:
                await websocket.send_json({"type": "error", "message": "project_id is required"})
                continue

            # Load conversation history for context
            history = await chat_repo.get_conversation_history(
                session_id=session_id, last_n=6
            )

            # Build RAG service
            try:
                rag_service = _build_rag_service()
            except HTTPException as exc:
                await websocket.send_json({"type": "error", "message": exc.detail})
                continue

            # Setup streaming pipeline
            try:
                message_id, metadata, token_stream = await rag_service.stream_ask(
                    query=query,
                    project_id=project_id,
                    prompt_type=prompt_type,
                    model=model,
                    top_k=top_k,
                    conversation_history=history or None,
                )
            except Exception as exc:
                logger.error("RAG stream setup failed: %s", exc)
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            # Send metadata (sources, message_id) before streaming starts
            await websocket.send_json({
                "type": "metadata",
                "message_id": message_id,
                **metadata,
            })

            # Persist user message
            await chat_repo.add_message(
                session_id=session_id,
                role="user",
                content=query,
                prompt_type=prompt_type.value if hasattr(prompt_type, "value") else str(prompt_type),
            )

            # Stream tokens to client
            tokens: list[str] = []
            model_used = model
            try:
                async for chunk in token_stream:
                    if chunk.is_final:
                        model_used = chunk.model
                        break
                    tokens.append(chunk.token)
                    await websocket.send_json({
                        "type": "token",
                        "token": chunk.token,
                        "message_id": message_id,
                    })

                full_text = "".join(tokens)

                # Signal completion
                await websocket.send_json({
                    "type": "done",
                    "full_text": full_text,
                    "message_id": message_id,
                })

                # Persist assistant response
                await chat_repo.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_text,
                    model_used=model_used,
                    sources=metadata.get("sources", []),
                    context_tokens=metadata.get("context_tokens", 0),
                )

            except Exception as exc:
                logger.error("Token streaming error: %s", exc)
                await websocket.send_json({"type": "error", "message": str(exc)})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception as exc:
        logger.error("WebSocket fatal error: %s", exc, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        logger.info("WebSocket closed: session=%s", session_id)