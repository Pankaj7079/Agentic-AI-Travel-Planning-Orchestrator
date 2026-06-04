# Phase 5: Human-in-the-Loop + Notifications

## Overview

Phase 5 adds the **safety net** — the ability for the system to pause and ask the user before taking expensive or irreversible actions. When the Booking Agent finds a hotel that costs 60% of the budget, or when a train ticket needs actual booking, the system stops, notifies the user across all channels, waits for approval, and resumes exactly where it left off.

### What This Phase Delivers
- **LangGraph interrupt mechanism** — agents pause at approval checkpoints
- **Multi-channel notifications** — WebSocket (instant), Email (Resend), Push (FCM)
- **Approval/rejection handling** — user can approve, reject, or modify
- **State persistence and resume** — graph continues from exactly where it paused
- **Timeout handling** — auto-cancel unanswered approvals after 1 hour

---

## Architecture Decisions

### Decision 1: LangGraph interrupt_before vs Custom Polling
**Why LangGraph interrupts:** Built-in `interrupt_before` suspends graph execution at a node boundary and persists state to the checkpointer. When the user approves, we call `graph.ainvoke()` with the same thread_id and it resumes from the exact checkpoint. No custom state machine needed.

### Decision 2: Notification Channels
| Channel | Latency | Reliability | Use Case |
|---------|---------|-------------|----------|
| **WebSocket** | Instant | Session-dependent | User is in the app |
| **Email (Resend)** | 1-5 seconds | High | User left the app |
| **Push (FCM)** | 1-3 seconds | Medium | Mobile users |

**Why all three:** Users can't be expected to stare at the app. If they close the tab, WebSocket notifications are lost. Email ensures they see it eventually. Push brings them back to the app immediately.

---

## Database Schema

```sql
-- ══════════════════════════════════════════════════════════════════════
-- Phase 5 Database Tables
-- ══════════════════════════════════════════════════════════════════════

-- ── Approval Requests ──────────────────────────────────────────────
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(30) NOT NULL,            -- 'hotel_booking', 'transport_booking', 'budget_exceed'
    title VARCHAR(255) NOT NULL,
    description TEXT,
    payload JSONB NOT NULL DEFAULT '{}',  -- details of what needs approval
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending → approved | rejected | expired
    user_response JSONB,                  -- modifications the user made
    expires_at TIMESTAMPTZ NOT NULL,
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_approvals_user ON approval_requests(user_id);
CREATE INDEX idx_approvals_trip ON approval_requests(trip_id);
CREATE INDEX idx_approvals_status ON approval_requests(status);
CREATE INDEX idx_approvals_expires ON approval_requests(expires_at) WHERE status = 'pending';

-- ── Notifications ──────────────────────────────────────────────────
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(30) NOT NULL,            -- from NotificationType enum
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',     -- extra payload (trip_id, approval_id, etc.)
    channels_sent TEXT[] DEFAULT '{}',    -- ['websocket', 'email', 'push']
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_notifications_unread ON notifications(user_id, is_read) WHERE is_read = FALSE;
```

---

## Key APIs

```
POST   /api/v1/approvals/{id}/approve       Approve a pending request
POST   /api/v1/approvals/{id}/reject        Reject a pending request
GET    /api/v1/approvals                     List user's pending approvals
GET    /api/v1/approvals/{id}                Get approval details

GET    /api/v1/notifications                 List notifications (paginated)
PATCH  /api/v1/notifications/{id}/read       Mark notification as read
POST   /api/v1/notifications/read-all        Mark all as read
GET    /api/v1/notifications/unread-count     Count unread notifications

WS     /ws/{user_id}                         WebSocket connection for real-time updates
```

---

## Implementation

### WebSocket Connection Manager

