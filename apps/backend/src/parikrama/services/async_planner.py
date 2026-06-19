"""
async_planner.py — Background trip planning runner.

Runs the full LangGraph pipeline independently from the request context,
using its own DB session so it's not bound to the HTTP request lifecycle.

This allows the /plan endpoint to return immediately (202 Accepted)
while planning continues in the background. Status is polled via
GET /trips/{id}/status or received via WebSocket.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from parikrama.agents.trip_graph import build_trip_planning_graph
from parikrama.agents.trip_state import TripPlanningState
from parikrama.api.websocket.manager import ws_manager
from parikrama.db.session import async_session_factory
from parikrama.models.trip import AgentRun, Trip
from parikrama.models.user import User

logger = structlog.get_logger(__name__)


async def run_planning_background(
    trip_id: str,
    user_id: str,
    raw_input: str,
) -> None:
    """
    Execute the LangGraph planning pipeline in the background.

    This function creates its own database session so it is completely
    decoupled from the originating HTTP request. It commits after each
    major stage so the polling endpoint reflects real progress.

    Args:
        trip_id: UUID of the existing Trip record.
        user_id: UUID of the authenticated user.
        raw_input: Natural language trip request.
    """
    log = logger.bind(trip_id=trip_id, user_id=user_id)
    log.info("background_planning_started", raw_input=raw_input[:80])

    async with async_session_factory() as db:
        try:
            # ── 1. Mark trip as planning ─────────────────────────────────
            result = await db.execute(
                select(Trip).where(
                    Trip.id == uuid.UUID(trip_id),
                    Trip.user_id == uuid.UUID(user_id),
                )
            )
            trip = result.scalar_one_or_none()
            if not trip:
                log.error("background_trip_not_found")
                return

            trip.status = "planning"
            trip.request = {**(trip.request or {}), "raw_input": raw_input}
            await db.commit()

            # Notify client planning has started
            await ws_manager.broadcast_agent_update(
                user_id=user_id,
                trip_id=trip_id,
                agent="system",
                status="running",
                message="🚀 Starting multi-agent planning pipeline...",
            )

            # ── 2. Build initial state ────────────────────────────────────
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

            # ── 3. Build and run the LangGraph pipeline ───────────────────
            from parikrama.config import settings
            from parikrama.llm.router import LLMRouter

            llm_router = LLMRouter.from_settings(settings)
            graph = build_trip_planning_graph(llm_router, db)

            start_time = time.perf_counter()
            try:
                final_state = await graph.ainvoke(initial_state)
            except Exception as exc:
                log.error("background_pipeline_failed", error=str(exc))
                trip.status = "failed"
                trip.result = {"error": str(exc), "errors": [str(exc)]}
                await db.commit()
                await ws_manager.broadcast_agent_update(
                    user_id=user_id,
                    trip_id=trip_id,
                    agent="system",
                    status="failed",
                    message=f"Planning failed: {str(exc)[:200]}",
                )
                return

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # ── 4. Handle HITL approval gate ─────────────────────────────
            if final_state.get("requires_approval", False):
                trip.status = "awaiting_approval"
                trip.result = {
                    "request": final_state.get("request", {}),
                    "hotel_options": final_state.get("hotel_options", []),
                    "transport_options": final_state.get("transport_options", []),
                    "weather": final_state.get("weather"),
                    "places_of_interest": final_state.get("places_of_interest", []),
                    "destination_info": final_state.get("destination_info", ""),
                    "reviews_summary": final_state.get("reviews_summary", ""),
                }
                await db.commit()

                # Create approval record
                user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
                user = user_result.scalar_one_or_none()
                if user:
                    from parikrama.services.approval_service import ApprovalService

                    approval_svc = ApprovalService(db)
                    hotels = final_state.get("hotel_options", [])
                    budget = (final_state.get("request") or {}).get("budget_inr", 0)
                    top_hotel = hotels[0] if hotels else {}
                    approval_id = await approval_svc.create_approval(
                        trip_id=trip_id,
                        user=user,
                        approval_type="hotel_booking",
                        title="Approval needed: Hotel exceeds 50% of your budget",
                        description=(
                            f"{top_hotel.get('name', 'Selected hotel')} costs "
                            f"₹{top_hotel.get('price_per_night_inr', 0):,}/night. "
                            f"Your total budget is ₹{budget:,}. Approve to continue planning."
                        ),
                        payload={
                            "hotel_options": hotels[:3],
                            "transport_options": final_state.get("transport_options", [])[:3],
                            "budget_inr": budget,
                        },
                    )
                    await db.commit()

                    # Broadcast approval request
                    await ws_manager.broadcast_approval_request(
                        user_id=user_id,
                        approval_id=approval_id,
                        title="Approval needed",
                        description=f"Hotel exceeds budget. Top option: {top_hotel.get('name', 'N/A')} at ₹{top_hotel.get('price_per_night_inr', 0):,}/night",
                        payload={"hotel_options": hotels[:3]},
                    )

                log.info("background_awaiting_approval", trip_id=trip_id)
                return

            # ── 5. Persist agent run records ──────────────────────────────
            await _persist_agent_runs(db, trip_id, final_state, duration_ms)

            # ── 6. Update trip with completed results ─────────────────────
            # Update the trip request with the parsed structured data from LLM
            parsed_request = final_state.get("request", {})
            trip.request = {
                **(trip.request or {}),
                **parsed_request,
                "raw_input": raw_input,
            }
            trip.status = final_state.get("status", "completed")
            trip.result = {
                "itinerary": final_state.get("itinerary", []),
                "budget_breakdown": final_state.get("budget_breakdown"),
                "summary": final_state.get("summary", ""),
                "hotel_options": final_state.get("hotel_options", []),
                "transport_options": final_state.get("transport_options", []),
                "request": parsed_request,
                "weather": final_state.get("weather"),
                "places_of_interest": final_state.get("places_of_interest", []),
                "errors": final_state.get("errors", []),
            }
            trip.planning_duration_ms = duration_ms
            trip.completed_at = datetime.now(tz=UTC)
            await db.commit()

            # ── 7. Notify completion ──────────────────────────────────────
            await ws_manager.broadcast_trip_completed(
                user_id=user_id,
                trip_id=trip_id,
            )
            log.info(
                "background_planning_completed",
                duration_ms=duration_ms,
                itinerary_days=len(final_state.get("itinerary", [])),
                errors=len(final_state.get("errors", [])),
            )

        except Exception as exc:
            log.error("background_planning_unexpected_error", error=str(exc))
            try:
                # Try to mark trip as failed
                async with async_session_factory() as recovery_db:
                    result = await recovery_db.execute(
                        select(Trip).where(Trip.id == uuid.UUID(trip_id))
                    )
                    trip = result.scalar_one_or_none()
                    if trip:
                        trip.status = "failed"
                        trip.result = {"error": str(exc)}
                        await recovery_db.commit()
            except Exception:
                pass  # Nothing more we can do


async def _persist_agent_runs(
    db: Any,
    trip_id: str,
    final_state: TripPlanningState,
    total_duration_ms: int,
) -> None:
    """Create AgentRun records from pipeline messages for observability."""
    messages = final_state.get("messages", [])
    errors = final_state.get("errors", [])

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
            continue
        seen_agents.add(agent_name)

        agent_error = next((e for e in errors if agent_name.lower() in e.lower()), None)

        run = AgentRun(
            trip_id=uuid.UUID(trip_id),
            agent_name=agent_name,
            status="completed" if not agent_error else "failed",
            input_summary=f"state at {agent_name} entry",
            output_summary=msg.get("content", "")[:500],
            tokens_used=0,
            duration_ms=agent_duration_ms,
            error_message=agent_error,
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
        )
        db.add(run)

    await db.flush()
