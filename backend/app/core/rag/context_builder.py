"""
Context window builder for RAG prompts.

Assembles retrieved code chunks into a structured context block
that fits within the LLM's token budget, prioritizing highest-scored
chunks and maintaining readability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.core.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class BuiltContext:
    """Assembled context ready for prompt injection."""

    context_text: str
    chunks_included: int
    chunks_truncated: int
    estimated_tokens: int
    file_paths: list[str]

    def is_empty(self) -> bool:
        """Return True if no chunks were included in context."""
        return self.chunks_included == 0


class ContextBuilder:
    """
    Builds a structured context window from retrieved code chunks.

    Manages token budget to stay within the LLM's context limit,
    deduplicates overlapping chunks, and formats code with clear
    source attribution headers.
    """

    # Conservative token estimation: ~4 characters per token
    CHARS_PER_TOKEN: int = 4
    DEFAULT_MAX_TOKENS: int = 3000  # Reserve space for query + answer
    CONTEXT_HEADER = "=== RELEVANT CODE CONTEXT ==="
    CONTEXT_FOOTER = "=== END OF CONTEXT ==="

    def __init__(self, max_context_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        """
        Initialize the context builder.

        Args:
            max_context_tokens: Maximum tokens to use for context
        """
        self._max_tokens = max_context_tokens
        self._max_chars = max_context_tokens * self.CHARS_PER_TOKEN
        logger.debug(
            "ContextBuilder initialized: max_tokens=%d", max_context_tokens
        )

    def build(
        self,
        chunks: list[RetrievedChunk],
        include_file_summary: bool = True,
        deduplicate: bool = True,
    ) -> BuiltContext:
        """
        Build a context block from retrieved chunks.

        Args:
            chunks: Retrieved code chunks, pre-ranked by relevance
            include_file_summary: Whether to include a file list header
            deduplicate: Whether to remove overlapping line ranges

        Returns:
            BuiltContext with the assembled prompt-ready context
        """
        if not chunks:
            return BuiltContext(
                context_text="",
                chunks_included=0,
                chunks_truncated=0,
                estimated_tokens=0,
                file_paths=[],
            )

        # Deduplicate overlapping chunks from the same file
        if deduplicate:
            chunks = self._deduplicate_chunks(chunks)

        sections: list[str] = []
        total_chars = 0
        included_count = 0
        truncated_count = 0
        file_paths: list[str] = []

        if include_file_summary:
            unique_files = list({c.file_path for c in chunks})
            file_list = "\n".join(f"  • {f}" for f in sorted(unique_files))
            summary = f"Files referenced:\n{file_list}\n"
            sections.append(summary)
            total_chars += len(summary)

        for chunk in chunks:
            chunk_text = chunk.to_context_string()
            chunk_chars = len(chunk_text)

            if total_chars + chunk_chars > self._max_chars:
                # Try to include a truncated version if it's the only chunk
                if not sections or included_count == 0:
                    remaining = self._max_chars - total_chars - 100
                    if remaining > 200:
                        truncated_content = chunk.content[:remaining] + "\n... [truncated]"
                        truncated_chunk = RetrievedChunk(
                            chunk_id=chunk.chunk_id,
                            content=truncated_content,
                            file_path=chunk.file_path,
                            language=chunk.language,
                            chunk_type=chunk.chunk_type,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            similarity_score=chunk.similarity_score,
                            project_id=chunk.project_id,
                        )
                        sections.append(truncated_chunk.to_context_string())
                        included_count += 1
                truncated_count += 1
                continue

            sections.append(chunk_text)
            total_chars += chunk_chars
            included_count += 1
            if chunk.file_path not in file_paths:
                file_paths.append(chunk.file_path)

        context_body = "\n\n".join(sections)
        estimated_tokens = len(context_body) // self.CHARS_PER_TOKEN

        logger.debug(
            "Context built: %d chunks included, %d truncated, ~%d tokens",
            included_count,
            truncated_count,
            estimated_tokens,
        )

        return BuiltContext(
            context_text=context_body,
            chunks_included=included_count,
            chunks_truncated=truncated_count,
            estimated_tokens=estimated_tokens,
            file_paths=file_paths,
        )

    def _deduplicate_chunks(
        self, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """
        Remove chunks that overlap significantly with higher-scored chunks.

        For chunks from the same file, if their line ranges overlap by more
        than 50%, keep only the higher-scored one.
        """
        if len(chunks) <= 1:
            return chunks

        deduplicated: list[RetrievedChunk] = []

        for candidate in chunks:
            is_redundant = False
            for selected in deduplicated:
                if selected.file_path != candidate.file_path:
                    continue
                # Calculate overlap ratio
                overlap_start = max(selected.start_line, candidate.start_line)
                overlap_end = min(selected.end_line, candidate.end_line)
                if overlap_end > overlap_start:
                    candidate_span = max(
                        1, candidate.end_line - candidate.start_line
                    )
                    overlap_ratio = (overlap_end - overlap_start) / candidate_span
                    if overlap_ratio > 0.5:
                        is_redundant = True
                        break
            if not is_redundant:
                deduplicated.append(candidate)

        logger.debug(
            "Deduplication: %d → %d chunks", len(chunks), len(deduplicated)
        )
        return deduplicated

    def format_no_context_message(self, query: str) -> str:
        """Generate a fallback message when no relevant context is found."""
        return (
            f"No relevant code context was found for this query. "
            f"The codebase may not contain code related to: '{query}'. "
            f"Please ensure the project has been indexed before asking questions."
        )