```python
# apps/backend/src/parikrama/api/websocket/manager.py
"""
WebSocket connection manager for real-time agent updates.

Manages connections per user — supports multiple tabs/devices.
Broadcasts messages to all connections for a given user.
"""
import asyncio
import json

import structlog
from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = structlog.get_logger()


class ConnectionManager:
    """Manage active WebSocket connections per user."""

    def __init__(self) -> None:
        # user_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection for a user."""
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
        logger.info("ws_connected", user_id=user_id, total=len(self._connections.get(user_id, set())))

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
        logger.info("ws_disconnected", user_id=user_id)

    async def send_to_user(self, user_id: str, message: dict) -> int:
        """
        Send a message to all connections for a user.
        Returns number of successfully sent messages.
        """
        connections = self._connections.get(user_id, set()).copy()
        if not connections:
            return 0

        sent = 0
        failed = []
        payload = json.dumps(message)

        for ws in connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(payload)
                    sent += 1
                else:
                    failed.append(ws)
            except Exception:
                failed.append(ws)

        # cleanup dead connections
        if failed:
            async with self._lock:
                for ws in failed:
                    self._connections.get(user_id, set()).discard(ws)

        return sent

    async def broadcast_agent_update(
        self, user_id: str, trip_id: str, agent: str, status: str, message: str,
    ) -> None:
        """Broadcast an agent progress update to the user."""
        await self.send_to_user(user_id, {
            "type": "agent_update",
            "trip_id": trip_id,
            "agent": agent,
            "status": status,
            "message": message,
        })

    async def broadcast_approval_request(
        self, user_id: str, approval_id: str, title: str, payload: dict,
    ) -> None:
        """Send an approval request card to the user."""
        await self.send_to_user(user_id, {
            "type": "approval_request",
            "approval_id": approval_id,
            "title": title,
            "payload": payload,
        })

    @property
    def active_connections(self) -> int:
        """Total active connections across all users."""
        return sum(len(conns) for conns in self._connections.values())


# singleton — shared across the application
ws_manager = ConnectionManager()
```

### Notification Service

```python
# apps/backend/src/parikrama/services/notification_service.py
"""
Multi-channel notification delivery.

Sends notifications via WebSocket (instant), Email (Resend), and Push (FCM).
Respects user preferences — some users opt out of email or push.
"""
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.api.websocket.manager import ws_manager
from parikrama.config import settings
from parikrama.models.notification import Notification
from parikrama.models.user import User
from parikrama_common.enums import NotificationType

logger = structlog.get_logger()


class NotificationService:
    """Deliver notifications across all enabled channels."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def send(
        self,
        user: User,
        type: NotificationType,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> str:
        """
        Send notification to a user via all enabled channels.
        Returns the notification ID.
        """
        notification_id = str(uuid.uuid4())
        channels_sent = []

        # channel 1: WebSocket (always attempted)
        ws_sent = await ws_manager.send_to_user(
            str(user.id),
            {
                "type": "notification",
                "notification_id": notification_id,
                "notification_type": type.value,
                "title": title,
                "body": body,
                "data": data or {},
            },
        )
        if ws_sent > 0:
            channels_sent.append("websocket")

        # channel 2: Email (if user enabled and we have Resend configured)
        if user.email_notifications and settings.RESEND_API_KEY:
            try:
                await self._send_email(user.email, title, body, data)
                channels_sent.append("email")
            except Exception as e:
                logger.error("email_notification_failed", user_id=str(user.id), error=str(e))

        # channel 3: Push (if user has FCM token and enabled)
        if user.push_notifications and user.fcm_token:
            try:
                await self._send_push(user.fcm_token, title, body, data)
                channels_sent.append("push")
            except Exception as e:
                logger.error("push_notification_failed", user_id=str(user.id), error=str(e))

        # persist notification record
        notification = Notification(
            id=uuid.UUID(notification_id),
            user_id=user.id,
            type=type.value,
            title=title,
            body=body,
            data=data or {},
            channels_sent=channels_sent,
        )
        self.db.add(notification)

        logger.info(
            "notification_sent",
            notification_id=notification_id,
            user_id=str(user.id),
            type=type.value,
            channels=channels_sent,
        )

        return notification_id

    async def _send_email(self, to_email: str, title: str, body: str, data: dict | None) -> None:
        """Send email notification via Resend."""
        import resend
        resend.api_key = settings.RESEND_API_KEY

        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to_email],
            "subject": f"PariKrama: {title}",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #4F46E5;">{title}</h2>
                <p>{body}</p>
                <hr>
                <p style="color: #666; font-size: 12px;">
                    You're receiving this from PariKrama Travel Planner.
                    <a href="http://localhost:3000/settings">Manage preferences</a>
                </p>
            </div>
            """,
        })

    async def _send_push(self, fcm_token: str, title: str, body: str, data: dict | None) -> None:
        """Send push notification via Firebase Cloud Messaging."""
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=fcm_token,
        )
        messaging.send(message)
```

