"""Phase 2 — Add document_chunks table with pgvector HNSW index and pg_trgm GIN index.

Revision ID: 0002_document_chunks
Revises: 0001_initial_schema
Create Date: 2026-06-05 00:00:00

This migration:
1. Enables pg_trgm extension (for BM25-style keyword search)
2. Creates document_chunks table with vector(384) column
3. Creates HNSW index for fast approximate nearest-neighbor vector search
4. Creates GIN trigram index on content for keyword search
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_document_chunks"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Enable required PostgreSQL extensions ───────────────────────────────
    # pg_trgm: trigram similarity for BM25-style keyword search
    # vector: pgvector for cosine similarity search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── 2. Create document_chunks table ───────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        # vector(384) = all-MiniLM-L6-v2 output dimension
        # Stored as a pgvector native type; requires pgvector extension above.
        sa.Column(
            "embedding",
            sa.Text,  # Alembic doesn't know pgvector natively; raw SQL handles the cast
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── 3. Alter embedding column to proper vector type ────────────────────────
    # We create it as Text above (Alembic-compatible), then alter to vector(384).
    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)"
    )

    # ── 4. B-tree index on document_id for fast join / delete cascade ─────────
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    # ── 5. HNSW index for fast approximate nearest-neighbor vector search ──────
    # m=16: max connections per node (16 is the standard default)
    # ef_construction=64: build-time quality vs speed tradeoff
    # vector_cosine_ops: cosine distance operator (<=>)
    # For >1M vectors, increase ef_construction to 128 and m to 32.
    op.execute(
        """
        CREATE INDEX ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # ── 6. GIN trigram index on content for BM25-style keyword search ─────────
    # Enables: SELECT ... WHERE content % :query (trigram similarity)
    # and: SELECT ... ORDER BY similarity(content, :query) DESC
    op.execute(
        """
        CREATE INDEX ix_document_chunks_content_trgm
        ON document_chunks
        USING gin (content gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_content_trgm", table_name="document_chunks")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    # Note: We intentionally do NOT drop the extensions — they may be used by
    # other migrations. Drop them manually if truly needed.
