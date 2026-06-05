"""
Document service — manages uploaded travel document lifecycle.

Flow:
1. User POSTs a file → validate → upload to MinIO → create DB record → queue Celery task
2. Celery worker processes the file asynchronously (chunk + embed)
3. User can check status, list, or delete their documents
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select

from parikrama.models.document import Document
from parikrama.schemas.rag import DocumentListResponse, DocumentResponse, DocumentUploadResponse
from parikrama.services import storage_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class DocumentService:
    """Business logic for document upload, listing, and deletion."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Upload ─────────────────────────────────────────────────────────────────

    async def upload_document(
        self,
        *,
        user_id: uuid.UUID,
        file_data: bytes,
        filename: str,
        content_type: str,
        destination: str | None = None,
        description: str | None = None,
    ) -> DocumentUploadResponse:
        """Upload a document to MinIO and queue it for RAG processing.

        Args:
            user_id: ID of the uploading user.
            file_data: Raw file bytes.
            filename: Original filename.
            content_type: MIME type.
            destination: Optional travel destination tag, e.g. ``"Manali"``.
            description: Optional free-text description for the document.

        Returns:
            ``DocumentUploadResponse`` with the new document's ID and status.

        Raises:
            ValueError: If file validation fails (see ``storage_service.upload_file``).
        """
        # 1. Upload file to MinIO
        minio_key, size = storage_service.upload_file(
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            user_id=str(user_id),
        )

        # 2. Create Document record in Postgres
        doc = Document(
            id=uuid.uuid4(),
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            status="uploaded",
            minio_key=minio_key,
            file_size_bytes=size,
            chunk_count=0,
            destination=destination,
            description=description,
        )
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)

        logger.info(
            "document_created",
            document_id=str(doc.id),
            filename=filename,
            size_bytes=size,
            user_id=str(user_id),
        )

        # 3. Queue Celery processing task (import here to avoid circular deps)
        self._queue_processing(str(doc.id), minio_key)

        return DocumentUploadResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status,  # type: ignore[arg-type]
            file_size_bytes=doc.file_size_bytes,
            destination=doc.destination,
        )

    def _queue_processing(self, document_id: str, minio_key: str) -> None:
        """Queue a Celery task to process the document.

        Imported lazily to avoid importing Celery at module level (keeps
        the backend server boot fast when no Celery broker is needed).
        """
        try:
            from parikrama_worker.tasks.document_tasks import (
                process_document,  # type: ignore[import]
            )

            process_document.delay(document_id, minio_key)
            logger.info("document_processing_queued", document_id=document_id)
        except ImportError:
            # Worker package not installed in the API environment — log and skip.
            # This is fine for testing; real deployment runs API + Worker separately.
            logger.warning(
                "celery_worker_not_available",
                document_id=document_id,
                hint="Install parikrama-worker to enable background processing.",
            )
        except Exception as exc:
            logger.error(
                "document_queue_failed",
                document_id=document_id,
                error=str(exc),
            )

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_documents(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        destination_filter: str | None = None,
    ) -> DocumentListResponse:
        """List all documents for a user, paginated.

        Args:
            user_id: Filter by this user's documents.
            page: 1-based page number.
            page_size: Results per page (max 100).
            status_filter: Optional status filter, e.g. ``"embedded"``.
            destination_filter: Optional destination filter, e.g. ``"Manali"``.

        Returns:
            Paginated ``DocumentListResponse``.
        """
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        base_q = select(Document).where(Document.user_id == user_id)
        if status_filter:
            base_q = base_q.where(Document.status == status_filter)
        if destination_filter:
            base_q = base_q.where(Document.destination == destination_filter)

        # Count query
        count_q = select(func.count()).select_from(base_q.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        # Paginated items
        items_q = base_q.order_by(Document.created_at.desc()).offset(offset).limit(page_size)
        rows = (await self.db.execute(items_q)).scalars().all()

        return DocumentListResponse(
            items=[DocumentResponse.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DocumentResponse | None:
        """Get a single document by ID.

        Args:
            document_id: Target document UUID.
            user_id: Must match document owner (authorization check).

        Returns:
            ``DocumentResponse`` if found and owned by user, else ``None``.
        """
        q = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        doc = (await self.db.execute(q)).scalar_one_or_none()
        if doc is None:
            return None
        return DocumentResponse.model_validate(doc)

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete a document and all its chunks (cascade) + MinIO file.

        Args:
            document_id: Target document UUID.
            user_id: Must match document owner.

        Returns:
            ``True`` if deleted, ``False`` if not found or not authorized.
        """
        q = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        doc = (await self.db.execute(q)).scalar_one_or_none()
        if doc is None:
            return False

        # Delete from MinIO (best-effort)
        try:
            storage_service.delete_file(doc.minio_key)
        except Exception as exc:
            logger.warning(
                "minio_delete_failed_continuing",
                document_id=str(document_id),
                error=str(exc),
            )

        await self.db.delete(doc)
        await self.db.commit()

        logger.info("document_deleted", document_id=str(document_id), user_id=str(user_id))
        return True