### Approval Service

```python
# apps/backend/src/parikrama/services/approval_service.py
"""
Manages the approval lifecycle — create, respond, expire, resume.

Connects the LangGraph interrupt mechanism to the notification system.
When an agent pauses for approval, this service handles the entire flow.
"""
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.models.approval import ApprovalRequest
from parikrama.models.trip import Trip
from parikrama.models.user import User
from parikrama.services.notification_service import NotificationService
from parikrama_common.enums import ApprovalStatus, NotificationType, TripStatus

logger = structlog.get_logger()

# approval expires after 1 hour
APPROVAL_TIMEOUT_HOURS = 1


class ApprovalService:
    """Handle human-in-the-loop approval workflows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.notification_service = NotificationService(db)

    async def create_approval(
        self,
        trip_id: str,
        user: User,
        approval_type: str,
        title: str,
        description: str,
        payload: dict,
    ) -> str:
        """
        Create an approval request and notify the user.
        Returns the approval request ID.
        """
        approval_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=APPROVAL_TIMEOUT_HOURS)

        approval = ApprovalRequest(
            id=uuid.UUID(approval_id),
            trip_id=uuid.UUID(trip_id),
            user_id=user.id,
            type=approval_type,
            title=title,
            description=description,
            payload=payload,
            status=ApprovalStatus.PENDING,
            expires_at=expires_at,
        )
        self.db.add(approval)

        # update trip status
        await self.db.execute(
            update(Trip)
            .where(Trip.id == uuid.UUID(trip_id))
            .values(status=TripStatus.AWAITING_APPROVAL)
        )

        # notify user across all channels
        await self.notification_service.send(
            user=user,
            type=NotificationType.APPROVAL_REQUIRED,
            title=f"Approval Needed: {title}",
            body=description,
            data={"trip_id": trip_id, "approval_id": approval_id},
        )

        logger.info(
            "approval_created",
            approval_id=approval_id,
            trip_id=trip_id,
            type=approval_type,
            expires_at=expires_at.isoformat(),
        )

        return approval_id

    async def approve(self, approval_id: str, user_id: str, modifications: dict | None = None) -> dict:
        """Approve a pending request and resume the agent pipeline."""
        approval = await self._get_approval(approval_id, user_id)

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval already {approval.status}")

        if approval.expires_at < datetime.now(timezone.utc):
            approval.status = ApprovalStatus.EXPIRED
            raise ValueError("Approval has expired")

        approval.status = ApprovalStatus.APPROVED
        approval.responded_at = datetime.now(timezone.utc)
        approval.user_response = modifications or {"action": "approved_as_is"}

        # resume the LangGraph pipeline
        await self._resume_pipeline(str(approval.trip_id), {
            "approved": True,
            "modifications": modifications,
        })

        logger.info("approval_approved", approval_id=approval_id)
        return {"status": "approved", "trip_id": str(approval.trip_id)}

    async def reject(self, approval_id: str, user_id: str, reason: str = "") -> dict:
        """Reject a pending request and cancel the trip."""
        approval = await self._get_approval(approval_id, user_id)

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval already {approval.status}")

        approval.status = ApprovalStatus.REJECTED
        approval.responded_at = datetime.now(timezone.utc)
        approval.user_response = {"action": "rejected", "reason": reason}

        # update trip status to cancelled
        await self.db.execute(
            update(Trip)
            .where(Trip.id == approval.trip_id)
            .values(status=TripStatus.CANCELLED)
        )

        logger.info("approval_rejected", approval_id=approval_id, reason=reason)
        return {"status": "rejected", "trip_id": str(approval.trip_id)}

    async def _get_approval(self, approval_id: str, user_id: str) -> ApprovalRequest:
        """Fetch approval and verify ownership."""
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == uuid.UUID(approval_id),
                ApprovalRequest.user_id == uuid.UUID(user_id),
            )
        )
        approval = result.scalar_one_or_none()
        if not approval:
            raise ValueError("Approval not found")
        return approval

    async def _resume_pipeline(self, trip_id: str, approval_response: dict) -> None:
        """Resume the LangGraph pipeline after approval."""
        from parikrama.agents.graph import build_trip_graph

        result = await self.db.execute(
            select(Trip).where(Trip.id == uuid.UUID(trip_id))
        )
        trip = result.scalar_one()

        graph = await build_trip_graph(self.db)
        config = {"configurable": {"thread_id": trip.thread_id}}

        # resume with approval data injected into state
        await graph.ainvoke(
            {"approval_response": approval_response},
            config=config,
        )

        logger.info("pipeline_resumed", trip_id=trip_id)
```

