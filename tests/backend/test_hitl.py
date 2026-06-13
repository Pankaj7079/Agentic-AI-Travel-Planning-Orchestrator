"""
Tests for Phase 5 — Human-in-the-Loop + Notifications.

All DB calls use the real test PostgreSQL (via conftest fixtures).
WebSocket tests use mocked connections.
External services (Resend, FCM) are mocked to avoid network calls.

Test coverage:
- WebSocket ConnectionManager (connect, disconnect, send, multi-tab, dead conn pruning)
- NotificationService (WebSocket delivery, email skip, DB persistence)
- ApprovalService (create, approve, reject, expire, ownership)
- Approval API endpoints (auth guards, list, get, approve, reject)
- Notification API endpoints (list, unread count, mark read, mark all)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from sqlalchemy import select

from parikrama.api.websocket.manager import ConnectionManager
from parikrama.models.approval import ApprovalRequest
from parikrama.models.notification import Notification
from parikrama.models.user import User
from parikrama_common.enums import ApprovalStatus, TripStatus

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

# ── Helpers ────────────────────────────────────────────────────────────────────


async def _make_user(db: AsyncSession, email: str = "test@parikrama.dev") -> User:
    """Create and persist a test user."""
    user = User(
        id=uuid.uuid4(),
        email=email,
        name="Test User",
        hashed_password="$2b$12$dummy_hash_for_testing_only",
        auth_provider="local",
        is_active=True,
        is_verified=True,
        email_notifications=True,
        push_notifications=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_trip(db: AsyncSession, user_id: uuid.UUID, status: str = "planning") -> Any:
    """Create and persist a test trip."""
    from parikrama.models.trip import Trip

    trip = Trip(
        id=uuid.uuid4(),
        user_id=user_id,
        status=status,
        request={"raw_input": "Delhi to Manali 5 days"},
    )
    db.add(trip)
    await db.flush()
    return trip


async def _register_and_login(client: AsyncClient, email: str = "hitl@test.com") -> str:
    """Register a user and return the access token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "HITL Tester", "password": "Secure@123"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Secure@123"},
    )
    return resp.json()["tokens"]["access_token"]


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket ConnectionManager
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionManager:
    """Unit tests for the WebSocket ConnectionManager."""

    def test_initial_state(self):
        """Manager starts empty."""
        mgr = ConnectionManager()
        assert mgr.active_connections == 0
        assert mgr.connected_users == 0

    @pytest.mark.asyncio
    async def test_connect_accept_and_track(self):
        """connect() calls accept() and tracks the connection."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.client_state = MagicMock()

        await mgr.connect("user_1", ws)

        ws.accept.assert_called_once()
        assert mgr.active_connections == 1
        assert mgr.connected_users == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        """disconnect() removes the WebSocket and cleans up empty sets."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.client_state = MagicMock()

        await mgr.connect("user_1", ws)
        await mgr.disconnect("user_1", ws)

        assert mgr.active_connections == 0
        assert mgr.connected_users == 0

    @pytest.mark.asyncio
    async def test_multi_tab_same_user(self):
        """Multiple connections from the same user are tracked separately."""
        mgr = ConnectionManager()
        ws1, ws2 = AsyncMock(), AsyncMock()

        await mgr.connect("user_1", ws1)
        await mgr.connect("user_1", ws2)

        assert mgr.active_connections == 2
        assert mgr.connected_users == 1  # still 1 user

    @pytest.mark.asyncio
    async def test_send_to_user_delivers_message(self):
        """send_to_user sends JSON payload to connected WebSocket."""
        from starlette.websockets import WebSocketState

        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED

        await mgr.connect("user_1", ws)
        count = await mgr.send_to_user("user_1", {"type": "ping"})

        assert count == 1
        ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_to_offline_user_returns_zero(self):
        """send_to_user returns 0 when user has no active connections."""
        mgr = ConnectionManager()
        count = await mgr.send_to_user("no_one", {"type": "ping"})
        assert count == 0

    @pytest.mark.asyncio
    async def test_dead_connection_pruned_on_send(self):
        """Connections that fail on send are pruned automatically."""
        from starlette.websockets import WebSocketState

        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        ws.send_text.side_effect = RuntimeError("connection closed")

        await mgr.connect("user_1", ws)
        count = await mgr.send_to_user("user_1", {"type": "test"})

        assert count == 0
        assert mgr.active_connections == 0  # pruned

    @pytest.mark.asyncio
    async def test_broadcast_agent_update_format(self):
        """broadcast_agent_update sends correctly structured message."""
        import json

        from starlette.websockets import WebSocketState

        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED

        await mgr.connect("user_1", ws)
        await mgr.broadcast_agent_update("user_1", "trip_abc", "orchestrator", "completed", "Done")

        call_args = ws.send_text.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["type"] == "agent_update"
        assert msg["agent"] == "orchestrator"
        assert msg["trip_id"] == "trip_abc"


