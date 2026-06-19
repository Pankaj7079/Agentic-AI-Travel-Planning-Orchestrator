"""
Trip Planning API — endpoints for the Phase 4 multi-agent pipeline.

Routes:
    POST /api/v1/trips/{id}/plan    — Start the full multi-agent planning pipeline (async, returns immediately)
    GET  /api/v1/trips/{id}/agents  — Get per-agent run history for a trip

Design:
    The /plan endpoint dispatches planning as a background asyncio task and returns
    202 Accepted immediately. The client polls /trips/{id}/status or connects via
    WebSocket at /ws/{user_id} to receive real-time agent progress updates.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from parikrama.core.security import get_current_user_id
from parikrama.db.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/trips", tags=["trip-planning"])


# ── Request / Response schemas ─────────────────────────────────────────────────


class PlanTripRequest(BaseModel):
    """Request body to start the multi-agent trip planning pipeline."""

    raw_input: str = Field(
        min_length=5,
        max_length=2000,
        description="Natural language trip request (English/Hindi/Hinglish)",
        examples=["Plan a 5-day trip from Delhi to Manali with a budget of ₹15,000"],
    )


class PlanTripResponse(BaseModel):
    """Immediate response from the trip planning pipeline dispatch."""

    trip_id: str
    status: str
    message: str


class AgentRunResponse(BaseModel):
    """A single agent execution record."""

    id: str
    agent_name: str
    status: str
    duration_ms: int | None
    input_summary: str | None
    output_summary: str | None
    tokens_used: int
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/{trip_id}/plan",
    response_model=PlanTripResponse,
    status_code=202,
    summary="Start multi-agent trip planning pipeline (async)",
)
async def plan_trip(
    trip_id: str,
    request: PlanTripRequest,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanTripResponse:
    """
    Trigger the full multi-agent planning pipeline for an existing trip.

    **Returns immediately (202 Accepted)** — planning runs as a background task.

    Poll `GET /api/v1/trips/{id}/status` to track progress, or connect to
    `WebSocket /ws/{user_id}?token=<access_token>` for real-time agent updates.

    **Pipeline (runs in background):**
    1. **Orchestrator** — parses your natural language request
    2. **Research** (parallel) — gathers weather, places, travel knowledge
    3. **Booking** (parallel) — finds hotels and transport options
    4. **Budget Optimizer** — calculates cost breakdown, suggests savings
    5. **Itinerary Finalizer** — generates day-by-day plan
    """
    import uuid
    from sqlalchemy import select
    from parikrama.models.trip import Trip

    # Verify trip exists and belongs to user before dispatching
    try:
        result = await db.execute(
            select(Trip).where(
                Trip.id == uuid.UUID(trip_id),
                Trip.user_id == uuid.UUID(user_id),
            )
        )
        trip = result.scalar_one_or_none()
    except Exception:
        trip = None

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip {trip_id} not found or access denied",
        )

    if trip.status in ("completed", "failed", "cancelled"):
        # Allow re-planning by resetting status
        trip.status = "pending"
        await db.flush()

    # Check LLM is configured before dispatching
    try:
        from parikrama.config import settings
        from parikrama.llm.router import LLMRouter, LLMUnavailableError
        LLMRouter.from_settings(settings)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM provider not configured: {exc}",
        ) from exc

    # Dispatch the background planning task
    from parikrama.services.async_planner import run_planning_background
    background_tasks.add_task(
        run_planning_background,
        trip_id=trip_id,
        user_id=user_id,
        raw_input=request.raw_input,
    )

    logger.info(
        "trip_planning_dispatched",
        trip_id=trip_id,
        user_id=user_id,
        raw_input=request.raw_input[:80],
    )

    return PlanTripResponse(
        trip_id=trip_id,
        status="planning",
        message="Planning started. Poll /trips/{id}/status or connect to WebSocket for live updates.",
    )


@router.get(
    "/{trip_id}/agents",
    response_model=list[AgentRunResponse],
    summary="Get agent run history for a trip",
)
async def get_agent_runs(
    trip_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentRunResponse]:
    """
    Get the per-agent execution history for a trip planning session.

    Returns one record per agent (orchestrator, research, booking,
    budget_optimizer, itinerary_finalizer) with timing and status.
    Useful for debugging slow or failed pipelines.
    """
    import uuid
    from sqlalchemy import select
    from parikrama.models.trip import AgentRun, Trip

    # Verify trip belongs to user
    result = await db.execute(
        select(Trip).where(
            Trip.id == uuid.UUID(trip_id),
            Trip.user_id == uuid.UUID(user_id),
        )
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip {trip_id} not found or access denied",
        )

    runs_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.trip_id == uuid.UUID(trip_id))
        .order_by(AgentRun.created_at)
    )
    runs = runs_result.scalars().all()

    return [
        AgentRunResponse(
            id=str(run.id),
            agent_name=run.agent_name,
            status=run.status,
            duration_ms=run.duration_ms,
            input_summary=run.input_summary,
            output_summary=run.output_summary,
            tokens_used=run.tokens_used,
            error_message=run.error_message,
            started_at=run.started_at.isoformat() if run.started_at else None,
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            created_at=run.created_at.isoformat(),
        )
        for run in runs
    ]