### Celery Task for Approval Timeout

```python
# apps/worker/src/parikrama_worker/tasks/cleanup_tasks.py
"""
Scheduled tasks for approval timeout and cleanup.

Runs every 5 minutes via Celery Beat.
Expires unanswered approvals and cancels their associated trips.
"""
from datetime import datetime, timezone

import structlog
from celery import shared_task
from sqlalchemy import select, update

logger = structlog.get_logger()


@shared_task(name="expire_pending_approvals")
def expire_pending_approvals() -> dict:
    """Expire approval requests that have passed their deadline."""
    from parikrama_worker.config import get_sync_session

    db = get_sync_session()
    try:
        from parikrama.models.approval import ApprovalRequest
        from parikrama.models.trip import Trip
        from parikrama_common.enums import ApprovalStatus, TripStatus

        now = datetime.now(timezone.utc)

        # find expired approvals
        result = db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.expires_at < now,
            )
        )
        expired = result.scalars().all()

        count = 0
        for approval in expired:
            approval.status = ApprovalStatus.EXPIRED
            approval.responded_at = now

            # cancel the associated trip
            db.execute(
                update(Trip)
                .where(Trip.id == approval.trip_id)
                .values(status=TripStatus.CANCELLED)
            )
            count += 1

        db.commit()
        if count > 0:
            logger.info("approvals_expired", count=count)

        return {"expired_count": count}
    finally:
        db.close()
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| WebSocket connect/disconnect | Unit | Connection tracking works |
| Send to offline user | Unit | Returns 0, no crash |
| Approval creation sends notifications | Integration | All channels attempted |
| Approve resumes pipeline | Integration | Graph continues from checkpoint |
| Reject cancels trip | Integration | Trip status set to cancelled |
| Expired approval auto-expires | Integration | Celery task updates status |
| Multi-tab WebSocket | Unit | Multiple connections per user |

---

## Definition of Done — Phase 5

- [ ] WebSocket connection manager handles multi-tab users
- [ ] Approval requests stored with expiration timestamp
- [ ] Approve endpoint resumes LangGraph pipeline
- [ ] Reject endpoint cancels trip
- [ ] Email notifications sent via Resend
- [ ] Push notifications sent via FCM
- [ ] User notification preferences respected
- [ ] Celery Beat task expires pending approvals every 5 minutes
- [ ] Notification history persisted and queryable
- [ ] Unread count endpoint works
- [ ] LangGraph `interrupt_before` pauses at booking confirmation

## Common Pitfalls

| Pitfall | How to Avoid |
|---------|-------------|
| **WebSocket drops silently** | Implement heartbeat ping/pong every 30s |
| **Resend rate limits** | Free tier: 3000/month. Queue emails, don't spam |
| **FCM token stale** | Handle token refresh on the frontend |
| **Approval race condition** | Use database-level status check, not in-memory |
| **Graph resume fails** | Ensure thread_id matches exactly, checkpointer is same instance |

---

*Phase 5 ensures the system never takes expensive actions without user consent. This is critical for trust and for future payment integrations.*
