# Phase 2: RAG Pipeline + Knowledge Base

## Overview

Phase 2 builds the **intelligence layer** — the RAG (Retrieval-Augmented Generation) system that gives our agents real, grounded knowledge about travel destinations. Without RAG, agents hallucinate hotel names, invent attractions, and fabricate reviews. With RAG, they retrieve actual travel guides, real reviews, and verified destination data before generating responses.

### What This Phase Delivers
- Upload travel guides, reviews, and destination PDFs
- Automatic chunking, embedding, and indexing via Celery workers
- **Hybrid search** combining semantic (vector) and keyword (BM25) retrieval
- **Cross-encoder reranking** for precision in top results
- Document management CRUD with status tracking

### Why Hybrid Search Over Pure Semantic
Pure semantic search misses exact matches. If a user searches "IRCTC train from Delhi to Manali", semantic search might return results about "Indian railway journeys" but miss the exact IRCTC reference. BM25 catches exact keyword matches. Combining both with Reciprocal Rank Fusion (RRF) gives the best of both worlds.

---

## Architecture Decisions

### Decision 1: pgvector vs Dedicated Vector DB
| Option | Performance | Ops Overhead | Cost |
|--------|------------|-------------|------|
| **pgvector (chosen)** | Good (up to ~5M vectors) | Zero (same DB) | Free |
| Pinecone | Excellent | Managed SaaS | $$$ at scale |
| Qdrant | Excellent | Self-hosted container | Free but extra infra |
| ChromaDB | Good for prototyping | Embedded only | Free |

**Why pgvector:** We already run PostgreSQL. Adding a separate vector DB means another service to manage, another backup strategy, another failure point. pgvector gives us HNSW indexing with excellent recall up to millions of vectors. When we hit limits, migrating to Qdrant is straightforward.

### Decision 2: Embedding Model
| Model | Dimensions | Speed | Quality | Size |
|-------|-----------|-------|---------|------|
| **all-MiniLM-L6-v2 (chosen)** | 384 | Fast | Good | 80MB |
| all-mpnet-base-v2 | 768 | Medium | Better | 420MB |
| text-embedding-3-small (OpenAI) | 1536 | API call | Best | N/A |

**Why MiniLM:** Runs locally (no API cost), fast enough for real-time search, and 384 dimensions keep storage manageable. For a travel app, the quality difference vs larger models is negligible — we're matching destinations, not doing legal document analysis.

### Decision 3: Chunking Strategy
- **Chunk size: 512 tokens** — large enough for context, small enough for precise retrieval
- **Overlap: 50 tokens** — prevents information loss at chunk boundaries
- **Splitter: RecursiveCharacterTextSplitter** — respects paragraph/sentence boundaries

---

## Database Schema

```sql
-- ══════════════════════════════════════════════════════════════════════
-- Phase 2 Database Tables
-- ══════════════════════════════════════════════════════════════════════

-- ── Documents (uploaded files) ──────────────────────────────────────
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'upload',  -- 'upload' | 'web_scrape' | 'manual'
    file_path VARCHAR(512),             -- MinIO object path
    file_type VARCHAR(20),              -- 'pdf' | 'txt' | 'md'
    file_size_bytes BIGINT,
    status VARCHAR(20) NOT NULL DEFAULT 'uploaded',
    -- status: uploaded → processing → chunked → embedded → failed
    chunk_count INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    -- example: {"destination": "Manali", "category": "travel_guide", "language": "en"}
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_user ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(status);

-- ── Document Chunks (with embeddings) ──────────────────────────────
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,       -- order within document
    token_count INTEGER NOT NULL,
    embedding vector(384) NOT NULL,     -- matches MiniLM output dimension
    metadata JSONB NOT NULL DEFAULT '{}',
    -- metadata: {"page": 3, "section": "Hotels", "destination": "Manali"}
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);

-- HNSW index for fast approximate nearest neighbor search
-- lists=100 works well up to ~1M vectors; increase for larger datasets
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index for full-text search (BM25-like keyword matching)
CREATE INDEX idx_chunks_content_trgm ON document_chunks
    USING gin (content gin_trgm_ops);

-- ── Embedding Cache ────────────────────────────────────────────────
CREATE TABLE embedding_cache (
    query_hash VARCHAR(64) PRIMARY KEY,  -- SHA-256 of the query text
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Key APIs

```
POST   /api/v1/documents/upload        Upload a document (PDF/TXT)
GET    /api/v1/documents                List user's documents
GET    /api/v1/documents/{id}           Get document details + status
DELETE /api/v1/documents/{id}           Delete document and its chunks