# ══════════════════════════════════════════════════════════════════════════════
# NotificationService
# ══════════════════════════════════════════════════════════════════════════════


class TestNotificationService:
    """Integration tests for multi-channel notification delivery."""

    @pytest.mark.asyncio
    async def test_send_persists_notification_record(self, db_session: AsyncSession):
        """NotificationService.send() persists a Notification to the DB."""
        from parikrama.services.notification_service import NotificationService

        user = await _make_user(db_session, "notif1@test.com")
        svc = NotificationService(db_session)

        with patch.object(svc, "_send_email", new_callable=AsyncMock):
            notif_id = await svc.send(
                user=user,
                notification_type="trip_update",
                title="Your itinerary is ready",
                body="5-day Manali trip planned successfully.",
                data={"trip_id": str(uuid.uuid4())},
            )

        result = await db_session.execute(
            select(Notification).where(Notification.id == uuid.UUID(notif_id))
        )
        record = result.scalar_one_or_none()
        assert record is not None
        assert record.title == "Your itinerary is ready"
        assert record.type == "trip_update"
        assert record.user_id == user.id

    @pytest.mark.asyncio
    async def test_send_websocket_when_connected(self, db_session: AsyncSession):
        """WebSocket delivery is attempted and logged in channels_sent."""
        from parikrama.api.websocket.manager import ws_manager
        from parikrama.services.notification_service import NotificationService

        user = await _make_user(db_session, "notif2@test.com")
        svc = NotificationService(db_session)

        with patch.object(ws_manager, "send_to_user", new_callable=AsyncMock, return_value=1):
            notif_id = await svc.send(
                user=user,
                notification_type="approval_required",
                title="Approval needed",
                body="Hotel costs Rs.8000/night.",
            )

        result = await db_session.execute(
            select(Notification).where(Notification.id == uuid.UUID(notif_id))
        )
        record = result.scalar_one()
        assert "websocket" in record.channels_sent

    @pytest.mark.asyncio
    async def test_email_skipped_without_api_key(self, db_session: AsyncSession):
        """Email is not attempted when RESEND_API_KEY is empty."""
        from parikrama.config import settings
        from parikrama.services.notification_service import NotificationService

        user = await _make_user(db_session, "notif3@test.com")
        svc = NotificationService(db_session)

        # Ensure no key is set
        original = settings.RESEND_API_KEY
        settings.RESEND_API_KEY = ""

        try:
            with patch.object(svc, "_send_email", new_callable=AsyncMock) as mock_email:
                await svc.send(
                    user=user,
                    notification_type="system",
                    title="Test",
                    body="Body",
                )
            mock_email.assert_not_called()
        finally:
            settings.RESEND_API_KEY = original

    @pytest.mark.asyncio
    async def test_mark_read_updates_record(self, db_session: AsyncSession):
        """mark_read() sets is_read=True and read_at timestamp."""
        from parikrama.services.notification_service import NotificationService

        user = await _make_user(db_session, "notif4@test.com")
        svc = NotificationService(db_session)

        # create a notification record directly
        notif = Notification(
            id=uuid.uuid4(),
            user_id=user.id,
            type="system",
            title="Hello",
            body="World",
            data={},
            channels_sent=[],
            is_read=False,
        )
        db_session.add(notif)
        await db_session.flush()

        found = await svc.mark_read(str(notif.id), str(user.id))
        assert found is True
        assert notif.is_read is True
        assert notif.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_count(self, db_session: AsyncSession):
        """mark_all_read() marks all unread notifications and returns count."""
        from parikrama.services.notification_service import NotificationService

        user = await _make_user(db_session, "notif5@test.com")
        svc = NotificationService(db_session)

        for i in range(3):
            db_session.add(
                Notification(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    type="system",
                    title=f"Notif {i}",
                    body="body",
                    data={},
                    channels_sent=[],
                    is_read=False,
                )
            )
        await db_session.flush()

        count = await svc.mark_all_read(str(user.id))
        assert count == 3


# ══════════════════════════════════════════════════════════════════════════════
# ApprovalService
# ══════════════════════════════════════════════════════════════════════════════


