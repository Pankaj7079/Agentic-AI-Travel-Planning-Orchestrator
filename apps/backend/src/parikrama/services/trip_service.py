"""
Trip service — business logic for trip creation, retrieval, and status management.

Actual LangGraph orchestration wired in Phase 4.
Phase 1 provides the CRUD layer and async task dispatch pattern.
"""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.exceptions import ForbiddenError, NotFoundError
from parikrama.models.trip import AgentRun, Trip
from parikrama.schemas.trip import (
    AgentRunResponse,
    CreateTripRequest,
    TripDetailResponse,
    TripResponse,
)

logger = structlog.get_logger()


class TripService:
    """Handles trip lifecycle — create, retrieve, list, cancel."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_trip(self, user_id: str, request: CreateTripRequest) -> TripResponse:
        """
        Create a new trip planning session.

        The actual LangGraph orchestration will be triggered by a
        Celery task (Phase 4). For now, we create the record and
        set status to 'pending'.
        """
        trip = Trip(
            user_id=uuid.UUID(user_id),
            status="pending",
            request={
                "origin": request.origin,
                "destination": request.destination,
                "days": request.days,
                "budget_inr": request.budget_inr,
                "travelers": request.travelers,
                "start_date": request.start_date,
                "preferences": request.preferences.model_dump(),
            },
            thread_id=str(uuid.uuid4()),
        )
        self.db.add(trip)
        await self.db.flush()

        logger.info(
            "trip_created",
            trip_id=str(trip.id),
            user_id=user_id,
            origin=request.origin,
            destination=request.destination,
            budget=request.budget_inr,
        )

        # TODO Phase 4: dispatch LangGraph orchestration
        # from parikrama_worker.tasks.trip_tasks import run_trip_planning
        # run_trip_planning.delay(str(trip.id))

        return TripResponse.model_validate(trip)

    async def get_trip(self, trip_id: str, user_id: str) -> TripDetailResponse:
        """Get a trip with full agent run history."""
        trip = await self._get_trip_owned_by(trip_id, user_id)

        # load agent runs
        runs_result = await self.db.execute(
            select(AgentRun).where(AgentRun.trip_id == trip.id).order_by(AgentRun.created_at)
        )
        agent_runs = runs_result.scalars().all()

        response = TripDetailResponse.model_validate(trip)
        response.agent_runs = [AgentRunResponse.model_validate(r).model_dump() for r in agent_runs]
        return response

    async def list_trips(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> dict:
        """List all trips for a user with pagination."""
        query = select(Trip).where(Trip.user_id == uuid.UUID(user_id))

        if status:
            query = query.where(Trip.status == status)

        # total count
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()

        # paginated results
        trips_result = await self.db.execute(
            query.order_by(Trip.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        trips = trips_result.scalars().all()

        return {
            "items": [TripResponse.model_validate(t) for t in trips],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),  # ceiling division
        }

    async def cancel_trip(self, trip_id: str, user_id: str) -> TripResponse:
        """Cancel a pending or planning trip."""
        trip = await self._get_trip_owned_by(trip_id, user_id)

        if trip.status not in ("pending", "planning"):
            raise ValueError(
                f"Cannot cancel trip in '{trip.status}' status. "
                "Only pending or planning trips can be cancelled."
            )

        trip.status = "cancelled"
        await self.db.flush()
        await self.db.refresh(trip)

        logger.info("trip_cancelled", trip_id=trip_id, user_id=user_id)
        return TripResponse.model_validate(trip)

    async def get_trip_status(self, trip_id: str, user_id: str) -> dict:
        """Get current planning status for WebSocket / polling."""
        trip = await self._get_trip_owned_by(trip_id, user_id)

        # get latest agent run
        runs_result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.trip_id == trip.id)
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
        latest_run = runs_result.scalar_one_or_none()

        # calculate progress based on status
        progress_map = {
            "pending": 5,
            "planning": 40,
            "awaiting_approval": 75,
            "approved": 90,
            "completed": 100,
            "failed": 0,
            "cancelled": 0,
        }

        # Look for pending approval id
        approval_id = None
        if trip.status == "awaiting_approval":
            from parikrama.models.approval import ApprovalRequest

            approvals_result = await self.db.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.trip_id == trip.id,
                    ApprovalRequest.status == "pending",
                )
                .order_by(ApprovalRequest.created_at.desc())
                .limit(1)
            )
            approval = approvals_result.scalar_one_or_none()
            if approval:
                approval_id = str(approval.id)

        return {
            "trip_id": str(trip.id),
            "status": trip.status,
            "current_agent": latest_run.agent_name if latest_run else None,
            "progress_percent": progress_map.get(trip.status, 0),
            "message": _status_message(trip.status, latest_run),
            "is_complete": trip.status in ("completed", "failed", "cancelled", "awaiting_approval"),
            "approval_id": approval_id,
            "has_result": bool(trip.result and trip.result.get("itinerary")),
            "error": _extract_error(trip),
        }

    # ── Private helpers ───────────────────────────────────────────────

    async def _get_trip_owned_by(self, trip_id: str, user_id: str) -> Trip:
        """Get trip, raising 404 if not found or 403 if not owned by user."""
        result = await self.db.execute(select(Trip).where(Trip.id == uuid.UUID(trip_id)))
        trip = result.scalar_one_or_none()

        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")

        if str(trip.user_id) != user_id:
            raise ForbiddenError("You don't have access to this trip")

        return trip


def _status_message(status: str, latest_run: AgentRun | None) -> str:
    """Human-readable status message for the frontend."""
    messages = {
        "pending": "Your trip is queued for planning...",
        "planning": f"Planning in progress — {latest_run.agent_name if latest_run else 'initializing'}...",
        "awaiting_approval": "Waiting for your approval on the plan",
        "approved": "Finalizing your itinerary...",
        "completed": "Your trip plan is ready! 🎉",
        "failed": "Planning failed. Please try again.",
        "cancelled": "Trip cancelled.",
    }
    return messages.get(status, "Processing...")


def _extract_error(trip: Trip) -> str | None:
    """Extract user-friendly error message from trip result."""
    if trip.status != "failed":
        return None
    result = trip.result or {}
    error = result.get("error", "")
    if not error:
        return "An unexpected error occurred during planning."
    # Make error user-friendly — strip technical details
    if "Invalid trip request:" in error:
        return error.replace("Invalid trip request: ", "")
    if "Could not determine" in error:
        return f"Could not parse your request: {error}"
    if "timeout" in error.lower():
        return "The planning service timed out. Please try again with a simpler request."
    if "LLM" in error or "gemini" in error.lower() or "groq" in error.lower():
        return "AI service temporarily unavailable. Please try again in a moment."
    # For other errors, return a sanitized version (max 200 chars)
    return error[:200] if len(error) > 200 else error
