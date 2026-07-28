"""
High-level RAG service.

Wires all RAG components together with dependency injection,
Redis caching, and error handling. This is the single entry point
that API routes and WebSocket handlers use.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional, AsyncGenerator

import redis.asyncio as aioredis

from app.core.rag.retriever import CodeRetriever
from app.core.rag.context_builder import ContextBuilder
from app.core.rag.pipeline import RAGPipeline, RAGRequest, RAGResponse
from app.core.llm.prompt_templates import PromptTemplateEngine, PromptType
from app.core.llm.streaming import OllamaStreamingClient, StreamChunk
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Cache TTL: 1 hour for identical queries
CACHE_TTL_SECONDS = 3600


def _make_cache_key(request: RAGRequest) -> str:
    """
    Generate a deterministic cache key for a RAG request.

    Two requests are cache-equivalent if they have the same:
    query, project_id, prompt_type, model, and top_k.
    """
    key_data = (
        f"{request.query}::{request.project_id}::{request.prompt_type}"
        f"::{request.model}::{request.top_k}"
    )
    return f"rag:cache:{hashlib.sha256(key_data.encode()).hexdigest()}"


class RAGService:
    """
    Production RAG service with caching and error handling.

    Provides a clean API for both REST and WebSocket handlers.
    Handles cache hits, graceful degradation, and detailed logging.
    """

    def __init__(
        self,
        retriever: CodeRetriever,
        streaming_client: OllamaStreamingClient,
        redis_client: Optional[aioredis.Redis] = None,
    ) -> None:
        """
        Initialize the RAG service.

        Args:
            retriever: Configured CodeRetriever instance
            streaming_client: Configured OllamaStreamingClient
            redis_client: Optional Redis client for response caching
        """
        self._pipeline = RAGPipeline(
            retriever=retriever,
            context_builder=ContextBuilder(max_context_tokens=3000),
            prompt_engine=PromptTemplateEngine(),
            streaming_client=streaming_client,
            default_model=settings.OLLAMA_DEFAULT_MODEL,
        )
        self._redis = redis_client
        logger.info("RAGService initialized")

    async def ask(
        self,
        query: str,
        project_id: str,
        prompt_type: PromptType = PromptType.CODE_QA,
        model: Optional[str] = None,
        top_k: int = 8,
        language_filter: Optional[str] = None,
        file_filter: Optional[str] = None,
        conversation_history: Optional[str] = None,
        use_cache: bool = True,
    ) -> RAGResponse:
        """
        Execute a non-streaming RAG query with optional caching.

        Args:
            query: User's natural language question
            project_id: Project to query against
            prompt_type: Type of AI analysis
            model: LLM model override
            top_k: Number of chunks to retrieve
            language_filter: Filter by programming language
            file_filter: Filter by file path substring
            conversation_history: Prior conversation for threading
            use_cache: Whether to use Redis cache

        Returns:
            Complete RAGResponse

        Raises:
            ValueError: If query is empty
            RuntimeError: If retrieval or LLM fails
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        request = RAGRequest(
            query=query.strip(),
            project_id=project_id,
            prompt_type=prompt_type,
            model=model or settings.OLLAMA_DEFAULT_MODEL,
            top_k=top_k,
            language_filter=language_filter,
            file_filter=file_filter,
            conversation_history=conversation_history,
        )

        # Check Redis cache first
        if use_cache and self._redis:
            cache_key = _make_cache_key(request)
            try:
                cached = await self._redis.get(cache_key)
                if cached:
                    cached_data = json.loads(cached)
                    logger.info("Cache HIT for query: %s...", query[:50])
                    # Rebuild a minimal RAGResponse from cached data
                    # (Full deserialization would require more complex logic)
                    # For now, return the cached response dict as-is
                    # The API endpoint will handle both cached and live responses
                    cached_data["cached"] = True
                    return cached_data  # type: ignore[return-value]
            except Exception as exc:
                logger.warning("Cache read failed (continuing without cache): %s", exc)

        # Execute RAG pipeline
        try:
            response = await self._pipeline.query(request)
        except ConnectionError as exc:
            logger.error("Ollama connection failed: %s", exc)
            raise RuntimeError(
                "AI service is unavailable. Please ensure Ollama is running."
            ) from exc
        except Exception as exc:
            logger.error("RAG pipeline failed: %s", exc, exc_info=True)
            raise RuntimeError(f"Failed to process query: {exc}") from exc

        # Cache the successful response
        if use_cache and self._redis:
            cache_key = _make_cache_key(request)
            try:
                response_dict = response.to_dict()
                await self._redis.setex(
                    cache_key,
                    CACHE_TTL_SECONDS,
                    json.dumps(response_dict),
                )
                logger.debug("Response cached: %s", cache_key[:40])
            except Exception as exc:
                logger.warning("Cache write failed: %s", exc)

        return response

    async def stream_ask(
        self,
        query: str,
        project_id: str,
        prompt_type: PromptType = PromptType.CODE_QA,
        model: Optional[str] = None,
        top_k: int = 8,
        language_filter: Optional[str] = None,
        conversation_history: Optional[str] = None,
    ) -> tuple[str, dict, AsyncGenerator[StreamChunk, None]]:
        """
        Execute a streaming RAG query for WebSocket delivery.

        Args:
            query: User's question
            project_id: Project to query
            prompt_type: Type of AI task
            model: Model override
            top_k: Chunks to retrieve
            language_filter: Language filter
            conversation_history: Prior conversation

        Returns:
            Tuple of (message_id, metadata_dict, token_stream_generator)
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        request = RAGRequest(
            query=query.strip(),
            project_id=project_id,
            prompt_type=prompt_type,
            model=model or settings.OLLAMA_DEFAULT_MODEL,
            top_k=top_k,
            language_filter=language_filter,
            conversation_history=conversation_history,
        )

        message_id, retrieval, context, token_stream = (
            await self._pipeline.stream_query(request)
        )

        metadata = {
            "message_id": message_id,
            "retrieval": retrieval.to_dict(),
            "context_tokens": context.estimated_tokens,
            "sources": [c.to_dict() for c in retrieval.chunks],
        }

        return message_id, metadata, token_stream