class TestApprovalService:
    """Integration tests for the approval lifecycle."""

    @pytest.mark.asyncio
    async def test_create_approval_persists_record(self, db_session: AsyncSession):
        """create_approval() creates ApprovalRequest + pauses trip."""
        from parikrama.services.approval_service import ApprovalService

        user = await _make_user(db_session, "appr1@test.com")
        trip = await _make_trip(db_session, user.id)
        svc = ApprovalService(db_session)

        with patch.object(
            svc._notification_service, "send", new_callable=AsyncMock, return_value="notif_id"
        ):
            approval_id = await svc.create_approval(
                trip_id=str(trip.id),
                user=user,
                approval_type="hotel_booking",
                title="Expensive hotel",
                description="Hotel costs Rs.8000/night.",
                payload={"hotel": "Grand Manali"},
            )

        result = await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == uuid.UUID(approval_id))
        )
        approval = result.scalar_one_or_none()
        assert approval is not None
        assert approval.status == ApprovalStatus.PENDING
        assert approval.type == "hotel_booking"

    @pytest.mark.asyncio
    async def test_approve_changes_status(self, db_session: AsyncSession):
        """approve() sets status to approved and calls pipeline resume."""
        from parikrama.services.approval_service import ApprovalService

        user = await _make_user(db_session, "appr2@test.com")
        trip = await _make_trip(db_session, user.id)
        svc = ApprovalService(db_session)

        approval = ApprovalRequest(
            id=uuid.uuid4(),
            trip_id=trip.id,
            user_id=user.id,
            type="hotel_booking",
            title="Test",
            description="Test",
            payload={},
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        db_session.add(approval)
        await db_session.flush()

        with patch.object(svc, "_resume_pipeline", new_callable=AsyncMock):
            result = await svc.approve(str(approval.id), str(user.id))

        assert result["status"] == "approved"
        assert approval.status == ApprovalStatus.APPROVED
        assert approval.responded_at is not None

    @pytest.mark.asyncio
    async def test_reject_cancels_trip(self, db_session: AsyncSession):
        """reject() sets approval to rejected and trip to cancelled."""
        from parikrama.models.trip import Trip
        from parikrama.services.approval_service import ApprovalService

        user = await _make_user(db_session, "appr3@test.com")
        trip = await _make_trip(db_session, user.id)
        svc = ApprovalService(db_session)

        approval = ApprovalRequest(
            id=uuid.uuid4(),
            trip_id=trip.id,
            user_id=user.id,
            type="hotel_booking",
            title="Test",
            description="Test",
            payload={},
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        db_session.add(approval)
        await db_session.flush()

        result = await svc.reject(str(approval.id), str(user.id), reason="too expensive")

        assert result["status"] == "rejected"
        assert approval.status == ApprovalStatus.REJECTED

        # verify trip is cancelled
        trip_result = await db_session.execute(select(Trip).where(Trip.id == trip.id))
        updated_trip = trip_result.scalar_one()
        assert updated_trip.status == TripStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_double_approve_raises_error(self, db_session: AsyncSession):
        """Approving an already-approved request raises ValueError."""
        from parikrama.services.approval_service import ApprovalService

        user = await _make_user(db_session, "appr4@test.com")
        trip = await _make_trip(db_session, user.id)
        svc = ApprovalService(db_session)

        approval = ApprovalRequest(
            id=uuid.uuid4(),
            trip_id=trip.id,
            user_id=user.id,
            type="hotel_booking",
            title="Test",
            description="Test",
            payload={},
            status=ApprovalStatus.APPROVED,
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        db_session.add(approval)
        await db_session.flush()

        with pytest.raises(ValueError, match="already approved"):
            await svc.approve(str(approval.id), str(user.id))

    @pytest.mark.asyncio
    async def test_expired_approval_raises_error(self, db_session: AsyncSession):
        """Approving an expired request raises ValueError."""
        from parikrama.services.approval_service import ApprovalService

        user = await _make_user(db_session, "appr5@test.com")
        trip = await _make_trip(db_session, user.id)
        svc = ApprovalService(db_session)

        approval = ApprovalRequest(
            id=uuid.uuid4(),
            trip_id=trip.id,
            user_id=user.id,
            type="hotel_booking",
            title="Test",
            description="Test",
            payload={},
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(tz=UTC) - timedelta(hours=2),  # already expired
        )
        db_session.add(approval)
        await db_session.flush()

        with pytest.raises(ValueError, match="expired"):
            await svc.approve(str(approval.id), str(user.id))

    @pytest.mark.asyncio
    async def test_expire_stale_marks_expired(self, db_session: AsyncSession):
        """expire_stale() marks overdue pending approvals as expired."""
        from parikrama.services.approval_service import ApprovalService

        user = await _make_user(db_session, "appr6@test.com")
        trip = await _make_trip(db_session, user.id)
        svc = ApprovalService(db_session)

        stale = ApprovalRequest(
            id=uuid.uuid4(),
            trip_id=trip.id,
            user_id=user.id,
            type="hotel_booking",
            title="Old Request",
            description="Expired",
            payload={},
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(tz=UTC) - timedelta(hours=3),  # overdue
        )
        db_session.add(stale)
        await db_session.flush()

        count = await svc.expire_stale()
        assert count >= 1
        assert stale.status == ApprovalStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_ownership_check_prevents_cross_user_access(self, db_session: AsyncSession):
        """get() raises ValueError when user_id doesn't match."""
        from parikrama.services.approval_service import ApprovalService

        owner = await _make_user(db_session, "owner@test.com")
        attacker = await _make_user(db_session, "attacker@test.com")
        trip = await _make_trip(db_session, owner.id)
        svc = ApprovalService(db_session)

        approval = ApprovalRequest(
            id=uuid.uuid4(),
            trip_id=trip.id,
            user_id=owner.id,
            type="hotel_booking",
            title="Private",
            description="Private",
            payload={},
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        db_session.add(approval)
        await db_session.flush()

        with pytest.raises(ValueError, match="not found"):
            await svc.get(str(approval.id), str(attacker.id))


# ══════════════════════════════════════════════════════════════════════════════
# Approvals API Endpoints
# ══════════════════════════════════════════════════════════════════════════════


class TestApprovalsAPI:
    """Integration tests for approval REST endpoints."""

    @pytest.mark.asyncio
    async def test_list_approvals_requires_auth(self, client: AsyncClient):
        """GET /approvals without token returns 401."""
        resp = await client.get("/api/v1/approvals")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_list_approvals_empty(self, client: AsyncClient):
        """GET /approvals returns empty list when no pending approvals."""
        token = await _register_and_login(client, "list_appr@test.com")
        resp = await client.get(
            "/api/v1/approvals",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_nonexistent_approval_returns_404(self, client: AsyncClient):
        """GET /approvals/{id} for unknown ID returns 404."""
        token = await _register_and_login(client, "get_appr@test.com")
        resp = await client.get(
            f"/api/v1/approvals/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_reject_nonexistent_returns_409(self, client: AsyncClient):
        """POST /approvals/{id}/reject for unknown ID returns 409."""
        token = await _register_and_login(client, "rej_appr@test.com")
        resp = await client.post(
            f"/api/v1/approvals/{uuid.uuid4()}/reject",
            json={"reason": "nope"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_409_CONFLICT


# ══════════════════════════════════════════════════════════════════════════════
# Notifications API Endpoints
# ══════════════════════════════════════════════════════════════════════════════


class TestNotificationsAPI:
    """Integration tests for notification inbox REST endpoints."""

    @pytest.mark.asyncio
    async def test_list_notifications_requires_auth(self, client: AsyncClient):
        """GET /notifications without token returns 401."""
        resp = await client.get("/api/v1/notifications")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_list_notifications_empty(self, client: AsyncClient):
        """GET /notifications returns empty for new user."""
        token = await _register_and_login(client, "notif_api1@test.com")
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["notifications"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_unread_count_zero_for_new_user(self, client: AsyncClient):
        """GET /notifications/unread-count returns 0 for new user."""
        token = await _register_and_login(client, "notif_api2@test.com")
        resp = await client.get(
            "/api/v1/notifications/unread-count",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["unread_count"] == 0

    @pytest.mark.asyncio
    async def test_mark_nonexistent_notification_returns_404(self, client: AsyncClient):
        """PATCH /notifications/{id}/read for unknown ID returns 404."""
        token = await _register_and_login(client, "notif_api3@test.com")
        resp = await client.patch(
            f"/api/v1/notifications/{uuid.uuid4()}/read",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_ok(self, client: AsyncClient):
        """POST /notifications/read-all returns ok with 0 when nothing unread."""
        token = await _register_and_login(client, "notif_api4@test.com")
        resp = await client.post(
            "/api/v1/notifications/read-all",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "ok"
        assert resp.json()["marked_read"] == 0