POST   /api/v1/rag/search              Hybrid search (semantic + BM25)
POST   /api/v1/rag/search/semantic     Semantic-only search
POST   /api/v1/rag/search/keyword      Keyword-only (BM25) search
```

---

## Implementation

### Embedding Service

```python
# apps/backend/src/parikrama/rag/embeddings.py
"""
Embedding model wrapper with caching.

Loads the model once at startup and reuses it.
Caches query embeddings in PostgreSQL to avoid redundant computation.
"""
import hashlib
from functools import lru_cache

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from parikrama.config import settings

logger = structlog.get_logger()


class EmbeddingService:
    """Generate and cache text embeddings using a local model."""

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the model on first use (saves ~2s on startup)."""
        if self._model is None:
            logger.info("loading_embedding_model", model=settings.EMBEDDING_MODEL)
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info("embedding_model_loaded", dimension=settings.EMBEDDING_DIMENSION)
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text string."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Generate embeddings for a batch of texts — much faster than one-by-one."""
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    @staticmethod
    def query_hash(text: str) -> str:
        """Generate a deterministic hash for caching embeddings."""
        return hashlib.sha256(text.strip().lower().encode()).hexdigest()


# singleton — expensive to initialize, so we reuse
embedding_service = EmbeddingService()
```

### Document Chunker

```python
# apps/backend/src/parikrama/rag/chunker.py
"""
Document chunking with configurable strategy.

Uses RecursiveCharacterTextSplitter which tries to split at:
1. Paragraphs (\\n\\n)
2. Sentences (. ! ?)
3. Words (spaces)
4. Characters (last resort)

This preserves semantic coherence within each chunk.
"""
import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter

from parikrama.config import settings

logger = structlog.get_logger()

# roughly 4 chars per token for English/Hindi mixed text
CHARS_PER_TOKEN = 4
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50


def create_splitter() -> RecursiveCharacterTextSplitter:
    """Build a text splitter with our standard chunking parameters."""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN,
        chunk_overlap=CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN,
        length_function=len,
        separators=[
            "\n\n",    # paragraphs first
            "\n",      # then newlines
            "। ",      # Hindi sentence boundary (purna viram)
            ". ",      # English sentence boundary
            "! ",
            "? ",
            ", ",
            " ",       # words
            "",        # chars
        ],
        is_separator_regex=False,
    )


def chunk_text(text: str, metadata: dict | None = None) -> list[dict]:
    """
    Split text into chunks with metadata.
    Returns list of {content, chunk_index, token_count, metadata}.
    """
    splitter = create_splitter()
    raw_chunks = splitter.split_text(text)

    chunks = []
    for i, content in enumerate(raw_chunks):
        token_count = len(content) // CHARS_PER_TOKEN
        chunks.append({
            "content": content,
            "chunk_index": i,
            "token_count": token_count,
            "metadata": {**(metadata or {}), "chunk_index": i},
        })

    logger.info(
        "text_chunked",
        total_chunks=len(chunks),
        avg_tokens=sum(c["token_count"] for c in chunks) // max(len(chunks), 1),
    )
    return chunks
```

### Hybrid Retriever (Semantic + BM25)

```python
# apps/backend/src/parikrama/rag/retriever.py
"""
Hybrid retriever combining semantic search (pgvector) and BM25 keyword search.

Uses Reciprocal Rank Fusion (RRF) to merge results from both methods.
RRF is model-free — it doesn't need training, just rank positions.

Flow:
1. User query → embed with MiniLM → cosine similarity search in pgvector
2. User query → BM25 keyword match against chunk content
3. Merge results using RRF formula: score = Σ 1/(k + rank)
4. Optionally rerank top-N with cross-encoder for precision
"""
import structlog
from rank_bm25 import BM25Okapi
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.rag.embeddings import embedding_service

logger = structlog.get_logger()

# RRF constant — 60 is standard, prevents high-ranked items from dominating
RRF_K = 60


