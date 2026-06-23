"""
NotificationService — multi-channel notification delivery.

Delivery priority:
1. WebSocket (instant, best-effort) — always attempted
2. Email via Resend (1-5s, skipped if RESEND_API_KEY not set)
3. Push via FCM (logged stub until Phase 7 frontend is built)

Persists a Notification record regardless of delivery outcome so users
can access their full notification history in the inbox.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from parikrama.api.websocket.manager import ws_manager
from parikrama.config import settings
from parikrama.models.notification import Notification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.models.user import User

logger = structlog.get_logger(__name__)


class NotificationService:
    """Deliver notifications across all enabled channels and persist the record."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def send(
        self,
        user: User,
        notification_type: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> str:
        """
        Send a notification to a user via all enabled channels.

        Args:
            user: The recipient User ORM object.
            notification_type: Value from NotificationType enum (e.g. 'approval_required').
            title: Short heading (shown in push/email subject).
            body: Full notification text.
            data: Extra context payload (trip_id, approval_id, etc.).

        Returns:
            notification_id (UUID string) for the persisted record.
        """
        notification_id = str(uuid.uuid4())
        channels_sent: list[str] = []
        extra = data or {}

        # ── Channel 1: WebSocket (instant, always tried) ──────────────────
        ws_sent = await ws_manager.send_to_user(
            str(user.id),
            {
                "type": "notification",
                "notification_id": notification_id,
                "notification_type": notification_type,
                "title": title,
                "body": body,
                "data": extra,
            },
        )
        if ws_sent > 0:
            channels_sent.append("websocket")

        # ── Channel 2: Email via Resend or SMTP ──────────────────────────────
        if user.email_notifications:
            if settings.RESEND_API_KEY:
                try:
                    await self._send_email(user.email, title, body, extra)
                    channels_sent.append("email")
                except Exception as exc:
                    logger.error(
                        "email_notification_failed_resend",
                        user_id=str(user.id),
                        error=str(exc)[:200],
                    )
            elif settings.SMTP_HOST:
                try:
                    await self._send_email_smtp(user.email, title, body, extra)
                    channels_sent.append("email")
                except Exception as exc:
                    logger.error(
                        "email_notification_failed_smtp",
                        user_id=str(user.id),
                        error=str(exc)[:200],
                    )

        # ── Channel 3: Push via FCM (stub until Phase 7 frontend) ─────────
        if user.push_notifications and user.fcm_token:
            try:
                await self._send_push(user.fcm_token, title, body, extra)
                channels_sent.append("push")
            except Exception as exc:
                logger.warning(
                    "push_notification_skipped",
                    user_id=str(user.id),
                    error=str(exc)[:100],
                )

        # ── Persist record ─────────────────────────────────────────────────
        notification = Notification(
            id=uuid.UUID(notification_id),
            user_id=user.id,
            type=notification_type,
            title=title,
            body=body,
            data=extra,
            channels_sent=channels_sent,
        )
        self.db.add(notification)
        # caller is responsible for db.commit() / db.flush()

        logger.info(
            "notification_sent",
            notification_id=notification_id,
            user_id=str(user.id),
            type=notification_type,
            channels=channels_sent,
        )
        return notification_id

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _send_email(self, to_email: str, title: str, body: str, data: dict[str, Any]) -> None:
        """Send email notification via Resend API."""
        import resend  # lazy import — only needed when RESEND_API_KEY is set

        resend.api_key = settings.RESEND_API_KEY

        action_url = data.get("action_url", "")
        action_html = (
            f'<p style="margin-top:16px;">'
            f'<a href="{action_url}" style="background:#4F46E5;color:white;padding:10px 20px;'
            f'border-radius:6px;text-decoration:none;">View in PariKrama</a></p>'
            if action_url
            else ""
        )

        resend.Emails.send(
            {
                "from": settings.RESEND_FROM_EMAIL,
                "to": [to_email],
                "subject": f"PariKrama: {title}",
                "html": f"""
                <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
                    <h2 style="color:#4F46E5;margin-bottom:8px;">{title}</h2>
                    <p style="color:#374151;line-height:1.6;">{body}</p>
                    {action_html}
                    <hr style="margin:24px 0;border:none;border-top:1px solid #E5E7EB;">
                    <p style="color:#9CA3AF;font-size:12px;">
                        You are receiving this from PariKrama AI Travel Planner.
                        <a href="http://localhost:3000/settings" style="color:#6B7280;">
                            Manage notification preferences
                        </a>
                    </p>
                </div>
                """,
            }
        )
        logger.info("email_sent", to=to_email, title=title)

    async def _send_email_smtp(self, to_email: str, title: str, body: str, data: dict[str, Any]) -> None:
        """Send email notification via open-source SMTP (Nodemailer style)."""
        import aiosmtplib
        from email.message import EmailMessage

        action_url = data.get("action_url", "")
        action_html = (
            f'<p style="margin-top:16px;">'
            f'<a href="{action_url}" style="background:#4F46E5;color:white;padding:10px 20px;'
            f'border-radius:6px;text-decoration:none;">View in PariKrama</a></p>'
            if action_url
            else ""
        )

        message = EmailMessage()
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = to_email
        message["Subject"] = f"PariKrama: {title}"

        html_content = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
            <h2 style="color:#4F46E5;margin-bottom:8px;">{title}</h2>
            <p style="color:#374151;line-height:1.6;">{body}</p>
            {action_html}
            <hr style="margin:24px 0;border:none;border-top:1px solid #E5E7EB;">
            <p style="color:#9CA3AF;font-size:12px;">
                You are receiving this from PariKrama AI Travel Planner.
                <a href="http://localhost:3000/settings" style="color:#6B7280;">
                    Manage notification preferences
                </a>
            </p>
        </div>
        """
        message.set_content(body)
        message.add_alternative(html_content, subtype="html")

        # SMTP SSL or TLS logic
        use_tls = settings.SMTP_PORT == 587
        use_ssl = settings.SMTP_PORT == 465

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER if settings.SMTP_USER else None,
            password=settings.SMTP_PASS if settings.SMTP_PASS else None,
            use_tls=use_ssl,
            start_tls=use_tls,
        )
        logger.info("email_sent_smtp", to=to_email, title=title)

    async def _send_push(self, fcm_token: str, title: str, body: str, data: dict[str, Any]) -> None:
        """
        Send push notification via Firebase Cloud Messaging.

        Currently a logged stub — FCM integration is completed in Phase 7
        when the React Native / PWA frontend is built.
        """
        logger.info(
            "push_notification_stub",
            fcm_token=fcm_token[:20] + "...",
            title=title,
            note="FCM integration deferred to Phase 7",
        )
        # TODO(phase7): implement firebase_admin.messaging.send()

    async def mark_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a single notification as read. Returns True if found."""
        from sqlalchemy import select

        result = await self.db.execute(
            select(Notification).where(
                Notification.id == uuid.UUID(notification_id),
                Notification.user_id == uuid.UUID(user_id),
            )
        )
        notif = result.scalar_one_or_none()
        if not notif:
            return False

        notif.is_read = True
        notif.read_at = datetime.now(tz=UTC)
        return True

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications for user as read. Returns count updated."""
        from sqlalchemy import func, select, update

        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == uuid.UUID(user_id),
                Notification.is_read.is_(False),
            )
        )
        count = result.scalar_one()

        if count > 0:
            await self.db.execute(
                update(Notification)
                .where(
                    Notification.user_id == uuid.UUID(user_id),
                    Notification.is_read.is_(False),
                )
                .values(is_read=True, read_at=datetime.now(tz=UTC))
            )

        return count
