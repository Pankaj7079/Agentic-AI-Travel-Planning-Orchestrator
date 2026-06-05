"""
RAG service — high-level knowledge retrieval pipeline for agents and API endpoints.

Combines HybridRetriever (pgvector + BM25) + cross-encoder Reranker
into a single search interface. Agents call this before generating responses
to get grounded, factual travel knowledge.

Example usage by the Research Agent:
    rag = RAGService(db)
    results = await rag.search(SearchRequest(
        query="best budget hotels in Manali for 2 people",
        filter_metadata={"destination": "Manali"},
        top_k=5,
    ))
    context = "\\n\\n".join(r.content for r in results)
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.rag.reranker import reranker
from parikrama.rag.retriever import HybridRetriever
from parikrama.schemas.rag import SearchRequest, SearchResponse, SearchResult

logger = structlog.get_logger(__name__)


class RAGService:
    """High-level RAG search interface used by agents and the search API."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.retriever = HybridRetriever(db)

    async def search(
        self,
        request: SearchRequest,
        user_id: str | None = None,
    ) -> SearchResponse:
        """Full RAG search pipeline: retrieve → (optional) rerank → format.

        Args:
            request: ``SearchRequest`` with query, weights, and filters.
            user_id: If ``request.restrict_to_my_documents`` is True, this
                     is used to filter results to the user's own documents.

        Returns:
            ``SearchResponse`` with ranked chunks and pipeline metadata.
        """
        # Step 1: Hybrid retrieval — fetch more candidates than final top_k
        # so that the reranker has room to reorder.
        candidate_k = request.top_k * 3  # e.g. top_k=5 → fetch 15 candidates

        filter_uid = user_id if request.restrict_to_my_documents else None

        candidates = await self.retriever.search(
            query=request.query,
            top_k=candidate_k,
            semantic_weight=request.semantic_weight,
            keyword_weight=request.keyword_weight,
            filter_metadata=request.filter_metadata,
            user_id=filter_uid,
        )

        if not candidates:
            logger.info("rag_search_no_results", query=request.query[:60])
            return SearchResponse(
                query=request.query,
                results=[],
                total_found=0,
                reranked=False,
                semantic_weight=request.semantic_weight,
                keyword_weight=request.keyword_weight,
            )

        # Step 2: Cross-encoder reranking for precision (optional)
        was_reranked = False
        if request.use_reranker and len(candidates) > 1:
            ranked = reranker.rerank(
                query=request.query,
                results=candidates,
                top_k=request.top_k,
            )
            was_reranked = True
        else:
            ranked = candidates[: request.top_k]

        # Step 3: Format into response model
        results = [
            SearchResult(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                content=r["content"],
                metadata=r.get("metadata", {}),
                score=r.get("rerank_score", r.get("rrf_score", r.get("score", 0.0))),
                source=r.get("source", "hybrid"),
            )
            for r in ranked
        ]

        logger.info(
            "rag_search_completed",
            query_snippet=request.query[:60],
            candidates=len(candidates),
            returned=len(results),
            reranked=was_reranked,
            top_score=results[0].score if results else 0,
        )

        return SearchResponse(
            query=request.query,
            results=results,
            total_found=len(results),
            reranked=was_reranked,
            semantic_weight=request.semantic_weight,
            keyword_weight=request.keyword_weight,
        )

    async def get_context_for_query(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict | None = None,
        user_id: str | None = None,
    ) -> str:
        """Convenience method for agents — returns a single formatted context string.

        Calls ``search()`` and concatenates the top chunk contents into a
        newline-separated string ready to inject into an LLM prompt.

        Args:
            query: Natural language query.
            top_k: Number of chunks to include in context.
            filter_metadata: Optional JSONB filter.
            user_id: Optional user restriction.

        Returns:
            Formatted context string, or empty string if no results found.
        """
        request = SearchRequest(
            query=query,
            top_k=top_k,
            filter_metadata=filter_metadata,
            restrict_to_my_documents=user_id is not None,
        )
        response = await self.search(request, user_id=user_id)

        if not response.results:
            return ""

        # Format: numbered chunks with source metadata
        parts: list[str] = []
        for i, result in enumerate(response.results, start=1):
            dest = result.metadata.get("destination", "Unknown")
            page = result.metadata.get("page", "")
            source_info = f"[Source {i}: {dest}" + (f", p.{page}" if page else "") + "]"
            parts.append(f"{source_info}\n{result.content}")

        return "\n\n---\n\n".join(parts)
