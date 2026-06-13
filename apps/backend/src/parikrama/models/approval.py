"""
ApprovalRequest model — human-in-the-loop gate for expensive agent decisions.

When the Booking Agent finds a hotel or transport exceeding budget thresholds,
it creates an ApprovalRequest instead of proceeding automatically. The user
must approve or reject before the pipeline continues.

Lifecycle: pending → approved | rejected | expired
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from parikrama.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApprovalRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A pending human decision gate in the trip planning pipeline.

    Created when an agent reaches a decision point requiring user consent
    (e.g. booking a hotel that consumes >50% of the budget).
    """

    __tablename__ = "approval_requests"

    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # what kind of approval is this?
    type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="hotel_booking | transport_booking | budget_exceed",
    )

    # human-readable summary shown in the UI
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # structured data for the UI (hotel options, prices, etc.)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    # lifecycle
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
        comment="pending | approved | rejected | expired",
    )

    # user's response (modifications or rejection reason)
    user_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # hard deadline — Celery task expires these automatically
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ApprovalRequest {self.id} ({self.type}, {self.status})>"
