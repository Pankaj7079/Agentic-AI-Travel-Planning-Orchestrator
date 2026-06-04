"""
Trip model — stores trip planning sessions and results.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from parikrama.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Trip(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A trip planning session — from user request to final itinerary."""

    __tablename__ = "trips"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)

    # original request
    request: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # generated result
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # LangGraph state persistence
    thread_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    # metrics
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    planning_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Trip {self.id} ({self.status})>"


class AgentRun(Base, UUIDPrimaryKeyMixin):
    """Individual agent execution within a trip planning session."""

    __tablename__ = "agent_runs"

    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")

    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=__import__("sqlalchemy").func.now(),
        nullable=False,
    )
