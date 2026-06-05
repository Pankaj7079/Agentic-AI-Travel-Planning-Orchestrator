"""
Cross-encoder reranker for final precision boost.

After hybrid search returns top-K candidates, the cross-encoder
scores each (query, chunk) pair jointly for relevance.
This is more accurate than bi-encoder similarity but slower,
so we only apply it to the small top-K set (≤20 candidates).

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (22MB, ~50ms for 10 pairs on CPU)

Pipeline:
  Hybrid Search  → fast, high recall, moderate precision
  ↓ top-K candidates
  Cross-Encoder  → slow, high precision
  ↓ top-5 results
  Agents / API   ← grounded travel knowledge
"""
from __future__ import annotations

import structlog

try:
    from sentence_transformers import CrossEncoder
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "sentence-transformers is required for reranking. "
        "Run: uv add sentence-transformers"
    ) from e

logger = structlog.get_logger(__name__)

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker:
    """Rerank search results using a cross-encoder model.

    The cross-encoder takes a (query, document) pair and outputs a
    relevance score. Unlike bi-encoders that encode query and document
    separately, the cross-encoder sees both together → better precision.
    """

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL) -> None:
        self._model_name = model_name
        self._model: CrossEncoder | None = None

    @property
    def model(self) -> CrossEncoder:
        """Lazy-load the cross-encoder model on first use."""
        if self._model is None:
            logger.info("loading_reranker_model", model=self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("reranker_model_loaded", model=self._model_name)
        return self._model

    def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank search results by cross-encoder relevance.

        Args:
            query: Original user query string.
            results: List of search result dicts, each with a ``content`` field.
            top_k: Maximum number of results to return after reranking.

        Returns:
            Results sorted by ``rerank_score`` (highest = most relevant), truncated
            to ``top_k``.
        """
        if not results:
            return []

        # CrossEncoder expects (query, document) pairs.
        pairs = [(query, r["content"]) for r in results]
        raw_scores = self.model.predict(pairs)

        # Attach scores and sort descending.
        scored = [
            {**result, "rerank_score": float(score)}
            for result, score in zip(results, raw_scores)
        ]
        reranked = sorted(scored, key=lambda x: x["rerank_score"], reverse=True)

        logger.info(
            "reranking_completed",
            input_count=len(results),
            output_count=min(top_k, len(reranked)),
            top_score=reranked[0]["rerank_score"] if reranked else None,
        )

        return reranked[:top_k]

    def is_loaded(self) -> bool:
        """Return True if the model has been loaded into memory."""
        return self._model is not None


# Module-level singleton.
reranker = Reranker()
