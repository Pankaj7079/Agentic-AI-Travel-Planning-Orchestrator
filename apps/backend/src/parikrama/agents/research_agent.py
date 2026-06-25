"""
ResearchAgent — gathers destination intelligence for trip planning.

Runs 4 tools concurrently (asyncio.gather):
    1. Weather forecast (OpenWeatherMap or mock)
    2. Places of interest (Google Places or mock)
    3. Web search (DuckDuckGo — live travel info, no API key needed)
    4. RAG retrieval (uploaded travel guides from knowledge base)

Then synthesizes all data into a comprehensive research brief via LLM.
Graceful fallback: if ANY tool fails, continues with partial data.
Runs in PARALLEL with BookingAgent in the LangGraph graph.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import structlog

from parikrama.agents.tools.places import search_places
from parikrama.agents.tools.weather import get_weather_forecast
from parikrama.agents.tools.web_search import search_web
from parikrama.agents.trip_state import AgentMessage, TripPlanningState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

RESEARCH_SYSTEM_PROMPT = """You are the Research Agent for PariKrama, an Indian travel planning system.

You have access to real data: web search results, weather forecasts, points of interest, and a travel knowledge base.

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

    Runs weather, places, web search, and RAG lookups concurrently,
    then synthesizes findings into a research brief using the LLM.

    Priority: Web search (live data) > RAG (uploaded guides) > fallback.
    If web search returns good data, RAG is supplementary.
    If RAG has no docs, web search fills the gap.

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
    errors: list[str] = []  # only NEW errors from this node

    # Broadcast to WebSocket
    from parikrama.api.websocket.manager import ws_manager

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="research",
        status="running",
        message=f"Research Agent started: Searching web and gathering data for {destination}...",
    )

    # ── Run ALL 4 tools concurrently ──────────────────────────────────────────
    weather_result, places_result, web_result, rag_result = await asyncio.gather(
        _fetch_weather(destination, days, errors),
        _fetch_places(destination, errors),
        _fetch_web_search(destination, errors),
        _fetch_rag_context(destination, db, errors),
        return_exceptions=False,
    )

    # ── Combine web + RAG context (web is primary, RAG supplements) ──────────
    combined_context = _combine_research_sources(web_result, rag_result)

    # ── Synthesize via LLM ────────────────────────────────────────────────────
    context = _build_research_context(request, weather_result, places_result, combined_context)
    research_brief = await _synthesize_research(
        context, destination, days, llm_router, state, errors
    )

    # Only return NEW messages — LangGraph's operator.add reducer concatenates
    # them onto the existing list. Returning the full list causes duplication
    # when parallel nodes (research + booking) both read and extend it.
    source_parts = []
    if web_result:
        source_parts.append("web")
    if rag_result:
        source_parts.append("KB")
    source_str = " + ".join(source_parts) if source_parts else "none"

    new_messages: list[AgentMessage] = [
        AgentMessage(
            agent="research",
            content=(
                f"Research complete: weather {'ok' if weather_result else 'N/A'}, "
                f"{len(places_result)} places, "
                f"sources: {source_str}"
            ),
        )
    ]

    log.info(
        "research_completed",
        destination=destination,
        places_count=len(places_result),
        web_chars=len(web_result),
        rag_chars=len(rag_result),
        brief_chars=len(research_brief),
    )

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="research",
        status="completed",
        message=f"Research complete: found weather, {len(places_result)} places, and travel info for {destination}.",
    )

    return {
        # ONLY return keys this node writes — do NOT spread **state
        "weather": weather_result,
        "places_of_interest": places_result,
        "destination_info": combined_context,
        "reviews_summary": research_brief,
        "current_agent": "research",
        "messages": new_messages,
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


async def _fetch_web_search(destination: str, errors: list[str]) -> str:
    """Search the web for live travel info about the destination."""
    try:
        return await search_web(destination, max_results=8)
    except Exception as exc:
        msg = f"Web search failed: {exc}"
        logger.warning("web_search_error", error=str(exc)[:100])
        errors.append(msg)
        return ""


async def _fetch_rag_context(destination: str, db: AsyncSession, errors: list[str]) -> str:
    """Retrieve RAG knowledge base context for this destination."""
    try:
        from parikrama.schemas.rag import SearchRequest
        from parikrama.services.rag_service import RAGService

        rag_service = RAGService(db)
        response = await rag_service.search(
            SearchRequest(
                query=f"travel guide {destination} attractions food tips budget",
                top_k=5,
            )
        )
        if response and response.results:
            chunks = []
            for r in response.results:
                content = r.content if hasattr(r, "content") else str(r)
                if content:
                    chunks.append(content)
            return "\n\n".join(chunks[:5])
        return ""
    except Exception as exc:
        logger.warning("rag_context_failed", error=str(exc)[:100])
        errors.append(f"RAG retrieval failed: {exc}")
        # Rollback the session to recover from any failed transaction state.
        with contextlib.suppress(Exception):
            await db.rollback()
        return ""


def _combine_research_sources(web: str, rag: str) -> str:
    """Combine web search and RAG results into a single context.

    Web search is the primary source (live, up-to-date).
    RAG is supplementary (curated travel guides from uploaded docs).
    If both are empty, returns empty string — downstream handles gracefully.
    """
    parts = []
    if web:
        parts.append(f"Travel Research (Web):\n{web[:2000]}")
    if rag:
        parts.append(f"Travel Guide (Knowledge Base):\n{rag[:1500]}")
    return "\n\n---\n\n".join(parts)


def _build_research_context(
    request: dict,
    weather: dict | None,
    places: list[dict],
    research_data: str,
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
            temps = [
                f"Day {i + 1}: {f['temp_min']}-{f['temp_max']}C"
                for i, f in enumerate(forecasts[:3])
            ]
            parts.append(f"\nWeather: {', '.join(temps)}")
        if advisory:
            parts.append(f"Weather Advisory: {advisory}")

    if places:
        place_names = [
            f"{p.get('name', '')} ({p.get('type', '')}, {p.get('entry_fee_inr', 0)} INR entry)"
            for p in places[:7]
        ]
        parts.append("Top Places:\n" + "\n".join(f"- {p}" for p in place_names))

    if research_data:
        parts.append(f"\n{research_data[:3000]}")

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
