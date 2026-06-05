"""
RAG pipeline schemas — request/response models for document management and search.

All schemas use Pydantic v2 with strict validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ── Enums ──────────────────────────────────────────────────────────────────────


class DocumentStatus(StrEnum):
    """Processing status lifecycle of an uploaded document."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    CHUNKED = "chunked"
    EMBEDDED = "embedded"
    FAILED = "failed"


# ── Document Schemas ───────────────────────────────────────────────────────────


class DocumentUploadResponse(BaseModel):
    """Response after a document is uploaded and processing is queued."""

    id: uuid.UUID
    filename: str
    status: DocumentStatus
    file_size_bytes: int
    destination: str | None = None
    message: str = "Document uploaded. Processing started in background."


class DocumentResponse(BaseModel):
    """Full document details including processing state."""

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    content_type: str
    status: DocumentStatus
    file_size_bytes: int
    chunk_count: int
    destination: str | None = None
    description: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


# ── RAG Search Schemas ─────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """Request to perform a hybrid RAG search."""

    query: str = Field(
        min_length=3,
        max_length=500,
        description="Natural language search query, e.g. 'hotels in Manali under ₹2000'.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of results to return after reranking.",
    )
    semantic_weight: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Weight given to semantic (vector) search in RRF fusion.",
    )
    keyword_weight: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Weight given to keyword (BM25/trigram) search in RRF fusion.",
    )
    use_reranker: bool = Field(
        default=True,
        description="If True, apply cross-encoder reranking for higher precision.",
    )
    filter_metadata: dict | None = Field(
        default=None,
        description="Optional JSONB filter, e.g. {'destination': 'Manali'}.",
    )
    restrict_to_my_documents: bool = Field(
        default=False,
        description="If True, only search documents uploaded by the current user.",
    )


class SearchResult(BaseModel):
    """A single retrieved and ranked chunk."""

    chunk_id: str
    document_id: str
    content: str = Field(description="The raw text of this chunk.")
    metadata: dict = Field(default_factory=dict)
    score: float = Field(description="Final relevance score (higher = better).")
    source: str = Field(
        default="hybrid",
        description="Which retrieval method surfaced this result: semantic/keyword/hybrid.",
    )


class SearchResponse(BaseModel):
    """Search pipeline response with metadata."""

    query: str
    results: list[SearchResult]
    total_found: int
    reranked: bool
    semantic_weight: float
    keyword_weight: float