class HybridRetriever:
    """Retrieve relevant document chunks using semantic + keyword search."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(
        self,
        query: str,
        top_k: int = 10,
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4,
        filter_metadata: dict | None = None,
    ) -> list[dict]:
        """
        Run hybrid search and return merged results.

        Args:
            query: User search query
            top_k: Number of results to return
            semantic_weight: Weight for semantic results in RRF
            keyword_weight: Weight for BM25 results in RRF
            filter_metadata: Optional filter (e.g., {"destination": "Manali"})
        """
        # fetch more candidates than needed — we'll merge and trim
        candidate_k = top_k * 3

        # run both searches concurrently
        semantic_results = await self._semantic_search(query, candidate_k, filter_metadata)
        keyword_results = await self._keyword_search(query, candidate_k, filter_metadata)

        # merge with RRF
        merged = self._reciprocal_rank_fusion(
            semantic_results, keyword_results,
            semantic_weight, keyword_weight,
        )

        logger.info(
            "hybrid_search_completed",
            query_length=len(query),
            semantic_hits=len(semantic_results),
            keyword_hits=len(keyword_results),
            merged_results=len(merged[:top_k]),
        )

        return merged[:top_k]

    async def _semantic_search(
        self, query: str, top_k: int, filter_metadata: dict | None = None,
    ) -> list[dict]:
        """Vector similarity search using pgvector's cosine distance."""
        query_embedding = embedding_service.embed_text(query)

        # build dynamic filter clause
        filter_clause = ""
        params = {"embedding": str(query_embedding), "limit": top_k}

        if filter_metadata:
            conditions = []
            for i, (key, value) in enumerate(filter_metadata.items()):
                param_name = f"meta_{i}"
                conditions.append(f"dc.metadata->>'{key}' = :{param_name}")
                params[param_name] = value
            if conditions:
                filter_clause = "AND " + " AND ".join(conditions)

        sql = text(f"""
            SELECT
                dc.id,
                dc.content,
                dc.metadata,
                dc.document_id,
                1 - (dc.embedding <=> :embedding::vector) AS similarity
            FROM document_chunks dc
            WHERE 1=1 {filter_clause}
            ORDER BY dc.embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "chunk_id": str(row.id),
                "content": row.content,
                "metadata": row.metadata,
                "document_id": str(row.document_id),
                "score": float(row.similarity),
                "source": "semantic",
            }
            for row in rows
        ]

    async def _keyword_search(
        self, query: str, top_k: int, filter_metadata: dict | None = None,
    ) -> list[dict]:
        """BM25-style keyword search using PostgreSQL trigram similarity."""
        filter_clause = ""
        params = {"query": query, "limit": top_k}

        if filter_metadata:
            conditions = []
            for i, (key, value) in enumerate(filter_metadata.items()):
                param_name = f"meta_{i}"
                conditions.append(f"dc.metadata->>'{key}' = :{param_name}")
                params[param_name] = value
            if conditions:
                filter_clause = "AND " + " AND ".join(conditions)

        sql = text(f"""
            SELECT
                dc.id,
                dc.content,
                dc.metadata,
                dc.document_id,
                similarity(dc.content, :query) AS sim_score
            FROM document_chunks dc
            WHERE dc.content % :query {filter_clause}
            ORDER BY sim_score DESC
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "chunk_id": str(row.id),
                "content": row.content,
                "metadata": row.metadata,
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
        """
        Merge two ranked lists using Reciprocal Rank Fusion.

        RRF score = Σ weight / (k + rank)
        where k=60 prevents top-ranked items from having outsized influence.
        """
        scores: dict[str, float] = {}
        chunk_data: dict[str, dict] = {}

        # score semantic results
        for rank, item in enumerate(semantic):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0) + semantic_weight / (RRF_K + rank + 1)
            chunk_data[chunk_id] = item

        # score keyword results
        for rank, item in enumerate(keyword):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0) + keyword_weight / (RRF_K + rank + 1)
            chunk_data[chunk_id] = item

        # sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [
            {**chunk_data[cid], "rrf_score": scores[cid]}
            for cid in sorted_ids
        ]
```

### Cross-Encoder Reranker

```python
# apps/backend/src/parikrama/rag/reranker.py
"""
Cross-encoder reranker for final precision boost.

After hybrid search returns top-K candidates, the cross-encoder
scores each (query, chunk) pair for relevance. This is more accurate
than bi-encoder similarity but too slow for the initial retrieval.

Pipeline: Hybrid Search (fast, recall) → Rerank (slow, precision)
"""
import structlog
from sentence_transformers import CrossEncoder

logger = structlog.get_logger()


