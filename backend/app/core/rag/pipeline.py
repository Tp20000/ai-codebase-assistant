"""
Complete RAG (Retrieval-Augmented Generation) pipeline.

Orchestrates the full flow: query → embed → retrieve → build context →
augment prompt → stream answer → return structured result.

This is the central intelligence module of the entire system.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional, AsyncGenerator

from app.core.rag.retriever import CodeRetriever, RetrievalResult
from app.core.rag.context_builder import ContextBuilder, BuiltContext
from app.core.llm.prompt_templates import PromptTemplateEngine, PromptType
from app.core.llm.streaming import OllamaStreamingClient, StreamChunk, StreamingResult

logger = logging.getLogger(__name__)


@dataclass
class RAGRequest:
    """Input to the RAG pipeline."""

    query: str
    project_id: str
    prompt_type: PromptType = PromptType.CODE_QA
    model: str = "llama3.2"
    top_k: int = 8
    language_filter: Optional[str] = None
    file_filter: Optional[str] = None
    conversation_history: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 2048
    session_id: Optional[str] = None


@dataclass
class RAGResponse:
    """Complete output from the RAG pipeline."""

    answer: str
    message_id: str
    retrieval: RetrievalResult
    context: BuiltContext
    model: str
    total_elapsed_ms: float
    llm_elapsed_ms: float
    tokens_generated: int
    cached: bool = False

    def to_dict(self) -> dict:
        """Serialize to dictionary for API responses."""
        return {
            "answer": self.answer,
            "message_id": self.message_id,
            "model": self.model,
            "cached": self.cached,
            "timing": {
                "total_ms": round(self.total_elapsed_ms, 2),
                "llm_ms": round(self.llm_elapsed_ms, 2),
                "retrieval_ms": round(self.retrieval.retrieval_time_ms, 2),
            },
            "retrieval": self.retrieval.to_dict(),
            "context_tokens": self.context.estimated_tokens,
            "tokens_generated": self.tokens_generated,
            "sources": [c.to_dict() for c in self.retrieval.chunks],
        }


class RAGPipeline:
    """
    Production RAG pipeline for codebase question answering.

    Wires together retrieval, context building, prompt engineering,
    and LLM generation into a single coherent flow.

    Features:
    - Semantic similarity + MMR retrieval
    - Token-budget-aware context assembly
    - Task-specific prompt templates
    - Real-time streaming via async generators
    - Redis caching for repeated queries (injected via service)
    """

    def __init__(
        self,
        retriever: CodeRetriever,
        context_builder: ContextBuilder,
        prompt_engine: PromptTemplateEngine,
        streaming_client: OllamaStreamingClient,
        default_model: str = "llama3.2",
    ) -> None:
        """
        Initialize the RAG pipeline.

        Args:
            retriever: Semantic code retriever
            context_builder: Context window assembler
            prompt_engine: Prompt template factory
            streaming_client: Ollama streaming client
            default_model: Default LLM model to use
        """
        self._retriever = retriever
        self._context_builder = context_builder
        self._prompt_engine = prompt_engine
        self._streaming_client = streaming_client
        self._default_model = default_model
        logger.info("RAGPipeline initialized with model: %s", default_model)

    async def query(self, request: RAGRequest) -> RAGResponse:
        """
        Execute a complete non-streaming RAG query.

        Performs full retrieve → augment → generate cycle and
        returns the complete response with metadata.

        Args:
            request: Complete RAG request with query and config

        Returns:
            RAGResponse with answer and full diagnostic metadata
        """
        start_time = time.perf_counter()
        message_id = str(uuid.uuid4())
        model = request.model or self._default_model

        logger.info(
            "RAG query started",
            extra={
                "message_id": message_id,
                "project_id": request.project_id,
                "prompt_type": request.prompt_type,
                "model": model,
            },
        )

        # Step 1: Retrieve relevant chunks
        retrieval_result = await self._retriever.retrieve(
            query=request.query,
            project_id=request.project_id,
            top_k=request.top_k,
            strategy="mmr",
            language_filter=request.language_filter,
            file_filter=request.file_filter,
        )

        # Step 2: Build context window
        context = self._context_builder.build(
            chunks=retrieval_result.chunks,
            deduplicate=True,
        )

        # Step 3: Build prompt messages
        messages = self._prompt_engine.build_messages(
            query=request.query,
            context=context.context_text,
            prompt_type=request.prompt_type,
            conversation_history=request.conversation_history,
        )

        logger.debug(
            "Prompt built: %d chunks, ~%d context tokens",
            context.chunks_included,
            context.estimated_tokens,
        )

        # Step 4: Generate answer (non-streaming, collects all tokens)
        llm_start = time.perf_counter()
        streaming_result: StreamingResult = await self._streaming_client.collect_stream(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        llm_elapsed_ms = (time.perf_counter() - llm_start) * 1000
        total_elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "RAG query complete: %.1fms total (retrieval: %.1fms, llm: %.1fms), %d tokens",
            total_elapsed_ms,
            retrieval_result.retrieval_time_ms,
            llm_elapsed_ms,
            streaming_result.total_tokens,
        )

        return RAGResponse(
            answer=streaming_result.full_text,
            message_id=message_id,
            retrieval=retrieval_result,
            context=context,
            model=model,
            total_elapsed_ms=total_elapsed_ms,
            llm_elapsed_ms=llm_elapsed_ms,
            tokens_generated=streaming_result.total_tokens,
        )

    async def stream_query(
        self, request: RAGRequest
    ) -> tuple[str, RetrievalResult, BuiltContext, AsyncGenerator[StreamChunk, None]]:
        """
        Execute a streaming RAG query.

        Returns retrieval metadata immediately, then yields tokens
        as the LLM generates them. Used for WebSocket streaming.

        Args:
            request: Complete RAG request

        Returns:
            Tuple of (message_id, retrieval_result, context, token_stream)
        """
        message_id = str(uuid.uuid4())
        model = request.model or self._default_model

        logger.info(
            "RAG streaming query: %s (project=%s)",
            message_id,
            request.project_id,
        )

        # Step 1: Retrieve (blocking - we need this before streaming)
        retrieval_result = await self._retriever.retrieve(
            query=request.query,
            project_id=request.project_id,
            top_k=request.top_k,
            strategy="mmr",
            language_filter=request.language_filter,
            file_filter=request.file_filter,
        )

        # Step 2: Build context
        context = self._context_builder.build(
            chunks=retrieval_result.chunks,
            deduplicate=True,
        )

        # Step 3: Build messages
        messages = self._prompt_engine.build_messages(
            query=request.query,
            context=context.context_text,
            prompt_type=request.prompt_type,
            conversation_history=request.conversation_history,
        )

        # Step 4: Return stream generator (caller controls consumption)
        token_stream = self._streaming_client.stream_chat(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return message_id, retrieval_result, context, token_stream
