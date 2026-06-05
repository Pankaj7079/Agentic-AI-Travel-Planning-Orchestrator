"""
RAG search API routes.

Endpoints:
    POST /api/v1/rag/search            Full hybrid search (semantic + BM25 + reranker)
    POST /api/v1/rag/search/semantic   Semantic-only search
    POST /api/v1/rag/search/keyword    Keyword-only search
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Depends

from parikrama.core.security import get_current_user_id
from parikrama.db.session import get_db
from parikrama.schemas.rag import SearchRequest, SearchResponse
from parikrama.services.rag_service import RAGService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG Search"])


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Hybrid semantic + keyword RAG search",
)
async def hybrid_search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> SearchResponse:
    """Search the knowledge base using hybrid semantic + BM25 retrieval.

    The pipeline:
    1. Embed query with all-MiniLM-L6-v2
    2. Cosine similarity search in pgvector (semantic)
    3. PostgreSQL trigram match (BM25-like keyword)
    4. Merge with Reciprocal Rank Fusion
    5. Cross-encoder reranking (if ``use_reranker=True``)

    Returns top-k grounded chunks from uploaded travel documents.
    """
    rag = RAGService(db)
    return await rag.search(request, user_id=user_id)


@router.post(
    "/search/semantic",
    response_model=SearchResponse,
    summary="Semantic-only vector search",
)
async def semantic_search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> SearchResponse:
    """Pure semantic (vector) search only — no BM25, no reranking.

    Useful for conceptual queries where exact keyword matching is not important.
    """
    semantic_request = request.model_copy(
        update={"semantic_weight": 1.0, "keyword_weight": 0.0, "use_reranker": False}
    )
    rag = RAGService(db)
    return await rag.search(semantic_request, user_id=user_id)


@router.post(
    "/search/keyword",
    response_model=SearchResponse,
    summary="Keyword-only BM25 search",
)
async def keyword_search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> SearchResponse:
    """Keyword-only (BM25/trigram) search — no embeddings, no reranking.

    Useful for exact name/term lookups like ``"IRCTC"`` or ``"Volvo sleeper"``.
    """
    keyword_request = request.model_copy(
        update={"semantic_weight": 0.0, "keyword_weight": 1.0, "use_reranker": False}
    )
    rag = RAGService(db)
    return await rag.search(keyword_request, user_id=user_id)