class Reranker:
    """Rerank search results using a cross-encoder model."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model: CrossEncoder | None = None
        self._model_name = model_name

    @property
    def model(self) -> CrossEncoder:
        if self._model is None:
            logger.info("loading_reranker", model=self._model_name)
            self._model = CrossEncoder(self._model_name)
        return self._model

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        """
        Rerank search results using cross-encoder scoring.

        Args:
            query: Original user query
            results: List of search results with 'content' field
            top_k: Number of top results to return after reranking
        """
        if not results:
            return []

        # cross-encoder expects pairs of (query, document)
        pairs = [(query, r["content"]) for r in results]
        scores = self.model.predict(pairs)

        # attach rerank scores
        for result, score in zip(results, scores):
            result["rerank_score"] = float(score)

        # sort by cross-encoder score (higher = more relevant)
        reranked = sorted(results, key=lambda x: x["rerank_score"], reverse=True)

        logger.info(
            "reranking_completed",
            input_count=len(results),
            output_count=min(top_k, len(reranked)),
        )

        return reranked[:top_k]


# singleton
reranker = Reranker()
```

### RAG Service (Orchestrates Search Pipeline)

```python
# apps/backend/src/parikrama/services/rag_service.py
"""
RAG service — the main interface for knowledge retrieval.

Combines hybrid retriever + reranker into a single search pipeline.
Agents call this to get grounded information before generating responses.
"""
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.rag.embeddings import embedding_service
from parikrama.rag.reranker import reranker
from parikrama.rag.retriever import HybridRetriever
from parikrama.schemas.rag import SearchRequest, SearchResult

logger = structlog.get_logger()


class RAGService:
    """High-level RAG search interface used by agents and API endpoints."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.retriever = HybridRetriever(db)

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        """
        Full RAG search pipeline: retrieve → rerank → format.

        This is what agents call when they need travel knowledge.
        """
        # step 1: hybrid retrieval (semantic + BM25)
        candidates = await self.retriever.search(
            query=request.query,
            top_k=request.top_k * 3,  # fetch more for reranking
            semantic_weight=request.semantic_weight,
            keyword_weight=request.keyword_weight,
            filter_metadata=request.filter_metadata,
        )

        if not candidates:
            logger.info("rag_search_no_results", query=request.query)
            return []

        # step 2: cross-encoder reranking for precision
        if request.use_reranker and len(candidates) > 1:
            reranked = reranker.rerank(
                query=request.query,
                results=candidates,
                top_k=request.top_k,
            )
        else:
            reranked = candidates[:request.top_k]

        # step 3: format results
        results = [
            SearchResult(
                chunk_id=r["chunk_id"],
                content=r["content"],
                metadata=r.get("metadata", {}),
                document_id=r["document_id"],
                score=r.get("rerank_score", r.get("rrf_score", r.get("score", 0))),
            )
            for r in reranked
        ]

        logger.info(
            "rag_search_completed",
            query=request.query[:50],
            results_count=len(results),
            top_score=results[0].score if results else 0,
        )

        return results
```

### Document Ingestion (Celery Worker Task)

```python
# apps/worker/src/parikrama_worker/tasks/document_tasks.py
"""
Async document processing pipeline — runs in Celery workers.

Flow: Upload → Extract text → Chunk → Embed → Store
Each step updates the document status so the frontend can show progress.
"""
import uuid

import pymupdf
import structlog
from celery import shared_task
from sqlalchemy import update
from sqlalchemy.orm import Session

from parikrama_worker.config import get_sync_session
from parikrama_common.enums import DocumentStatus

logger = structlog.get_logger()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="process_document",
)
def process_document(self, document_id: str, file_path: str) -> dict:
    """
    Process an uploaded document: extract → chunk → embed → store.

    This runs in a Celery worker to avoid blocking the API server.
    The embedding model is loaded once per worker process.
    """
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("document_processing_started")

    db = get_sync_session()
    try:
        # step 1: update status to processing
        _update_status(db, document_id, DocumentStatus.PROCESSING)

        # step 2: extract text from file
        text = _extract_text(file_path)
        if not text.strip():
            raise ValueError("Extracted text is empty — file might be image-only PDF")

        log.info("text_extracted", char_count=len(text))

        # step 3: chunk the text
        from parikrama.rag.chunker import chunk_text
        chunks = chunk_text(text, metadata={"document_id": document_id})
        _update_status(db, document_id, DocumentStatus.CHUNKED)

        log.info("text_chunked", chunk_count=len(chunks))

        # step 4: generate embeddings in batches
        from parikrama.rag.embeddings import embedding_service
        contents = [c["content"] for c in chunks]
        embeddings = embedding_service.embed_batch(contents)

        # step 5: store chunks with embeddings
        from parikrama.models.document import DocumentChunk
        chunk_records = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk_records.append(DocumentChunk(
                id=uuid.uuid4(),
                document_id=uuid.UUID(document_id),
                content=chunk["content"],
                chunk_index=chunk["chunk_index"],
                token_count=chunk["token_count"],
                embedding=embedding,
                metadata=chunk["metadata"],
            ))

        db.bulk_save_objects(chunk_records)

        # step 6: update document with final status and chunk count
        db.execute(
            update(Document)
            .where(Document.id == uuid.UUID(document_id))
            .values(status=DocumentStatus.EMBEDDED, chunk_count=len(chunks))
        )
        db.commit()

        log.info("document_processing_completed", chunks_stored=len(chunks))
        return {"status": "success", "chunks": len(chunks)}

    except Exception as exc:
        db.rollback()
        _update_status(db, document_id, DocumentStatus.FAILED, error=str(exc))
        log.error("document_processing_failed", error=str(exc))
        raise self.retry(exc=exc)
    finally:
        db.close()


