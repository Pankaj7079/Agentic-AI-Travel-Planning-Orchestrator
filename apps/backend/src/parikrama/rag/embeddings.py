"""
Embedding model wrapper with caching.

Loads the sentence-transformers model once at startup (lazy) and reuses it.
Caches query embeddings in Redis to avoid redundant computation.

Model: all-MiniLM-L6-v2 (384 dimensions, 80MB, ~5ms per query on CPU)
"""

from __future__ import annotations

import hashlib

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Try sentence_transformers; fail fast with a clear message if missing.
try:
    from sentence_transformers import SentenceTransformer
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "sentence-transformers is required for the RAG pipeline. Run: uv add sentence-transformers"
    ) from e

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSION = 384


class EmbeddingService:
    """Generate and cache text embeddings using a local sentence-transformer model.

    Attributes:
        model_name: HuggingFace model identifier.
        dimension: Output vector size (384 for all-MiniLM-L6-v2).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the model on first use — saves ~2s on cold startup."""
        if self._model is None:
            logger.info("loading_embedding_model", model=self.model_name)
            self._model = SentenceTransformer(self.model_name)
            logger.info(
                "embedding_model_loaded",
                model=self.model_name,
                dimension=self.dimension,
            )
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """Generate a normalized embedding for a single text string.

        Args:
            text: Input text to embed (any length; long texts are truncated by model).

        Returns:
            List of floats with length == self.dimension.
        """
        embedding: np.ndarray = self.model.encode(  # type: ignore[assignment]
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[list[float]]:
        """Generate embeddings for a batch of texts — much faster than one-by-one.

        Args:
            texts: List of strings to embed.
            batch_size: How many to encode at once (controls GPU/CPU memory).

        Returns:
            List of float lists, one per input text.
        """
        if not texts:
            return []

        embeddings: np.ndarray = self.model.encode(  # type: ignore[assignment]
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    @staticmethod
    def query_hash(text: str) -> str:
        """Generate a deterministic SHA-256 hash for caching query embeddings.

        Args:
            text: Query text.

        Returns:
            64-character hex string.
        """
        return hashlib.sha256(text.strip().lower().encode()).hexdigest()


# Module-level singleton — expensive to initialize, so we create it once.
# Import this everywhere: `from parikrama.rag.embeddings import embedding_service`
embedding_service = EmbeddingService()
