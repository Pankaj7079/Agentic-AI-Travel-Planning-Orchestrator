"""
ApprovalService — manages the HITL approval lifecycle.

Flow:
1. Agent calls create_approval() when it hits a decision gate
2. User receives notification via all channels
3. User calls approve() or reject() via API
4. approve() resumes the trip planning pipeline
5. reject() cancels the trip
6. Celery Beat calls expire_stale() every 5 minutes to auto-expire old requests

Design notes:
- Status transitions are validated at the DB level (no double-approve possible)
- Expiry check at approval time prevents stale approvals from resuming pipelines
- On approve, the graph is re-invoked with approval_response injected into state;
  completed steps short-circuit via conditional logic (no LangGraph checkpointer needed)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, update

from parikrama.models.approval import ApprovalRequest
from parikrama.models.trip import Trip
from parikrama.services.notification_service import NotificationService
from parikrama_common.enums import ApprovalStatus, TripStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.models.user import User

logger = structlog.get_logger(__name__)

APPROVAL_TIMEOUT_HOURS = 1  # auto-expire after 1 hour


class ApprovalService:
    """Handle human-in-the-loop approval workflows end to end."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._notification_service = NotificationService(db)

    # ── Create ─────────────────────────────────────────────────────────────────

    async def create_approval(
        self,
        trip_id: str,
        user: User,
        approval_type: str,
        title: str,
        description: str,
        payload: dict[str, Any],
    ) -> str:
        """
        Create an approval request and notify the user across all channels.

        Args:
            trip_id: UUID string of the trip being planned.
            user: The authenticated user ORM object.
            approval_type: Category string ('hotel_booking', 'transport_booking', 'budget_exceed').
            title: Short summary for notification heading.
            description: Full description shown to the user.
            payload: Structured data (options, prices) for the UI to render.

        Returns:
            approval_id UUID string.
        """
        approval_id = str(uuid.uuid4())
        expires_at = datetime.now(tz=UTC) + timedelta(hours=APPROVAL_TIMEOUT_HOURS)

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

        # pause the trip
        await self.db.execute(
            update(Trip)
            .where(Trip.id == uuid.UUID(trip_id))
            .values(status=TripStatus.AWAITING_APPROVAL)
        )

        # broadcast to all channels
        await self._notification_service.send(
            user=user,
            notification_type="approval_required",
            title=f"Action Required: {title}",
            body=description,
            data={
                "trip_id": trip_id,
                "approval_id": approval_id,
                "approval_type": approval_type,
            },
        )

        await self.db.flush()

        logger.info(
            "approval_created",
            approval_id=approval_id,
            trip_id=trip_id,
            type=approval_type,
            expires_at=expires_at.isoformat(),
        )
        return approval_id

    # ── Respond ────────────────────────────────────────────────────────────────

    async def approve(
        self,
        approval_id: str,
        user_id: str,
        modifications: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Approve a pending request and resume the agent pipeline.

        Args:
            approval_id: UUID string of the approval record.
            user_id: Authenticated user UUID (authorization check).
            modifications: Optional changes the user wants to apply.

        Returns:
            Dict with status, trip_id, and message.

        Raises:
            ValueError: If not found, already responded, or expired.
        """
        approval = await self._get_approval(approval_id, user_id)
        self._assert_pending(approval)

        approval.status = ApprovalStatus.APPROVED
        approval.responded_at = datetime.now(tz=UTC)
        approval.user_response = modifications or {"action": "approved_as_is"}

        # resume the pipeline
        await self._resume_pipeline(
            trip_id=str(approval.trip_id),
            approval_response={"approved": True, "modifications": modifications or {}},
        )

        await self.db.flush()
        logger.info("approval_approved", approval_id=approval_id)

        return {
            "status": "approved",
            "trip_id": str(approval.trip_id),
            "message": "Pipeline resumed. Your itinerary will be ready shortly.",
        }

    async def reject(
        self,
        approval_id: str,
        user_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """
        Reject a pending request and cancel the trip.

        Args:
            approval_id: UUID string of the approval record.
            user_id: Authenticated user UUID.
            reason: Optional reason shown in logs.

        Returns:
            Dict with status and trip_id.
        """
        approval = await self._get_approval(approval_id, user_id)
        self._assert_pending(approval)

        approval.status = ApprovalStatus.REJECTED
        approval.responded_at = datetime.now(tz=UTC)
        approval.user_response = {"action": "rejected", "reason": reason}

        await self.db.execute(
            update(Trip).where(Trip.id == approval.trip_id).values(status=TripStatus.CANCELLED)
        )

        await self.db.flush()
        logger.info("approval_rejected", approval_id=approval_id, reason=reason)

        return {
            "status": "rejected",
            "trip_id": str(approval.trip_id),
            "message": "Trip planning cancelled.",
        }

    # ── Query ──────────────────────────────────────────────────────────────────

    async def list_pending(self, user_id: str) -> list[dict[str, Any]]:
        """Return all pending approval requests for a user."""
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.user_id == uuid.UUID(user_id),
                ApprovalRequest.status == ApprovalStatus.PENDING,
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
        return [self._serialize(a) for a in result.scalars().all()]

    async def get(self, approval_id: str, user_id: str) -> dict[str, Any]:
        """Get a single approval request (any status)."""
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == uuid.UUID(approval_id),
                ApprovalRequest.user_id == uuid.UUID(user_id),
            )
        )
        approval = result.scalar_one_or_none()
        if not approval:
            raise ValueError(f"Approval {approval_id} not found")
        return self._serialize(approval)

    # ── Expiry (called by Celery Beat) ─────────────────────────────────────────

    async def expire_stale(self) -> int:
        """
        Mark overdue pending approvals as expired and cancel their trips.

        Called by Celery Beat every 5 minutes.
        Returns count of approvals expired.
        """
        now = datetime.now(tz=UTC)
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == ApprovalStatus.PENDING,
                ApprovalRequest.expires_at < now,
            )
        )
        stale = result.scalars().all()
        count = 0

        for approval in stale:
            approval.status = ApprovalStatus.EXPIRED
            approval.responded_at = now
            await self.db.execute(
                update(Trip).where(Trip.id == approval.trip_id).values(status=TripStatus.CANCELLED)
            )
            count += 1

        if count > 0:
            await self.db.flush()
            logger.info("approvals_expired", count=count)

        return count

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_approval(self, approval_id: str, user_id: str) -> ApprovalRequest:
        """Fetch approval and verify user ownership."""
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == uuid.UUID(approval_id),
                ApprovalRequest.user_id == uuid.UUID(user_id),
            )
        )
        approval = result.scalar_one_or_none()
        if not approval:
            raise ValueError(f"Approval {approval_id} not found or access denied")
        return approval

    def _assert_pending(self, approval: ApprovalRequest) -> None:
        """Raise if the approval is not in pending state or has expired."""
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval already {approval.status} — cannot respond again")
        if approval.expires_at < datetime.now(tz=UTC):
            approval.status = ApprovalStatus.EXPIRED
            raise ValueError("Approval has expired — the 1-hour window has passed")

    async def _resume_pipeline(self, trip_id: str, approval_response: dict[str, Any]) -> None:
        """
        Re-invoke the LangGraph trip planning pipeline with approval context.
        Dispatches as a background asyncio task so approve() returns quickly.
        """
        from parikrama.services.async_planner import run_planning_background

        result = await self.db.execute(select(Trip).where(Trip.id == uuid.UUID(trip_id)))
        trip = result.scalar_one_or_none()
        if not trip:
            logger.error("resume_pipeline_trip_not_found", trip_id=trip_id)
            return

        raw_input = (trip.request or {}).get("raw_input", "")
        user_id = str(trip.user_id)

        # Update trip status back to planning
        trip.status = "planning"
        await self.db.flush()

        # Dispatch background planning — run_planning_background creates its
        # own DB session, so it is fully decoupled from this request's session.
        import asyncio

        async def _safe_resume() -> None:
            """Wrapper that catches and logs any errors from the resumed pipeline."""
            try:
                await run_planning_background(
                    trip_id=trip_id,
                    user_id=user_id,
                    raw_input=raw_input,
                    approval_response=approval_response,
                )
            except Exception as exc:
                logger.error(
                    "pipeline_resume_failed",
                    trip_id=trip_id,
                    error=str(exc),
                    exc_info=True,
                )
                # Mark trip as failed so user sees the error
                try:
                    from parikrama.db.session import async_session_factory

                    async with async_session_factory() as err_db:
                        from sqlalchemy import select as sa_select

                        res = await err_db.execute(
                            sa_select(Trip).where(Trip.id == uuid.UUID(trip_id))
                        )
                        trip_rec = res.scalar_one_or_none()
                        if trip_rec:
                            trip_rec.status = "failed"
                            trip_rec.result = {"error": f"Pipeline resume failed: {exc}"}
                            await err_db.commit()
                except Exception:
                    pass

        _resume_task = asyncio.create_task(_safe_resume())
        logger.info("pipeline_resume_dispatched", trip_id=trip_id, task_id=id(_resume_task))

    @staticmethod
    def _serialize(approval: ApprovalRequest) -> dict[str, Any]:
        """Serialize an ApprovalRequest to a JSON-safe dict."""
        return {
            "id": str(approval.id),
            "trip_id": str(approval.trip_id),
            "type": approval.type,
            "title": approval.title,
            "description": approval.description,
            "payload": approval.payload,
            "status": approval.status,
            "user_response": approval.user_response,
            "expires_at": approval.expires_at.isoformat(),
            "responded_at": approval.responded_at.isoformat() if approval.responded_at else None,
            "created_at": approval.created_at.isoformat(),
        }
