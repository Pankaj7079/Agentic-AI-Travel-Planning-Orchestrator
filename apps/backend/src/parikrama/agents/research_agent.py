"""
ResearchAgent — gathers destination intelligence for trip planning.

Runs 3 tools concurrently (asyncio.gather):
    1. Weather forecast (OpenWeatherMap or mock)
    2. Places of interest (Google Places or mock)
    3. RAG retrieval (uploaded travel guides from knowledge base)

Then synthesizes all data into a comprehensive research brief via LLM.
Graceful fallback: if ANY tool fails, continues with partial data.
Runs in PARALLEL with BookingAgent in the LangGraph graph.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from parikrama.agents.tools.places import search_places
from parikrama.agents.tools.weather import get_weather_forecast
from parikrama.agents.trip_state import AgentMessage, TripPlanningState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

RESEARCH_SYSTEM_PROMPT = """You are the Research Agent for PariKrama, an Indian travel planning system.

You have access to real data: weather forecasts, points of interest, and a travel knowledge base.

Your job: synthesize this data into a concise, actionable research brief for the trip.

Cover:
1. Weather summary and what to pack / best time for activities
2. Top attractions ranked by must-visit priority
3. Local food scene (must-try dishes, restaurant types, price range)
4. Safety notes, seasonal warnings, festival impacts on crowds/prices
5. Budget tips specific to this destination

For Indian destinations:
- Note monsoon season impact (Jun-Sep)
- Mention ATM availability in remote areas (Leh, Manali, etc.)
- Suggest regional transport (local buses, shared jeeps, auto-rickshaws)
- Include Hindi/local language tips for interacting with locals

Write in a friendly, practical tone. Be specific, not generic.
Keep the output under 600 words."""


async def research_node(
    state: TripPlanningState,
    llm_router: LLMRouter,
    db: AsyncSession,
) -> TripPlanningState:
    """
    LangGraph node: gather destination intelligence.

    Runs weather, places, and RAG lookups concurrently, then synthesizes
    findings into a research brief using the LLM.

    Args:
        state: Current pipeline state (must have `request` from orchestrator).
        llm_router: LLMRouter for LLM calls.
        db: Database session for RAG retrieval.

    Returns:
        Updated state with weather, places_of_interest, destination_info, reviews_summary.
    """
    log = logger.bind(agent="research", trip_id=state.get("trip_id"))
    log.info("research_started")

    request = state.get("request", {})
    destination = request.get("destination", "")
    days = request.get("days", 3)
    errors: list[str] = list(state.get("errors", []))

    # ── Run tools concurrently ────────────────────────────────────────────────
    weather_result, places_result, rag_result = await asyncio.gather(
        _fetch_weather(destination, days, errors),
        _fetch_places(destination, errors),
        _fetch_rag_context(destination, db, errors),
        return_exceptions=False,
    )

    # ── Synthesize via LLM ────────────────────────────────────────────────────
    context = _build_research_context(request, weather_result, places_result, rag_result)
    research_brief = await _synthesize_research(context, destination, days, llm_router, state, errors)

    messages: list[AgentMessage] = list(state.get("messages", []))
    messages.append(
        AgentMessage(
            agent="research",
            content=(
                f"Research complete: weather {'✓' if weather_result else '✗'}, "
                f"{len(places_result)} places found, "
                f"{'RAG context retrieved' if rag_result else 'no RAG context'}"
            ),
        )
    )

    log.info(
        "research_completed",
        destination=destination,
        places_count=len(places_result),
        rag_chars=len(rag_result),
        brief_chars=len(research_brief),
    )

    return {
        **state,
        "weather": weather_result,
        "places_of_interest": places_result,
        "destination_info": rag_result,
        "reviews_summary": research_brief,
        "current_agent": "research",
        "messages": messages,
        "errors": errors,
    }


# ── Private helpers ────────────────────────────────────────────────────────────


async def _fetch_weather(destination: str, days: int, errors: list[str]) -> dict | None:
    """Fetch weather with error capture."""
    try:
        return await get_weather_forecast(destination, days)
    except Exception as exc:
        msg = f"Weather tool failed: {exc}"
        logger.warning("weather_tool_error", error=str(exc)[:100])
        errors.append(msg)
        return None


async def _fetch_places(destination: str, errors: list[str]) -> list[dict]:
    """Fetch places with error capture."""
    try:
        return await search_places(destination, max_results=7)
    except Exception as exc:
        msg = f"Places tool failed: {exc}"
        logger.warning("places_tool_error", error=str(exc)[:100])
        errors.append(msg)
        return []


async def _fetch_rag_context(destination: str, db: AsyncSession, errors: list[str]) -> str:
    """Retrieve RAG knowledge base context for this destination."""
    try:
        from parikrama.schemas.rag import SearchRequest
        from parikrama.services.rag_service import RAGService

        rag_service = RAGService(db)
        results = await rag_service.search(
            SearchRequest(
                query=f"travel guide {destination} attractions food tips budget",
                top_k=5,
            )
        )
        if results and hasattr(results, "__iter__"):
            chunks = []
            for r in results:
                content = r.content if hasattr(r, "content") else str(r)
                if content:
                    chunks.append(content)
            return "\n\n".join(chunks[:5])
        return ""
    except Exception as exc:
        logger.warning("rag_context_failed", error=str(exc)[:100])
        errors.append(f"RAG retrieval failed: {exc}")
        return ""


def _build_research_context(
    request: dict,
    weather: dict | None,
    places: list[dict],
    rag_context: str,
) -> str:
    """Combine all research data into a context string for the LLM."""
    parts = []

    dest = request.get("destination", "Unknown")
    parts.append(f"Destination: {dest}")
    parts.append(f"Duration: {request.get('days', 3)} days")
    parts.append(f"Budget style: {request.get('preferences', {}).get('style', 'budget')}")

    if weather:
        advisory = weather.get("advisory", "")
        forecasts = weather.get("forecasts", [])
        if forecasts:
            temps = [f"Day {i+1}: {f['temp_min']}-{f['temp_max']}C" for i, f in enumerate(forecasts[:3])]
            parts.append(f"\nWeather: {', '.join(temps)}")
        if advisory:
            parts.append(f"Weather Advisory: {advisory}")

    if places:
        place_names = [
            f"{p.get('name', '')} ({p.get('type', '')}, {p.get('entry_fee_inr', 0)} INR entry)"
            for p in places[:7]
        ]
        parts.append("Top Places:\n" + "\n".join(f"- {p}" for p in place_names))

    if rag_context:
        parts.append(f"\nKnowledge Base:\n{rag_context[:1500]}")

    return "\n".join(parts)


async def _synthesize_research(
    context: str,
    destination: str,
    days: int,
    llm_router: LLMRouter,
    state: TripPlanningState,
    errors: list[str],
) -> str:
    """Synthesize research context into a brief via LLM."""
    try:
        response = await llm_router.generate(
            prompt=f"Write a research brief for a {days}-day trip to {destination}:\n\n{context}",
            system=RESEARCH_SYSTEM_PROMPT,
            temperature=0.6,
        )
        return response.content
    except Exception as exc:
        logger.error("research_llm_failed", error=str(exc)[:100])
        errors.append(f"Research synthesis failed: {exc}")
        # Return a minimal fallback brief
        return (
            f"Research data gathered for {destination}. "
            f"Found {context.count('- ')} places of interest. "
            "See weather and places data in the trip details."
        )
