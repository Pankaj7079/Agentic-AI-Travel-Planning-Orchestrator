"""
Celery task for asynchronous document processing.

Flow:
  Upload API → MinIO → DB record (status=uploaded) → [this task queued]
  [Worker] → download from MinIO → extract text → chunk → embed → store chunks
           → update DB status (processing → chunked → embedded)

Retries: 3 attempts with 60-second delay (handles transient MinIO/Postgres outages).
"""

from __future__ import annotations

import os
import uuid

import structlog
from celery import shared_task
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

logger = structlog.get_logger(__name__)

# ── Sync DB setup for Celery workers (Celery doesn't support async SQLAlchemy) ─
DATABASE_URL = os.getenv(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg2://parikrama:parikrama_dev_2024@localhost:5432/parikrama",
)


def _get_sync_engine():
    """Create a synchronous SQLAlchemy engine for the Celery worker."""
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=2, max_overflow=5)


def _get_sync_session() -> Session:
    """Return a new synchronous database session."""
    engine = _get_sync_engine()
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return SessionLocal()


# ── Document Processing Task ───────────────────────────────────────────────────


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="parikrama_worker.tasks.document_tasks.process_document",
    queue="documents",
)
def process_document(self, document_id: str, minio_key: str) -> dict:
    """Process an uploaded document: download → extract text → chunk → embed → store.

    This is the core RAG ingestion pipeline. Runs asynchronously in a Celery worker.

    Args:
        document_id: UUID of the ``documents`` DB record to process.
        minio_key: MinIO object key where the file is stored.

    Returns:
        Dict with ``{"status": "success", "chunks": N}`` on success.

    Raises:
        Exception: Re-raised after retries are exhausted (Celery handles logging).
    """
    log = logger.bind(document_id=document_id, task_id=self.request.id)
    log.info("document_processing_started", minio_key=minio_key)

    db = _get_sync_session()
    try:
        # ── Step 1: Mark as processing ────────────────────────────────────────
        _update_status(db, document_id, "processing")

        # ── Step 2: Download file from MinIO ──────────────────────────────────
        file_bytes = _download_from_minio(minio_key)
        log.info("file_downloaded", size_bytes=len(file_bytes))

        # ── Step 3: Extract text based on file type ───────────────────────────
        content_type = _detect_content_type(minio_key)
        if "pdf" in content_type or minio_key.lower().endswith(".pdf"):
            pages = _extract_pdf_pages(file_bytes)
            raw_text = "\n\n".join(pages)
        else:
            raw_text = file_bytes.decode("utf-8", errors="replace")

        if not raw_text.strip():
            raise ValueError("Extracted text is empty — file may be image-only PDF or corrupted.")

        log.info("text_extracted", char_count=len(raw_text))

        # ── Step 4: Chunk the text ────────────────────────────────────────────
        from parikrama.rag.chunker import chunk_text

        chunks = chunk_text(
            raw_text,
            metadata={"document_id": document_id},
        )
        _update_status(db, document_id, "chunked")
        log.info("text_chunked", chunk_count=len(chunks))

        # ── Step 5: Generate embeddings in batches ────────────────────────────
        from parikrama.rag.embeddings import embedding_service

        contents = [c["content"] for c in chunks]
        embeddings = embedding_service.embed_batch(contents, batch_size=32)
        log.info("embeddings_generated", count=len(embeddings))

        # ── Step 6: Store chunks with embeddings in Postgres ──────────────────
        _store_chunks(db, document_id, chunks, embeddings)

        # ── Step 7: Update document status to embedded ────────────────────────
        db.execute(
            text(
                "UPDATE documents SET status='embedded', chunk_count=:count WHERE id=:doc_id::uuid"
            ),
            {"count": len(chunks), "doc_id": document_id},
        )
        db.commit()

        log.info("document_processing_completed", chunks_stored=len(chunks))
        return {"status": "success", "chunks": len(chunks)}

    except Exception as exc:
        db.rollback()
        _update_status(db, document_id, "failed", error=str(exc))
        log.error("document_processing_failed", error=str(exc))
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


# ── Private helpers ────────────────────────────────────────────────────────────


def _download_from_minio(minio_key: str) -> bytes:
    """Download a file from MinIO by its object key."""
    from minio import Minio

    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    bucket = "parikrama-documents"

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    response = client.get_object(bucket, minio_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _extract_pdf_pages(file_bytes: bytes) -> list[str]:
    """Extract text from each page of a PDF using PyMuPDF (fastest Python PDF lib)."""
    import io

    try:
        import pymupdf  # type: ignore[import]
    except ImportError:
        import fitz as pymupdf  # type: ignore[import,no-redef]

    doc = pymupdf.open(stream=io.BytesIO(file_bytes), filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return pages


def _detect_content_type(minio_key: str) -> str:
    """Infer content type from the file extension in the MinIO key."""
    if minio_key.lower().endswith(".pdf"):
        return "application/pdf"
    if minio_key.lower().endswith((".txt", ".md")):
        return "text/plain"
    return "application/octet-stream"


def _store_chunks(
    db: Session,
    document_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    """Bulk-insert DocumentChunks with embeddings into Postgres.

    Uses raw SQL INSERT for performance (avoids ORM overhead for bulk ops).
    pgvector accepts embeddings as formatted list strings.
    """
    insert_sql = text(
        """
        INSERT INTO document_chunks
            (id, document_id, content, chunk_index, token_count, metadata, embedding)
        VALUES
            (:id, :document_id::uuid, :content, :chunk_index,
             :token_count, :metadata::jsonb, :embedding::vector)
        """
    )

    import json as json_lib

    records = []
    for chunk, embedding in zip(chunks, embeddings, strict=False):
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"
        records.append(
            {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "content": chunk["content"],
                "chunk_index": chunk["chunk_index"],
                "token_count": chunk["token_count"],
                "metadata": json_lib.dumps(chunk.get("metadata", {})),
                "embedding": embedding_str,
            }
        )

    db.execute(insert_sql, records)
    db.commit()
    logger.info("chunks_stored", count=len(records), document_id=document_id)


def _update_status(
    db: Session,
    document_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """Update a document's processing status in the database."""
    if error:
        db.execute(
            text(
                "UPDATE documents SET status=:status, error_message=:error WHERE id=:doc_id::uuid"
            ),
            {"status": status, "error": error, "doc_id": document_id},
        )
    else:
        db.execute(
            text("UPDATE documents SET status=:status WHERE id=:doc_id::uuid"),
            {"status": status, "doc_id": document_id},
        )
    db.commit()
