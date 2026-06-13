"""Add approval_requests and notifications tables for Phase 5 HITL.

approval_requests: Stores human-in-the-loop gate records when agents need
user consent before taking expensive/irreversible actions.

notifications: Persists every notification sent across all channels
(WebSocket, email, push) for the notification inbox UI.

Revision ID: 0003_add_approvals_notifications
Revises: 0002_add_agent_runs
Create Date: 2024-06-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_add_approvals_notifications"
down_revision: str | None = "0002_add_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── approval_requests ───────────────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "user_response",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_approvals_user", "approval_requests", ["user_id"])
    op.create_index("idx_approvals_trip", "approval_requests", ["trip_id"])
    op.create_index("idx_approvals_status", "approval_requests", ["status"])
    # partial index: only index pending rows for fast expiry scan
    op.create_index(
        "idx_approvals_expires_pending",
        "approval_requests",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ── notifications ────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "channels_sent",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_notifications_user", "notifications", ["user_id"])
    # partial index: fast unread count queries
    op.create_index(
        "idx_notifications_unread",
        "notifications",
        ["user_id", "is_read"],
        postgresql_where=sa.text("is_read = false"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("approval_requests")
