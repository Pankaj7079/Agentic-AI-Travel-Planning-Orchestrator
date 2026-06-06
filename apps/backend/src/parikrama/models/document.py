"""
Document models — stores uploaded files and their vector chunks for the RAG pipeline.

Two models:
- Document: metadata about an uploaded file (stored in MinIO)
- DocumentChunk: text chunk + 384-dim embedding (stored in pgvector)
"""

from __future__ import annotations

import uuid  # noqa: TC003

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from parikrama.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# pgvector Column type — lazy import so the model can still load without pgvector
try:
    from pgvector.sqlalchemy import Vector

    _VECTOR_AVAILABLE = True
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment,misc]
    _VECTOR_AVAILABLE = False

EMBEDDING_DIMENSION = 384


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Uploaded document processed by the RAG pipeline.

    Files are stored in MinIO; only metadata + chunk embeddings in Postgres.

    Status flow: uploaded → processing → chunked → embedded → failed (on error)
    """

    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", index=True)
    minio_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Destination context — which trip or destination this doc belongs to
    destination: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship — delete chunks when document is deleted
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Document {self.filename!r} status={self.status}>"


class DocumentChunk(Base, UUIDPrimaryKeyMixin):
    """
    A text chunk extracted from a Document, stored alongside its embedding.

    The ``embedding`` column uses pgvector's vector type (384-dim for MiniLM).
    Queries use cosine distance (``<=>`` operator) over the HNSW index.
    """

    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    # pgvector column — requires pgvector extension in Postgres
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSION) if _VECTOR_AVAILABLE else Text,  # type: ignore[arg-type]
        nullable=False,
    )

    # Relationship back to document
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk doc={self.document_id} "
            f"idx={self.chunk_index} tokens={self.token_count}>"
        )
