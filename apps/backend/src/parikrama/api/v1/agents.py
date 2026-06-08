"""
Agents API — endpoints for running PariKrama travel planning agents.

All endpoints require authentication. The LLM router is built once
at startup and injected via FastAPI dependency injection.

Routes:
    POST /api/v1/agents/itinerary  — Day-wise itinerary planner
    POST /api/v1/agents/budget     — Budget breakdown estimator
    GET  /api/v1/agents/health     — LLM router health status
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from parikrama.agents.schemas import AgentInput, AgentOutput
from parikrama.core.security import get_current_user_id
from parikrama.db.session import get_db

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Request / Response schemas ─────────────────────────────────────────────────


class ItineraryRequest(BaseModel):
    """Request body for itinerary generation."""

    query: str = Field(
        min_length=10,
        max_length=1000,
        examples=["Plan a 5-day trip from Delhi to Manali with budget ₹15,000"],
    )
    trip_id: str | None = Field(default=None, description="Optional linked trip UUID")
    budget: float | None = Field(default=None, gt=0, description="Budget in INR")


class BudgetRequest(BaseModel):
    """Request body for budget breakdown."""

    query: str = Field(
        min_length=10,
        max_length=1000,
        examples=["Budget breakdown for 5 days Manali trip, total budget 15000"],
    )
    trip_id: str | None = None
    budget: float | None = Field(default=None, gt=0, description="Budget in INR")


class AgentResponse(BaseModel):
    """Standardized agent API response."""

    content: str
    agent: str
    provider: str
    model: str
    latency_ms: int
    rag_chunks_used: int
    metadata: dict[str, Any] = {}


# ── LLM Router dependency ──────────────────────────────────────────────────────


def _get_llm_router():  # type: ignore[return]
    """FastAPI dependency — returns the singleton LLMRouter.

    Raises HTTP 503 if no LLM provider is configured.
    """
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
    "/itinerary",
    response_model=AgentResponse,
    summary="Generate a day-wise travel itinerary",
)
async def generate_itinerary(
    request: ItineraryRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentResponse:
    """Run the ItineraryAgent to generate a day-wise travel plan.

    The agent retrieves relevant knowledge from the RAG knowledge base
    (uploaded travel guides) before calling the LLM, ensuring grounded,
    factual itineraries.

    Example query: *"Plan a 5-day trip from Delhi to Manali, budget ₹15,000"*
    """
    from parikrama.agents.itinerary_agent import ItineraryAgent
    from parikrama.llm.router import LLMUnavailableError

    try:
        llm_router = _get_llm_router()
    except HTTPException:
        raise

    agent = ItineraryAgent(llm_router=llm_router, db=db)

    try:
        output: AgentOutput = await agent.run(
            AgentInput(
                query=request.query,
                user_id=user_id,
                trip_id=request.trip_id,
                budget=request.budget,
            )
        )
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("itinerary_agent_error", error=str(exc), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Itinerary generation failed. Please try again.",
        ) from exc

    return AgentResponse(
        content=output.content,
        agent=output.agent,
        provider=output.provider,
        model=output.model,
        latency_ms=output.latency_ms,
        rag_chunks_used=output.rag_chunks_used,
        metadata=output.metadata,
    )


@router.post(
    "/budget",
    response_model=AgentResponse,
    summary="Generate a budget breakdown for a trip",
)
async def generate_budget(
    request: BudgetRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentResponse:
    """Run the BudgetAgent to estimate trip costs by category.

    Returns a detailed breakdown: transport / accommodation / food /
    activities / emergency buffer. All amounts in Indian Rupees (₹).

    Example query: *"Budget breakdown for 5-day Manali trip, ₹15,000 total"*
    """
    from parikrama.agents.budget_agent import BudgetAgent
    from parikrama.llm.router import LLMUnavailableError

    try:
        llm_router = _get_llm_router()
    except HTTPException:
        raise

    agent = BudgetAgent(llm_router=llm_router, db=db)

    try:
        output: AgentOutput = await agent.run(
            AgentInput(
                query=request.query,
                user_id=user_id,
                trip_id=request.trip_id,
                budget=request.budget,
            )
        )
    except LLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("budget_agent_error", error=str(exc), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Budget generation failed. Please try again.",
        ) from exc

    return AgentResponse(
        content=output.content,
        agent=output.agent,
        provider=output.provider,
        model=output.model,
        latency_ms=output.latency_ms,
        rag_chunks_used=output.rag_chunks_used,
        metadata=output.metadata,
    )


@router.get(
    "/health",
    summary="LLM router health status",
)
async def agents_health(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    """Return the current health of the LLM router (circuit breaker state).

    Shows which provider is active, error counts, and latency history.
    Useful for debugging production issues.
    """
    from parikrama.config import settings
    from parikrama.llm.router import LLMRouter, LLMUnavailableError

    try:
        router_instance = LLMRouter.from_settings(settings)
        return {
            "status": "ok",
            "router": router_instance.health_status(),
        }
    except LLMUnavailableError as exc:
        return {
            "status": "degraded",
            "error": str(exc),
            "router": None,
        }
