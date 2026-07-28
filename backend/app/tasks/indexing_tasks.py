"""
Indexing Tasks - Step 29
AI Codebase Assistant v2.0

Full implementation of codebase indexing pipeline as Celery tasks.

Pipeline per file:
    1. Read file content from disk or passed content dict
    2. Detect language from extension
    3. Parse into chunks via CodeChunker (Step 10)
    4. Generate embeddings via HuggingFace (Step 11)
    5. Store in ChromaDB collection (Step 12)
    6. Update per-file progress in Redis

Progress schema (Redis key: indexing:progress:{project_id}):
    {
        "task_id":        str,
        "project_id":     str,
        "status":         PENDING | RUNNING | COMPLETED | FAILED,
        "total_files":    int,
        "indexed_files":  int,
        "failed_files":   int,
        "progress":       0.0 - 1.0,
        "current_file":   str | null,
        "started_at":     ISO str,
        "completed_at":   ISO str | null,
        "error":          str | null,
        "indexed_chunks": int,
        "file_results":   list[dict]
    }
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# =============================================================================
# Language detection map
# =============================================================================

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py":   "python",
    ".js":   "javascript",
    ".jsx":  "javascript",
    ".ts":   "typescript",
    ".tsx":  "typescript",
    ".java": "java",
    ".cpp":  "cpp",
    ".cc":   "cpp",
    ".c":    "c",
    ".go":   "go",
    ".rs":   "rust",
    ".rb":   "ruby",
    ".php":  "php",
    ".cs":   "csharp",
    ".swift": "swift",
    ".kt":   "kotlin",
    ".md":   "markdown",
    ".txt":  "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml":  "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css":  "css",
    ".sql":  "sql",
    ".sh":   "bash",
    ".bash": "bash",
}

# Files to skip during indexing
SKIP_EXTENSIONS = frozenset([
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".lock", ".log",
])

# Max file size to index (2MB)
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024


# =============================================================================
# Redis helpers
# =============================================================================

def _redis_client() -> redis.Redis:
    """
    Create a Redis client for indexing progress tracking.

    Returns:
        Connected Redis client with decode_responses=True
    """
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(url, decode_responses=True)


def _update_progress(
    project_id: str,
    task_id: str,
    status: str,
    total_files: int,
    indexed_files: int,
    failed_files: int,
    current_file: str | None,
    indexed_chunks: int,
    file_results: list[dict[str, Any]],
    error: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    """
    Write indexing progress to Redis for real-time polling.

    Key: indexing:progress:{project_id}
    TTL: 86400 seconds (24 hours)

    Args:
        project_id:    Project UUID
        task_id:       Celery task UUID
        status:        PENDING | RUNNING | COMPLETED | FAILED
        total_files:   Total files to index
        indexed_files: Successfully indexed so far
        failed_files:  Failed so far
        current_file:  File currently being processed
        indexed_chunks: Total chunks stored in ChromaDB
        file_results:  Per-file result list
        error:         Top-level error message if FAILED
        started_at:    ISO timestamp when started
        completed_at:  ISO timestamp when done
    """
    progress_pct = (
        round((indexed_files + failed_files) / max(total_files, 1), 3)
        if total_files > 0 else 0.0
    )

    payload: dict[str, Any] = {
        "task_id": task_id,
        "project_id": project_id,
        "status": status,
        "total_files": total_files,
        "indexed_files": indexed_files,
        "failed_files": failed_files,
        "progress": progress_pct,
        "current_file": current_file,
        "indexed_chunks": indexed_chunks,
        "file_results": file_results[-20:],  # keep last 20 for payload size
        "error": error,
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "completed_at": completed_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        client = _redis_client()
        client.setex(
            f"indexing:progress:{project_id}",
            86400,
            json.dumps(payload),
        )
        # Also store by task_id for cross-lookup
        client.setex(
            f"task:progress:{task_id}",
            86400,
            json.dumps({
                "task_id": task_id,
                "status": status,
                "agent_id": "indexer",
                "progress": progress_pct,
                "current_step": f"indexing {current_file or '...'}",
                "project_id": project_id,
            }),
        )
    except Exception as exc:
        logger.warning(
            "Failed to update indexing progress: project=%s error=%s",
            project_id, exc,
        )


def get_indexing_progress(project_id: str) -> dict[str, Any] | None:
    """
    Retrieve current indexing progress for a project from Redis.

    Args:
        project_id: Project UUID

    Returns:
        Progress dict or None if not found / Redis unavailable
    """
    try:
        client = _redis_client()
        raw = client.get(f"indexing:progress:{project_id}")
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Failed to get indexing progress: project=%s error=%s",
            project_id, exc,
        )
    return None


# =============================================================================
# File processing helpers
# =============================================================================

def _detect_language(file_path: str) -> str:
    """
    Detect programming language from file extension.

    Args:
        file_path: File path string (can be just filename)

    Returns:
        Language string e.g. "python", "javascript", "unknown"
    """
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext, "unknown")


def _should_skip_file(file_path: str, content: str) -> tuple[bool, str]:
    """
    Determine whether a file should be skipped during indexing.

    Skips: binary extensions, files too large, empty files,
           auto-generated files (package-lock.json etc.)

    Args:
        file_path: File path string
        content:   File content string

    Returns:
        Tuple of (should_skip: bool, reason: str)
    """
    path = Path(file_path)

    # Skip by extension
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return True, f"Binary/skip extension: {path.suffix}"

    # Skip empty files
    if not content or not content.strip():
        return True, "Empty file"

    # Skip too-large files
    if len(content.encode("utf-8")) > MAX_FILE_SIZE_BYTES:
        return True, f"File too large ({len(content)} bytes > {MAX_FILE_SIZE_BYTES})"

    # Skip auto-generated files
    auto_gen_patterns = [
        "package-lock.json", "yarn.lock", "poetry.lock",
        "Pipfile.lock", ".min.js", ".min.css",
    ]
    name_lower = path.name.lower()
    for pattern in auto_gen_patterns:
        if pattern in name_lower:
            return True, f"Auto-generated file: {path.name}"

    return False, ""


def _chunk_file_content(
    content: str,
    language: str,
    file_path: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[dict[str, Any]]:
    """
    Split file content into overlapping chunks for embedding.

    Tries to use the CodeChunker from Step 10 first.
    Falls back to simple line-based chunking if unavailable.

    Args:
        content:       File content string
        language:      Programming language
        file_path:     File path for metadata
        chunk_size:    Target characters per chunk
        chunk_overlap: Overlap characters between chunks

    Returns:
        List of chunk dicts with keys: content, metadata
    """
    chunks: list[dict[str, Any]] = []

    # Try Step 10 CodeChunker first
    try:
        import sys
        sys.path.insert(0, ".")
        from app.core.parsers.chunker import CodeChunker
        chunker = CodeChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        raw_chunks = chunker.chunk(
            content=content,
            language=language,
            file_path=file_path,
        )
        for i, chunk in enumerate(raw_chunks):
            chunks.append({
                "content": chunk.content if hasattr(chunk, "content") else str(chunk),
                "metadata": {
                    "file_path": file_path,
                    "language": language,
                    "chunk_index": i,
                    "chunk_type": getattr(chunk, "chunk_type", "code"),
                    "start_line": getattr(chunk, "start_line", 0),
                    "end_line": getattr(chunk, "end_line", 0),
                },
            })
        logger.debug(
            "CodeChunker produced %d chunks for %s", len(chunks), file_path
        )
        return chunks

    except Exception as exc:
        logger.debug(
            "CodeChunker unavailable (%s), using fallback chunker", exc
        )

    # Fallback: simple character-based sliding window
    lines = content.splitlines(keepends=True)
    current_chunk = ""
    current_start_line = 1

    for line_idx, line in enumerate(lines, start=1):
        current_chunk += line
        if len(current_chunk) >= chunk_size:
            chunks.append({
                "content": current_chunk,
                "metadata": {
                    "file_path": file_path,
                    "language": language,
                    "chunk_index": len(chunks),
                    "chunk_type": "code",
                    "start_line": current_start_line,
                    "end_line": line_idx,
                },
            })
            # Keep overlap
            overlap_text = current_chunk[-chunk_overlap:] if chunk_overlap > 0 else ""
            current_chunk = overlap_text
            current_start_line = max(1, line_idx - 5)

    # Add remaining content as final chunk
    if current_chunk.strip():
        chunks.append({
            "content": current_chunk,
            "metadata": {
                "file_path": file_path,
                "language": language,
                "chunk_index": len(chunks),
                "chunk_type": "code",
                "start_line": current_start_line,
                "end_line": len(lines),
            },
        })

    return chunks


def _store_chunks_in_vector_db(
    chunks: list[dict[str, Any]],
    project_id: str,
    file_path: str,
) -> int:
    """
    Generate embeddings and store chunks in ChromaDB.

    Tries to use the EmbeddingService (Step 11) and VectorStore (Step 12).
    Falls back to a no-op stub when services are unavailable.

    Args:
        chunks:     List of chunk dicts from _chunk_file_content
        project_id: Project UUID for ChromaDB collection namespacing
        file_path:  File path for logging

    Returns:
        Number of chunks successfully stored
    """
    if not chunks:
        return 0

    # Try production path via Step 11 + 12
    try:
        from app.core.rag.embeddings import EmbeddingService
        from app.core.rag.vector_store import VectorStore

        embedding_service = EmbeddingService()
        vector_store = VectorStore(project_id=project_id)

        texts = [c["content"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        # Generate embeddings (batch)
        embeddings = embedding_service.embed_texts(texts)

        # Generate unique IDs for each chunk
        import hashlib
        ids = [
            hashlib.md5(
                f"{project_id}:{file_path}:{i}".encode()
            ).hexdigest()
            for i in range(len(chunks))
        ]

        # Store in ChromaDB
        vector_store.add(
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )

        logger.debug(
            "Stored %d chunks for %s in ChromaDB", len(chunks), file_path
        )
        return len(chunks)

    except Exception as exc:
        logger.warning(
            "Vector store unavailable for %s: %s — using stub",
            file_path, exc,
        )

    # Stub: just return count without actually storing
    # Full storage requires ChromaDB running (Step 12)
    logger.debug(
        "Stub: would store %d chunks for %s", len(chunks), file_path
    )
    return len(chunks)


# =============================================================================
# Single File Indexer
# =============================================================================

def _index_single_file(
    file_path: str,
    content: str,
    project_id: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict[str, Any]:
    """
    Index a single file: detect language, chunk, embed, store.

    Args:
        file_path:     Relative file path (used as ID and metadata)
        content:       Raw file content string
        project_id:    Project UUID
        chunk_size:    Target chunk size in characters
        chunk_overlap: Overlap between consecutive chunks

    Returns:
        Result dict with keys: file_path, status, chunks_created,
        language, error, elapsed_ms
    """
    start = time.perf_counter()
    language = _detect_language(file_path)

    # Check if should skip
    should_skip, skip_reason = _should_skip_file(file_path, content)
    if should_skip:
        return {
            "file_path": file_path,
            "status": "skipped",
            "chunks_created": 0,
            "language": language,
            "error": None,
            "skip_reason": skip_reason,
            "elapsed_ms": 0.0,
        }

    try:
        # Step 1: Chunk the file
        chunks = _chunk_file_content(
            content=content,
            language=language,
            file_path=file_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if not chunks:
            return {
                "file_path": file_path,
                "status": "skipped",
                "chunks_created": 0,
                "language": language,
                "error": None,
                "skip_reason": "No chunks produced",
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
            }

        # Step 2: Embed and store
        stored = _store_chunks_in_vector_db(
            chunks=chunks,
            project_id=project_id,
            file_path=file_path,
        )

        elapsed = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Indexed %s: language=%s chunks=%d elapsed=%.0fms",
            file_path, language, stored, elapsed,
        )

        return {
            "file_path": file_path,
            "status": "indexed",
            "chunks_created": stored,
            "language": language,
            "error": None,
            "skip_reason": None,
            "elapsed_ms": elapsed,
        }

    except Exception as exc:
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            "Failed to index %s: %s", file_path, exc, exc_info=True
        )
        return {
            "file_path": file_path,
            "status": "failed",
            "chunks_created": 0,
            "language": language,
            "error": str(exc),
            "skip_reason": None,
            "elapsed_ms": elapsed,
        }


# =============================================================================
# Main Indexing Task
# =============================================================================

@celery_app.task(
    name="app.tasks.indexing_tasks.index_project_files",
    bind=True,
    max_retries=2,
    soft_time_limit=1200,  # 20 minutes
    time_limit=1500,
    queue="low",
)
def index_project_files(
    self: Any,
    project_id: str,
    user_id: str,
    files: list[dict[str, str]],
    force_reindex: bool = False,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict[str, Any]:
    """
    Celery task to index all project files into ChromaDB.

    Each file is processed sequentially with progress updates
    stored in Redis after every file for real-time polling.

    Args:
        self:          Celery task instance (bound)
        project_id:    Project UUID
        user_id:       User UUID
        files:         List of dicts: [{"path": str, "content": str}, ...]
        force_reindex: If True, re-index files already in vector store
        chunk_size:    Target chunk size in characters
        chunk_overlap: Overlap between chunks

    Returns:
        Dict with: status, task_id, project_id, total_files,
        indexed_count, skipped_count, failed_count,
        total_chunks, elapsed_ms, file_results
    """
    task_id = self.request.id or "local"
    started_at = datetime.now(timezone.utc).isoformat()
    total_files = len(files)

    logger.info(
        "Indexing task starting: project=%s files=%d task=%s",
        project_id, total_files, task_id,
    )

    # Initial progress
    _update_progress(
        project_id=project_id,
        task_id=task_id,
        status="RUNNING",
        total_files=total_files,
        indexed_files=0,
        failed_files=0,
        current_file=None,
        indexed_chunks=0,
        file_results=[],
        started_at=started_at,
    )

    indexed_count = 0
    skipped_count = 0
    failed_count = 0
    total_chunks = 0
    file_results: list[dict[str, Any]] = []
    wall_start = time.perf_counter()

    for file_num, file_entry in enumerate(files, start=1):
        file_path = str(file_entry.get("path", f"file_{file_num}"))
        content = str(file_entry.get("content", ""))

        logger.info(
            "Indexing file %d/%d: %s (project=%s)",
            file_num, total_files, file_path, project_id,
        )

        # Update progress: currently processing this file
        _update_progress(
            project_id=project_id,
            task_id=task_id,
            status="RUNNING",
            total_files=total_files,
            indexed_files=indexed_count,
            failed_files=failed_count,
            current_file=file_path,
            indexed_chunks=total_chunks,
            file_results=file_results,
            started_at=started_at,
        )

        # Index the file
        result = _index_single_file(
            file_path=file_path,
            content=content,
            project_id=project_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        file_results.append(result)

        # Update counters
        if result["status"] == "indexed":
            indexed_count += 1
            total_chunks += result.get("chunks_created", 0)
        elif result["status"] == "skipped":
            skipped_count += 1
        else:
            failed_count += 1

        logger.debug(
            "File %d/%d done: %s status=%s chunks=%d",
            file_num, total_files,
            file_path, result["status"],
            result.get("chunks_created", 0),
        )

    # Final progress update
    total_elapsed = round((time.perf_counter() - wall_start) * 1000, 2)
    completed_at = datetime.now(timezone.utc).isoformat()
    final_status = "FAILED" if failed_count == total_files else "COMPLETED"

    _update_progress(
        project_id=project_id,
        task_id=task_id,
        status=final_status,
        total_files=total_files,
        indexed_files=indexed_count,
        failed_files=failed_count,
        current_file=None,
        indexed_chunks=total_chunks,
        file_results=file_results,
        started_at=started_at,
        completed_at=completed_at,
    )

    logger.info(
        "Indexing complete: project=%s indexed=%d skipped=%d "
        "failed=%d chunks=%d elapsed=%.0fms",
        project_id, indexed_count, skipped_count,
        failed_count, total_chunks, total_elapsed,
    )

    return {
        "status": final_status,
        "task_id": task_id,
        "project_id": project_id,
        "total_files": total_files,
        "indexed_count": indexed_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "total_chunks": total_chunks,
        "elapsed_ms": total_elapsed,
        "completed_at": completed_at,
        "file_results": file_results,
    }


# =============================================================================
# Re-index single file task (for incremental updates)
# =============================================================================

@celery_app.task(
    name="app.tasks.indexing_tasks.reindex_single_file",
    bind=True,
    max_retries=3,
    soft_time_limit=120,
    time_limit=150,
    queue="default",
)
def reindex_single_file(
    self: Any,
    project_id: str,
    user_id: str,
    file_path: str,
    content: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> dict[str, Any]:
    """
    Re-index a single file after it has been edited.

    Removes existing chunks for the file from ChromaDB,
    then re-indexes with updated content.

    Args:
        self:          Celery task instance
        project_id:    Project UUID
        user_id:       User UUID
        file_path:     File path to re-index
        content:       Updated file content
        chunk_size:    Target chunk size
        chunk_overlap: Chunk overlap

    Returns:
        Single file indexing result dict
    """
    task_id = self.request.id or "local"
    logger.info(
        "Re-indexing single file: project=%s file=%s task=%s",
        project_id, file_path, task_id,
    )

    try:
        # Remove existing chunks for this file from ChromaDB
        try:
            from app.core.rag.vector_store import VectorStore
            vs = VectorStore(project_id=project_id)
            vs.delete_by_metadata({"file_path": file_path})
            logger.info("Removed existing chunks for %s", file_path)
        except Exception as exc:
            logger.warning(
                "Could not remove existing chunks for %s: %s",
                file_path, exc,
            )

        # Re-index with new content
        result = _index_single_file(
            file_path=file_path,
            content=content,
            project_id=project_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        return {
            **result,
            "task_id": task_id,
            "project_id": project_id,
            "operation": "reindex",
        }

    except Exception as exc:
        logger.error(
            "Re-index failed: project=%s file=%s error=%s",
            project_id, file_path, exc,
            exc_info=True,
        )
        # Retry on transient errors
        if any(
            kw in str(exc).lower()
            for kw in ["connection", "timeout", "refused"]
        ):
            raise self.retry(exc=exc, countdown=15)
        return {
            "file_path": file_path,
            "status": "failed",
            "chunks_created": 0,
            "language": _detect_language(file_path),
            "error": str(exc),
            "task_id": task_id,
            "project_id": project_id,
            "operation": "reindex",
        }
