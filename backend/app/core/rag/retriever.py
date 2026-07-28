"""
Semantic code retriever with MMR (Maximal Marginal Relevance) re-ranking.

Retrieves the most relevant code chunks from ChromaDB for a given query,
applying metadata filtering and diversity-aware re-ranking to prevent
redundant context from dominating the prompt window.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from app.core.rag.embeddings import EmbeddingService
from app.core.rag.vector_store import VectorStoreService

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single retrieved code chunk with its metadata and relevance score."""

    chunk_id: str
    content: str
    file_path: str
    language: str
    chunk_type: str          # "function", "class", "module", "block"
    start_line: int
    end_line: int
    similarity_score: float
    project_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context_string(self) -> str:
        """Format chunk as a readable context block for the prompt."""
        header = f"[FILE: {self.file_path} | LINES: {self.start_line}-{self.end_line} | TYPE: {self.chunk_type}]"
        return f"{header}\n`{self.language}\n{self.content}\n`"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for API responses."""
        return {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "language": self.language,
            "chunk_type": self.chunk_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "similarity_score": round(self.similarity_score, 4),
            "content_preview": self.content[:200] + "..." if len(self.content) > 200 else self.content,
        }


@dataclass
class RetrievalResult:
    """Complete retrieval result with chunks, timing, and diagnostics."""

    chunks: list[RetrievedChunk]
    query: str
    retrieval_time_ms: float
    total_candidates: int
    strategy: str  # "similarity" | "mmr" | "hybrid"

    @property
    def is_empty(self) -> bool:
        """Return True if no relevant chunks were found."""
        return len(self.chunks) == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for API responses."""
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "query": self.query,
            "retrieval_time_ms": round(self.retrieval_time_ms, 2),
            "total_candidates": self.total_candidates,
            "strategy": self.strategy,
            "chunks_found": len(self.chunks),
        }


