"""
Trip Planning API — endpoints for the Phase 4 multi-agent pipeline.

Routes:
    POST /api/v1/trips/{id}/plan    — Start the full multi-agent planning pipeline
    GET  /api/v1/trips/{id}/agents  — Get per-agent run history for a trip
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
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
        min_length=10,
        max_length=1000,
        description="Natural language trip request (English/Hindi/Hinglish)",
        examples=["Plan a 5-day trip from Delhi to Manali with a budget of ₹15,000"],
    )


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


class PlanTripResponse(BaseModel):
    """Response from the trip planning pipeline."""

    trip_id: str
    status: str
    duration_ms: int
    summary: str
    itinerary_days: int
    has_budget_breakdown: bool
    has_hotel_options: bool
    has_transport_options: bool
    errors: list[str]
    result: dict[str, Any]


# ── Dependency ─────────────────────────────────────────────────────────────────


def _get_llm_router():  # type: ignore[return]
    """FastAPI dependency — returns the singleton LLMRouter. Raises 503 if unavailable."""
    from parikrama.config import settings
    from parikrama.llm.router import LLMRouter, LLMUnavailableError

    try:
        return LLMRouter.from_settings(settings)
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/{trip_id}/plan",
    response_model=PlanTripResponse,
    summary="Start multi-agent trip planning pipeline",
)
async def plan_trip(
    trip_id: str,
    request: PlanTripRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanTripResponse:
    """
    Trigger the full multi-agent planning pipeline for an existing trip.

    **Pipeline:**
    1. **Orchestrator** — parses your natural language request
    2. **Research** (parallel) — gathers weather, places, travel knowledge
    3. **Booking** (parallel) — finds hotels and transport options
    4. **Budget Optimizer** — calculates cost breakdown, suggests savings
    5. **Itinerary Finalizer** — generates day-by-day plan

    The trip must exist (create via `POST /api/v1/trips/`) and belong to the authenticated user.

    Example: `"Plan a 5-day trip from Delhi to Manali, budget ₹15,000, I love adventure"`
    """
    from parikrama.llm.router import LLMUnavailableError
    from parikrama.services.trip_planning_service import TripPlanningService

    llm_router = _get_llm_router()
    service = TripPlanningService(db=db, llm_router=llm_router)

    try:
        result = await service.run_planning(
            trip_id=trip_id,
            user_id=user_id,
            raw_input=request.raw_input,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        logger.error("trip_planning_api_error", trip_id=trip_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Trip planning pipeline failed. Please try again.",
        ) from exc

    trip_result = result.get("result", {})

    return PlanTripResponse(
        trip_id=result["trip_id"],
        status=result["status"],
        duration_ms=result["duration_ms"],
        summary=trip_result.get("summary", ""),
        itinerary_days=len(trip_result.get("itinerary", [])),
        has_budget_breakdown=trip_result.get("budget_breakdown") is not None,
        has_hotel_options=len(trip_result.get("hotel_options", [])) > 0,
        has_transport_options=len(trip_result.get("transport_options", [])) > 0,
        errors=result.get("errors", []),
        result=trip_result,
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
    from parikrama.llm.router import LLMRouter
    from parikrama.services.trip_planning_service import TripPlanningService

    # llm_router not needed for this read-only operation
    try:
        from parikrama.config import settings

        llm_router = LLMRouter.from_settings(settings)
    except Exception:
        # For agent history reads, we don't need a working LLM router
        llm_router = None  # type: ignore[assignment]

    try:

        class _NoOpRouter:
            pass

        service = TripPlanningService(db=db, llm_router=llm_router or _NoOpRouter())  # type: ignore[arg-type]
        runs = await service.get_agent_runs(trip_id=trip_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return [AgentRunResponse(**run) for run in runs]