def _extract_text(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF (fastest Python PDF library)."""
    doc = pymupdf.open(file_path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n\n".join(text_parts)


def _update_status(
    db: Session,
    document_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """Update document processing status in database."""
    from parikrama.models.document import Document
    values = {"status": status}
    if error:
        values["error_message"] = error
    db.execute(
        update(Document)
        .where(Document.id == uuid.UUID(document_id))
        .values(**values)
    )
    db.commit()
```

### RAG Search Schemas

```python
# apps/backend/src/parikrama/schemas/rag.py (within schemas/)
"""Schemas for RAG search requests and responses."""
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    semantic_weight: float = Field(default=0.6, ge=0, le=1)
    keyword_weight: float = Field(default=0.4, ge=0, le=1)
    use_reranker: bool = True
    filter_metadata: dict | None = None


class SearchResult(BaseModel):
    chunk_id: str
    content: str
    metadata: dict
    document_id: str
    score: float
```

---

## Environment Variables Required

```bash
# New in Phase 2:
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
EMBEDDING_BATCH_SIZE=32
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| Chunking produces correct sizes | Unit | Chunks ~512 tokens, overlap works |
| Hindi text chunking | Unit | Purna viram (।) splitting works |
| Embedding dimensions match | Unit | Output is 384-dimensional |
| Semantic search returns ranked results | Integration | pgvector cosine search works |
| Keyword search finds exact matches | Integration | Trigram matching works |
| RRF merges correctly | Unit | Fusion formula produces valid scores |
| Reranker improves precision | Integration | Cross-encoder rescores accurately |
| Document processing end-to-end | Integration | PDF → chunks → embeddings in DB |

---

## Definition of Done — Phase 2

- [ ] pgvector extension enabled with HNSW index
- [ ] Document upload endpoint stores file in MinIO
- [ ] Celery task extracts PDF text, chunks, embeds, and stores
- [ ] Document status updates in real-time (uploaded → processing → embedded)
- [ ] Hybrid search returns merged semantic + keyword results
- [ ] Cross-encoder reranker improves top-5 precision
- [ ] Document CRUD endpoints (list, detail, delete)
- [ ] Embedding cache prevents redundant computation
- [ ] Hindi text chunking works with purna viram separator
- [ ] Integration tests cover full ingestion pipeline

## Common Pitfalls

| Pitfall | How to Avoid |
|---------|-------------|
| **pgvector not installed** | Use `pgvector/pgvector:pg16` Docker image |
| **Embedding dimension mismatch** | `EMBEDDING_DIMENSION` must match model output |
| **Worker can't find model** | Models download on first use — worker needs internet |
| **Large PDF OOM** | Set Celery worker memory limits, process pages in batches |
| **BM25 empty results** | Ensure `pg_trgm` extension is enabled and similarity threshold is reasonable |

## Scale-Up Path

| Component | Current | Trigger | Upgrade |
|-----------|---------|---------|---------|
| pgvector | HNSW index | > 5M chunks | Qdrant or Weaviate |
| Embedding Model | MiniLM (384d) | Need multilingual | multilingual-e5-large |
| Reranker | ms-marco-MiniLM | Latency > 500ms | Cohere Rerank API |
| Chunking | Fixed 512 tokens | Complex docs | Semantic chunking (by topic) |

---

*Phase 2 gives our agents a knowledge backbone. The Research Agent (Phase 4) will call `RAGService.search()` to ground every recommendation in real data.*
