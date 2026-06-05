"""
Document management API routes.

Endpoints:
    POST   /api/v1/documents/upload       Upload a document for RAG processing
    GET    /api/v1/documents              List user's documents (paginated)
    GET    /api/v1/documents/{id}         Get document details + processing status
    DELETE /api/v1/documents/{id}         Delete document and all its chunks
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.security import get_current_user_id
from parikrama.db.session import get_db
from parikrama.schemas.rag import DocumentListResponse, DocumentResponse, DocumentUploadResponse
from parikrama.services.document_service import DocumentService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Upload ─────────────────────────────────────────────────────────────────────


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for RAG processing",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF or TXT file to upload."),
    destination: str | None = Form(None, description="Travel destination tag, e.g. 'Manali'."),
    description: str | None = Form(None, description="Optional description of the document."),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> DocumentUploadResponse:
    """Upload a travel guide, review, or any PDF/TXT for knowledge base indexing.

    The file is uploaded to MinIO and background processing starts immediately:
    text extraction → chunking → embedding → stored in pgvector.

    Monitor progress via ``GET /documents/{id}`` (status: uploaded → embedded).
    """
    if file.content_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content type header is required.",
        )

    file_data = await file.read()
    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    service = DocumentService(db)
    try:
        return await service.upload_document(
            user_id=uuid.UUID(user_id),
            file_data=file_data,
            filename=file.filename or "document",
            content_type=file.content_type,
            destination=destination,
            description=description,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


# ── List ───────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List your uploaded documents",
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page."),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status: uploaded|processing|chunked|embedded|failed.",
    ),
    destination: str | None = Query(default=None, description="Filter by destination tag."),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> DocumentListResponse:
    """List all documents uploaded by the current user, with optional filters."""
    service = DocumentService(db)
    return await service.list_documents(
        user_id=uuid.UUID(user_id),
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        destination_filter=destination,
    )


# ── Get ────────────────────────────────────────────────────────────────────────


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details and processing status",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> DocumentResponse:
    """Retrieve details for a single document. Use to poll processing status."""
    service = DocumentService(db)
    doc = await service.get_document(document_id, uuid.UUID(user_id))
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you do not have permission to view it.",
        )
    return doc


# ── Delete ─────────────────────────────────────────────────────────────────────


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and all its chunks",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Delete a document from MinIO, all its vector chunks from Postgres, and the metadata record.

    This is irreversible. The document will need to be re-uploaded if deleted accidentally.
    """
    service = DocumentService(db)
    deleted = await service.delete_document(document_id, uuid.UUID(user_id))
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you do not have permission to delete it.",
        )
