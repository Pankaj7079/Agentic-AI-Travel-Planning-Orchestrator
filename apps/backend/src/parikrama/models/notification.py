"""
Notification model — persisted record of every notification sent.

Tracks what was sent, to whom, via which channels, and whether the user
has acknowledged it. Powers the notification inbox UI.
"""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from parikrama.models.base import Base, UUIDPrimaryKeyMixin


class Notification(Base, UUIDPrimaryKeyMixin):
    """
    An in-app notification record.

    Created whenever NotificationService.send() is called.
    Channels that were actually used are stored in channels_sent.
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # notification category (from NotificationType enum)
    type: Mapped[str] = mapped_column(String(30), nullable=False)

    # display content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # structured payload (trip_id, approval_id, etc.)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    # delivery audit — which channels actually sent
    channels_sent: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}"
    )

    # read state
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=__import__("sqlalchemy").func.now(),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.id} ({self.type}, read={self.is_read})>"
