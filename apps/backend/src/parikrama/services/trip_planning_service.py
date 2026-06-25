"""
TripPlanningService — connects the API layer to the LangGraph pipeline.

Responsibilities:
1. Create/update Trip and AgentRun DB records
2. Build and invoke the LangGraph with the right initial state
3. Persist results back to the Trip record
4. Emit per-agent run records for observability

This service is the single point of truth for trip lifecycle management.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from parikrama.agents.trip_graph import build_trip_planning_graph
from parikrama.models.trip import AgentRun, Trip
from parikrama.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.agents.trip_state import TripPlanningState
    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)


class TripPlanningService:
    """Manages trip planning lifecycle: DB records → LangGraph → results."""

    def __init__(self, db: AsyncSession, llm_router: LLMRouter) -> None:
        self.db = db
        self.llm_router = llm_router

    async def run_planning(self, trip_id: str, user_id: str, raw_input: str) -> dict[str, Any]:
        """
        Execute the full multi-agent planning pipeline for a trip.

        Args:
            trip_id: UUID of an existing Trip record (status must be "pending").
            user_id: Authenticated user UUID string.
            raw_input: Natural language trip request.

        Returns:
            Dict with trip_id, status, result, duration_ms.

        Raises:
            ValueError: If trip not found or not in pending/planning status.
            RuntimeError: If the planning pipeline fails critically.
        """
        log = logger.bind(trip_id=trip_id, user_id=user_id)
        log.info("trip_planning_started", raw_input=raw_input[:80])

        # Validate trip exists and belongs to user
        trip = await self._get_trip(trip_id, user_id)

        # Mark trip as planning
        trip.status = "planning"
        trip.request = {**(trip.request or {}), "raw_input": raw_input}
        await self.db.flush()

        # Build initial state
        initial_state: TripPlanningState = {
            "trip_id": trip_id,
            "user_id": user_id,
            "raw_input": raw_input,
            "request": {},
            "weather": None,
            "destination_info": "",
            "reviews_summary": "",
            "places_of_interest": [],
            "hotel_options": [],
            "transport_options": [],
            "requires_approval": False,
            "budget_breakdown": None,
            "is_within_budget": True,
            "itinerary": [],
            "summary": "",
            "current_agent": "",
            "messages": [],
            "errors": [],
            "status": "planning",
            "approval_response": None,
            "_budget_retries": 0,
        }

        start_time = time.perf_counter()

        try:
            graph = build_trip_planning_graph(self.llm_router, self.db)
            final_state = await graph.ainvoke(initial_state)
        except Exception as exc:
            log.error("trip_planning_pipeline_failed", error=str(exc))
            trip.status = "failed"
            await self.db.flush()
            raise RuntimeError(f"Trip planning failed: {exc}") from exc

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # ── HITL gate: approval required before proceeding ──────────────────
        if final_state.get("requires_approval", False):
            # persist intermediate result so resume can access it
            trip.result = {
                "request": final_state.get("request", {}),
                "hotel_options": final_state.get("hotel_options", []),
                "transport_options": final_state.get("transport_options", []),
                "weather": final_state.get("weather"),
                "places_of_interest": final_state.get("places_of_interest", []),
                "destination_info": final_state.get("destination_info", ""),
                "reviews_summary": final_state.get("reviews_summary", ""),
            }
            await self.db.flush()

            # fetch the user object for notifications
            from sqlalchemy import select

            user_result = await self.db.execute(select(User).where(User.id == uuid.UUID(user_id)))
            user = user_result.scalar_one()

            # create approval and notify user
            from parikrama.services.approval_service import ApprovalService

            approval_svc = ApprovalService(self.db)
            hotels = final_state.get("hotel_options", [])
            budget = (final_state.get("request") or {}).get("budget_inr", 0)
            top_hotel = hotels[0] if hotels else {}
            approval_id = await approval_svc.create_approval(
                trip_id=trip_id,
                user=user,
                approval_type="hotel_booking",
                title="Hotel exceeds 50% of your budget",
                description=(
                    f"{top_hotel.get('name', 'Selected hotel')} costs "
                    f"Rs.{top_hotel.get('price_per_night_inr', 0)}/night. "
                    f"Your total budget is Rs.{budget}. Approve to continue planning."
                ),
                payload={
                    "hotel_options": hotels[:3],
                    "transport_options": final_state.get("transport_options", [])[:3],
                    "budget_inr": budget,
                },
            )
            await self.db.flush()

            log.info("trip_awaiting_approval", trip_id=trip_id, approval_id=approval_id)
            return {
                "trip_id": trip_id,
                "status": "awaiting_approval",
                "approval_id": approval_id,
                "message": "Approval required before finalising itinerary.",
                "duration_ms": duration_ms,
                "errors": final_state.get("errors", []),
            }

        # Persist agent run records for observability
        await self._persist_agent_runs(trip_id, final_state, duration_ms)

        # Update trip with results
        trip.status = final_state.get("status", "completed")
        trip.result = {
            "itinerary": final_state.get("itinerary", []),
            "budget_breakdown": final_state.get("budget_breakdown"),
            "summary": final_state.get("summary", ""),
            "hotel_options": final_state.get("hotel_options", []),
            "transport_options": final_state.get("transport_options", []),
            "request": final_state.get("request", {}),
            "weather": final_state.get("weather"),
            "places_of_interest": final_state.get("places_of_interest", []),
            "errors": final_state.get("errors", []),
        }
        trip.planning_duration_ms = duration_ms
        trip.completed_at = datetime.now(tz=UTC)
        await self.db.flush()

        # Broadcast completed status via WS
        from parikrama.api.websocket.manager import ws_manager

        await ws_manager.broadcast_trip_completed(user_id=user_id, trip_id=trip_id)

        log.info(
            "trip_planning_completed",
            duration_ms=duration_ms,
            status=trip.status,
            itinerary_days=len(final_state.get("itinerary", [])),
            errors=len(final_state.get("errors", [])),
        )

        return {
            "trip_id": trip_id,
            "status": trip.status,
            "result": trip.result,
            "duration_ms": duration_ms,
            "messages": final_state.get("messages", []),
            "errors": final_state.get("errors", []),
        }

    async def get_agent_runs(self, trip_id: str, user_id: str) -> list[dict[str, Any]]:
        """
        Get the agent run history for a trip.

        Args:
            trip_id: Trip UUID string.
            user_id: User UUID string (for authorization check).

        Returns:
            List of agent run dicts ordered by creation time.
        """
        # Verify trip belongs to user
        await self._get_trip(trip_id, user_id)

        result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.trip_id == uuid.UUID(trip_id))
            .order_by(AgentRun.created_at)
        )
        runs = result.scalars().all()

        return [
            {
                "id": str(run.id),
                "agent_name": run.agent_name,
                "status": run.status,
                "duration_ms": run.duration_ms,
                "input_summary": run.input_summary,
                "output_summary": run.output_summary,
                "tokens_used": run.tokens_used,
                "error_message": run.error_message,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "created_at": run.created_at.isoformat(),
            }
            for run in runs
        ]

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_trip(self, trip_id: str, user_id: str) -> Trip:
        """Fetch and validate a trip belongs to the user."""
        result = await self.db.execute(
            select(Trip).where(
                Trip.id == uuid.UUID(trip_id),
                Trip.user_id == uuid.UUID(user_id),
            )
        )
        trip = result.scalar_one_or_none()
        if not trip:
            raise ValueError(f"Trip {trip_id} not found or access denied")
        return trip

    async def _persist_agent_runs(
        self,
        trip_id: str,
        final_state: TripPlanningState,
        total_duration_ms: int,
    ) -> None:
        """Create AgentRun records from the pipeline messages for observability."""
        messages = final_state.get("messages", [])
        errors = final_state.get("errors", [])

        # Map agent messages to AgentRun records
        agent_order = [
            "orchestrator",
            "research",
            "booking",
            "budget_optimizer",
            "itinerary_finalizer",
        ]
        agent_duration_ms = total_duration_ms // max(len(agent_order), 1)

        seen_agents: set[str] = set()
        for msg in messages:
            agent_name = msg.get("agent", "unknown")
            if agent_name in seen_agents:
                continue  # Only one record per agent (budget may run multiple times)
            seen_agents.add(agent_name)

            # Check for errors related to this agent
            agent_error = next((e for e in errors if agent_name.lower() in e.lower()), None)

            run = AgentRun(
                trip_id=uuid.UUID(trip_id),
                agent_name=agent_name,
                status="completed" if not agent_error else "failed",
                input_summary=f"state at {agent_name} entry",
                output_summary=msg.get("content", "")[:500],
                tokens_used=0,  # Token tracking added in Phase 9 (monitoring)
                duration_ms=agent_duration_ms,
                error_message=agent_error,
                started_at=datetime.now(tz=UTC),
                completed_at=datetime.now(tz=UTC),
            )
            self.db.add(run)

        await self.db.flush()
