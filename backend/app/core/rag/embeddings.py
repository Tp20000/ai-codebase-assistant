"""
Embeddings Service — HuggingFace sentence-transformers integration.

Model: all-MiniLM-L6-v2
  - 384 dimensions
  - 22M parameters (fast inference even on CPU)
  - Trained on 1B+ sentence pairs
  - Best balance of speed vs quality for code search

Architecture:
  - Singleton model loading (load once on first call, reuse)
  - Batch embedding for efficiency (process multiple texts at once)
  - Configurable model via settings (swap to code-specific models later)
  - Graceful fallback if model unavailable
"""

import logging
import time
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Model singleton
# ─────────────────────────────────────────────

_model = None
_model_name: str = ""

# Default embedding model
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def _get_model():
    """
    Load or return cached sentence-transformer model.
    Downloads on first call (~80MB), then cached locally.
    Thread-safe: Python GIL ensures single initialization.
    """
    global _model, _model_name

    if _model is not None:
        return _model

    model_name = getattr(settings, "EMBEDDING_MODEL", DEFAULT_MODEL)

    try:
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model: {model_name}...")
        start = time.time()

        _model = SentenceTransformer(model_name)
        _model_name = model_name

        elapsed = round(time.time() - start, 2)
        logger.info(
            f"Embedding model loaded: {model_name} "
            f"(dim={_model.get_sentence_embedding_dimension()}, "
            f"took {elapsed}s)"
        )
        return _model

    except ImportError:
        logger.error(
            "sentence-transformers not installed. "
            "Run: pip install sentence-transformers"
        )
        return None
    except Exception as exc:
        logger.error(f"Failed to load embedding model: {exc}", exc_info=True)
        return None


# ─────────────────────────────────────────────
# Embedding Service
# ─────────────────────────────────────────────

class EmbeddingService:
    """
    Service for generating text embeddings using sentence-transformers.

    Usage:
        svc = EmbeddingService()
        vectors = svc.embed_texts(["def hello(): pass", "class Foo: ..."])
        # vectors shape: (2, 384)

    Features:
        - Lazy model loading (first call downloads/loads model)
        - Batch processing (efficient GPU/CPU utilization)
        - Configurable batch size for memory management
        - Returns Python lists (JSON-serializable for ChromaDB)
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        """
        Initialize embedding service.

        Args:
            model_name: Override default model. If None, uses settings or default.
        """
        self._custom_model_name = model_name
        self._custom_model = None

    def _get_active_model(self):
        """Get the active model — custom or global singleton."""
        if self._custom_model_name:
            if self._custom_model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    self._custom_model = SentenceTransformer(self._custom_model_name)
                except Exception as exc:
                    logger.error(f"Custom model load failed: {exc}")
                    return _get_model()
            return self._custom_model
        return _get_model()

    def embed_text(self, text: str) -> Optional[list[float]]:
        """
        Generate embedding for a single text string.

        Args:
            text: Text to embed (code snippet, query, etc.)

        Returns:
            List of floats (embedding vector) or None if model unavailable
        """
        if not text or not text.strip():
            logger.warning("Empty text passed to embed_text")
            return None

        model = self._get_active_model()
        if model is None:
            return None

        try:
            vector = model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return vector.tolist()
        except Exception as exc:
            logger.error(f"Embedding failed for text ({len(text)} chars): {exc}")
            return None

    def embed_texts(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> Optional[list[list[float]]]:
        """
        Generate embeddings for multiple texts in batch.
        More efficient than calling embed_text() in a loop.

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts to process per batch

        Returns:
            List of embedding vectors, or None if model unavailable
        """
        if not texts:
            return []

        # Filter empty texts but track indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            return [[] for _ in texts]

        model = self._get_active_model()
        if model is None:
            return None

        try:
            start = time.time()

            vectors = model.encode(
                valid_texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )

            elapsed = round(time.time() - start, 3)
            logger.info(
                f"Batch embedded {len(valid_texts)} texts "
                f"in {elapsed}s ({len(valid_texts)/max(elapsed,0.001):.0f} texts/s)"
            )

            # Reconstruct full result list with empty vectors for filtered texts
            result: list[list[float]] = [[] for _ in texts]
            for idx, vec in zip(valid_indices, vectors):
                result[idx] = vec.tolist()

            return result

        except Exception as exc:
            logger.error(f"Batch embedding failed ({len(valid_texts)} texts): {exc}")
            return None

    def embed_chunks(
        self,
        chunks: list[dict],
        content_key: str = "content",
        batch_size: int = 32,
    ) -> list[dict]:
        """
        Embed a list of chunk dictionaries in place.
        Adds 'embedding' key to each chunk dict.

        Args:
            chunks: List of chunk dicts (from CodeChunker)
            content_key: Key in chunk dict containing text to embed
            batch_size: Batch size for embedding

        Returns:
            Same chunks list with 'embedding' key added to each
        """
        if not chunks:
            return chunks

        texts = [c.get(content_key, "") for c in chunks]
        vectors = self.embed_texts(texts, batch_size=batch_size)

        if vectors is None:
            logger.warning("Embedding failed — chunks returned without vectors")
            for chunk in chunks:
                chunk["embedding"] = []
            return chunks

        for chunk, vector in zip(chunks, vectors):
            chunk["embedding"] = vector

        embedded_count = sum(1 for v in vectors if v)
        logger.info(
            f"Embedded {embedded_count}/{len(chunks)} chunks "
            f"(dim={len(vectors[0]) if vectors and vectors[0] else 0})"
        )
        return chunks

    def get_model_info(self) -> dict:
        """
        Return information about the active embedding model.

        Returns:
            Dict with model name, dimensions, and availability status
        """
        model = self._get_active_model()
        if model is None:
            return {
                "available": False,
                "model_name": self._custom_model_name or DEFAULT_MODEL,
                "dimensions": EMBEDDING_DIM,
                "error": "Model not loaded",
            }

        try:
            dim = model.get_sentence_embedding_dimension()
        except Exception:
            dim = EMBEDDING_DIM

        return {
            "available": True,
            "model_name": self._custom_model_name or _model_name or DEFAULT_MODEL,
            "dimensions": dim,
            "max_seq_length": getattr(model, "max_seq_length", 256),
        }

    @staticmethod
    def get_embedding_dimension() -> int:
        """Return the embedding dimension for the default model."""
        return EMBEDDING_DIM