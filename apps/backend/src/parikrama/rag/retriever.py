"""
Hybrid retriever combining semantic (pgvector) and keyword (BM25/trigram) search.

Uses Reciprocal Rank Fusion (RRF) to merge results from both methods.
RRF is model-free — it needs no training, just rank positions.

Pipeline:
1. User query → embed with MiniLM → cosine similarity search via pgvector
2. User query → PostgreSQL trigram similarity (BM25-like keyword match)
3. Merge both ranked lists using RRF: score = Σ weight / (k + rank)
4. Return merged results sorted by fused score

Why RRF over simple score averaging:
- Score scales differ wildly between cosine similarity and trigram percentage
- RRF only uses rank positions, making it scale-invariant
- Standard k=60 prevents top-ranked items from having outsized influence
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from parikrama.rag.embeddings import embedding_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# RRF constant — 60 is the standard value from the original RRF paper.
# Lower k = top-ranked items dominate. Higher k = flatter distribution.
RRF_K: int = 60


class HybridRetriever:
    """Retrieve relevant document chunks using semantic + keyword search combined via RRF."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(
        self,
        query: str,
        top_k: int = 10,
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4,
        filter_metadata: dict | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """Run hybrid search and return RRF-merged results.

        Args:
            query: User search string.
            top_k: Number of results to return after fusion.
            semantic_weight: RRF contribution weight for semantic results (0-1).
            keyword_weight: RRF contribution weight for keyword results (0-1).
            filter_metadata: Optional JSONB filter, e.g. {"destination": "Manali"}.
            user_id: If set, restricts results to documents owned by this user.

        Returns:
            List of result dicts with ``chunk_id``, ``content``, ``metadata``,
            ``document_id``, ``score``, ``rrf_score``.
        """
        # Fetch more candidates than needed — we'll merge and trim.
        candidate_k = top_k * 3

        # Run both searches; they're independent so we could run concurrently,
        # but pgvector embed_text blocks anyway so sequential is simpler here.
        semantic_results = await self._semantic_search(query, candidate_k, filter_metadata, user_id)
        keyword_results = await self._keyword_search(query, candidate_k, filter_metadata, user_id)

        # Merge with Reciprocal Rank Fusion.
        merged = self._reciprocal_rank_fusion(
            semantic_results, keyword_results, semantic_weight, keyword_weight
        )

        logger.info(
            "hybrid_search_completed",
            query_snippet=query[:60],
            semantic_hits=len(semantic_results),
            keyword_hits=len(keyword_results),
            merged_top=len(merged[:top_k]),
        )

        return merged[:top_k]

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _semantic_search(
        self,
        query: str,
        top_k: int,
        filter_metadata: dict | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """Vector cosine similarity search using pgvector.

        Uses the HNSW index on ``document_chunks.embedding`` for fast ANN search.
        ``<=>`` is the cosine distance operator; 1 - distance = similarity.
        """
        query_embedding = embedding_service.embed_text(query)
        # Build vector literal directly in SQL — asyncpg uses positional ($1) params
        # and does NOT support named-param type casts like ':embedding::vector'.
        # The embedding list contains only floats, so string interpolation is safe.
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        # Build dynamic WHERE clauses using named params (strings/ints are fine)
        conditions: list[str] = []
        params: dict = {"limit": top_k}

        if user_id:
            conditions.append("d.user_id = :user_id::uuid")
            params["user_id"] = user_id

        if filter_metadata:
            for i, (key, value) in enumerate(filter_metadata.items()):
                param_name = f"meta_{i}"
                conditions.append(f"dc.metadata->>'{key}' = :{param_name}")
                params[param_name] = value

        where_clause = ""
        if conditions:
            where_clause = "AND " + " AND ".join(conditions)

        # Embed vector literal directly in SQL (safe — numeric floats only)
        sql = text(
            f"""
            SELECT
                dc.id,
                dc.content,
                dc.metadata,
                dc.document_id,
                1 - (dc.embedding <=> '{embedding_str}'::vector) AS similarity
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE 1=1 {where_clause}
            ORDER BY dc.embedding <=> '{embedding_str}'::vector
            LIMIT :limit
            """
        )

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "chunk_id": str(row.id),
                "content": row.content,
                "metadata": row.metadata or {},
                "document_id": str(row.document_id),
                "score": float(row.similarity),
                "source": "semantic",
            }
            for row in rows
        ]

    async def _keyword_search(
        self,
        query: str,
        top_k: int,
        filter_metadata: dict | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """BM25-style keyword search using PostgreSQL trigram similarity.

        Requires ``pg_trgm`` extension and a GIN index on ``document_chunks.content``.
        The ``%`` operator requires trigram similarity > ``pg_trgm.similarity_threshold``
        (default 0.3).

        Falls back to ILIKE if no trigram matches (very short or rare terms).
        """
        conditions: list[str] = []
        params: dict = {"query": query, "limit": top_k}

        if user_id:
            conditions.append("d.user_id = :user_id::uuid")
            params["user_id"] = user_id

        if filter_metadata:
            for i, (key, value) in enumerate(filter_metadata.items()):
                param_name = f"meta_{i}"
                conditions.append(f"dc.metadata->>'{key}' = :{param_name}")
                params[param_name] = value

        extra_where = ""
        if conditions:
            extra_where = "AND " + " AND ".join(conditions)

        # Try trigram similarity first; fall back to ILIKE for short queries.
        if len(query) >= 3:
            sql = text(
                f"""
                SELECT
                    dc.id,
                    dc.content,
                    dc.metadata,
                    dc.document_id,
                    similarity(dc.content, :query) AS sim_score
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE dc.content % :query {extra_where}
                ORDER BY sim_score DESC
                LIMIT :limit
                """
            )
        else:
            sql = text(
                f"""
                SELECT
                    dc.id,
                    dc.content,
                    dc.metadata,
                    dc.document_id,
                    0.3::float AS sim_score
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE dc.content ILIKE :query_like {extra_where}
                LIMIT :limit
                """
            )
            params["query_like"] = f"%{query}%"

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "chunk_id": str(row.id),
                "content": row.content,
                "metadata": row.metadata or {},
                "document_id": str(row.document_id),
                "score": float(row.sim_score),
                "source": "keyword",
            }
            for row in rows
        ]

    def _reciprocal_rank_fusion(
        self,
        semantic: list[dict],
        keyword: list[dict],
        semantic_weight: float,
        keyword_weight: float,
    ) -> list[dict]:
        """Merge two ranked lists using Reciprocal Rank Fusion.

        Formula: RRF_score(d) = Σ  weight_i / (k + rank_i(d))
        where k=60 dampens the advantage of being ranked first.

        Args:
            semantic: Semantically ranked results (higher score = more relevant).
            keyword: Keyword-ranked results (higher score = more relevant).
            semantic_weight: Multiplier applied to semantic RRF scores (0-1).
            keyword_weight: Multiplier applied to keyword RRF scores (0-1).

        Returns:
            Merged list sorted by ``rrf_score`` descending, with all chunk data preserved.
        """
        scores: dict[str, float] = {}
        chunk_data: dict[str, dict] = {}

        for rank, item in enumerate(semantic):
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + semantic_weight / (RRF_K + rank + 1)
            chunk_data[cid] = item

        for rank, item in enumerate(keyword):
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + keyword_weight / (RRF_K + rank + 1)
            if cid not in chunk_data:
                chunk_data[cid] = item

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [{**chunk_data[cid], "rrf_score": round(scores[cid], 6)} for cid in sorted_ids]