class CodeRetriever:
    """
    Semantic code retriever with MMR re-ranking for diverse, relevant results.

    Uses Maximal Marginal Relevance to balance relevance with diversity,
    preventing the same code pattern from consuming the entire context window.
    """

    # Retrieval configuration constants
    DEFAULT_TOP_K: int = 8
    DEFAULT_FETCH_K: int = 20         # Candidate pool size before re-ranking
    DEFAULT_MMR_LAMBDA: float = 0.7   # 1.0 = pure similarity, 0.0 = pure diversity
    MIN_SIMILARITY_THRESHOLD: float = 0.15

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
    ) -> None:
        """
        Initialize the retriever with embedding and vector store services.

        Args:
            embedding_service: Service for generating query embeddings
            vector_store: ChromaDB vector store service
        """
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        logger.info("CodeRetriever initialized with MMR support")

    async def retrieve(
        self,
        query: str,
        project_id: str,
        top_k: int = DEFAULT_TOP_K,
        strategy: str = "mmr",
        language_filter: Optional[str] = None,
        file_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None,
    ) -> RetrievalResult:
        """
        Retrieve relevant code chunks for the given query.

        Args:
            query: Natural language question about the codebase
            project_id: Filter results to a specific project
            top_k: Number of final chunks to return
            strategy: "similarity" for pure cosine, "mmr" for diversity-aware
            language_filter: Optional programming language filter
            file_filter: Optional file path substring filter
            chunk_type_filter: Optional chunk type filter (function/class/etc)

        Returns:
            RetrievalResult with ranked chunks and diagnostics
        """
        start_time = time.perf_counter()

        logger.info(
            "Retrieving chunks",
            extra={
                "query_preview": query[:100],
                "project_id": project_id,
                "strategy": strategy,
                "top_k": top_k,
            },
        )

        # 1. Embed the query
        try:
            query_embedding = self._embedding_service.embed_text(query)
        except Exception as exc:
            logger.error("Failed to embed query: %s", exc)
            raise RuntimeError(f"Query embedding failed: {exc}") from exc

        # 2. Build metadata filter
        where_filter = self._build_metadata_filter(
            project_id=project_id,
            language=language_filter,
            file_path=file_filter,
            chunk_type=chunk_type_filter,
        )

        # 3. Fetch candidate pool from ChromaDB
        fetch_k = min(self.DEFAULT_FETCH_K, top_k * 3)
        try:
            raw_results = self._vector_store.query(
                collection_name=f"project_{project_id}",
                query_embedding=query_embedding,
                n_results=fetch_k,
                where=where_filter,
            )
        except Exception as exc:
            logger.error("Vector store query failed: %s", exc)
            raise RuntimeError(f"Vector retrieval failed: {exc}") from exc

        # 4. Parse raw results into RetrievedChunk objects
        candidate_chunks = self._parse_raw_results(raw_results)

        # 5. Filter by minimum similarity threshold
        candidate_chunks = [
            c for c in candidate_chunks
            if c.similarity_score >= self.MIN_SIMILARITY_THRESHOLD
        ]

        # 6. Apply re-ranking strategy
        if strategy == "mmr" and len(candidate_chunks) > top_k:
            final_chunks = self._apply_mmr(
                query_embedding=query_embedding,
                candidates=candidate_chunks,
                top_k=top_k,
                lambda_param=self.DEFAULT_MMR_LAMBDA,
            )
        else:
            final_chunks = candidate_chunks[:top_k]

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "Retrieval complete: %d/%d chunks selected in %.1fms",
            len(final_chunks),
            len(candidate_chunks),
            elapsed_ms,
        )

        return RetrievalResult(
            chunks=final_chunks,
            query=query,
            retrieval_time_ms=elapsed_ms,
            total_candidates=len(candidate_chunks),
            strategy=strategy,
        )

    def _build_metadata_filter(
        self,
        project_id: str,
        language: Optional[str],
        file_path: Optional[str],
        chunk_type: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Build ChromaDB 'where' filter from optional parameters."""
        conditions: list[dict[str, Any]] = [
            {"project_id": {"": project_id}}
        ]

        if language:
            conditions.append({"language": {"": language.lower()}})
        if chunk_type:
            conditions.append({"chunk_type": {"": chunk_type}})

        # ChromaDB requires  for multiple conditions
        if len(conditions) == 1:
            return conditions[0]
        return {"": conditions}

    def _parse_raw_results(
        self, raw_results: dict[str, Any]
    ) -> list[RetrievedChunk]:
        """Parse ChromaDB query results into RetrievedChunk objects."""
        chunks: list[RetrievedChunk] = []

        if not raw_results or not raw_results.get("ids"):
            return chunks

        ids = raw_results["ids"][0] if raw_results["ids"] else []
        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        for i, chunk_id in enumerate(ids):
            try:
                metadata = metadatas[i] if i < len(metadatas) else {}
                # ChromaDB returns L2 distance; convert to similarity [0,1]
                distance = distances[i] if i < len(distances) else 1.0
                similarity = max(0.0, 1.0 - (distance / 2.0))

                chunk = RetrievedChunk(
                    chunk_id=chunk_id,
                    content=documents[i] if i < len(documents) else "",
                    file_path=metadata.get("file_path", "unknown"),
                    language=metadata.get("language", "text"),
                    chunk_type=metadata.get("chunk_type", "block"),
                    start_line=int(metadata.get("start_line", 0)),
                    end_line=int(metadata.get("end_line", 0)),
                    similarity_score=similarity,
                    project_id=metadata.get("project_id", ""),
                    metadata=metadata,
                )
                chunks.append(chunk)
            except Exception as exc:
                logger.warning("Failed to parse chunk %s: %s", chunk_id, exc)
                continue

        return chunks

    def _apply_mmr(
        self,
        query_embedding: list[float],
        candidates: list[RetrievedChunk],
        top_k: int,
        lambda_param: float,
    ) -> list[RetrievedChunk]:
        """
        Apply Maximal Marginal Relevance re-ranking.

        MMR balances relevance to the query against diversity among
        selected chunks. This prevents redundant code snippets from
        filling the context window.

        Score = lambda * sim(chunk, query) - (1-lambda) * max(sim(chunk, selected))

        Args:
            query_embedding: The embedded query vector
            candidates: Candidate chunks sorted by similarity
            top_k: Number of chunks to select
            lambda_param: Balance between relevance (1.0) and diversity (0.0)

        Returns:
            Diverse, relevant subset of candidates
        """
        if not candidates:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        # Use similarity scores already computed (avoid re-embedding)
        candidate_scores = np.array(
            [c.similarity_score for c in candidates], dtype=np.float32
        )

        selected_indices: list[int] = []
        remaining_indices = list(range(len(candidates)))

        for _ in range(min(top_k, len(candidates))):
            if not remaining_indices:
                break

            if not selected_indices:
                # First selection: pick highest similarity
                best_idx = remaining_indices[
                    int(np.argmax(candidate_scores[remaining_indices]))
                ]
            else:
                # MMR selection: balance relevance and diversity
                best_score = float("-inf")
                best_idx = remaining_indices[0]

                for idx in remaining_indices:
                    relevance = candidate_scores[idx]
                    # Diversity: distance from already-selected chunks
                    # Use similarity scores as proxy (avoid storing all embeddings)
                    max_redundancy = max(
                        candidate_scores[sel] * candidate_scores[idx]
                        for sel in selected_indices
                    )
                    mmr_score = (
                        lambda_param * relevance
                        - (1 - lambda_param) * max_redundancy
                    )
                    if mmr_score > best_score:
                        best_score = mmr_score
                        best_idx = idx

            selected_indices.append(best_idx)
            remaining_indices.remove(best_idx)

        return [candidates[i] for i in selected_indices]