"""
ItineraryFinalizer — generates the complete day-by-day travel plan.

This is the LAST agent in the pipeline. It receives ALL gathered data
(weather, places, hotels, transport, budget) and produces a polished,
actionable day-by-day itinerary the user can follow.

Output is stored as both structured `itinerary` (list of DayPlans)
and a natural-language `summary`.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

from parikrama.agents.trip_state import AgentMessage, DayPlan, TripPlanningState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

ITINERARY_SYSTEM_PROMPT = """You are the Itinerary Finalizer for PariKrama, an Indian travel planning system.

Create a detailed day-by-day travel itinerary using all the research and booking data provided.

For EACH day, include:
- title: "Day 1: Arrival & Local Exploration" (creative, descriptive)
- activities: list of {time, activity, location, cost_inr, duration_mins, tips}
- meals: list of {time, type (breakfast/lunch/dinner), suggestion, estimated_cost_inr}
- accommodation: {hotel, check_in (Day 1 only), check_out (last day only)}
- estimated_cost_inr: total estimated spend for the day
- tips: list of practical tips for the day

Style guidelines:
- Friendly, conversational tone — like advice from a seasoned Indian traveler
- Include local food recommendations (specific dishes, dhaba vs restaurant)
- Mention photography spots with best lighting time
- Budget travel tips (shared cabs, local buses, packed lunch)
- Consider weather (no outdoor activities during peak heat or rain)
- Buffer time for rest and spontaneous exploration
- Hindi phrases helpful for locals (optional, 1-2 per day)

Return a JSON array of day plan objects, one per day.
No markdown, no explanation — only the JSON array starting with [."""


async def itinerary_finalizer_node(
    state: TripPlanningState,
    llm_router: LLMRouter,
    db: AsyncSession,
) -> TripPlanningState:
    """
    LangGraph node: generate the final day-by-day itinerary.

    Args:
        state: Full pipeline state with all agent outputs.
        llm_router: LLMRouter for the final LLM call.
        db: Not used — kept for interface consistency.

    Returns:
        Completed state with itinerary, summary, and status="completed".
    """
    log = logger.bind(agent="itinerary_finalizer", trip_id=state.get("trip_id"))
    log.info("itinerary_finalizer_started")

    request = state.get("request", {})
    days = int(request.get("days", 3))
    destination = request.get("destination", "")
    total_budget = float(request.get("budget_inr", 10000))
    errors: list[str] = []  # only NEW errors from this node

    # Broadcast to WebSocket
    from parikrama.api.websocket.manager import ws_manager

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="itinerary_finalizer",
        status="running",
        message=f"Itinerary Finalizer starting: Generating day-by-day travel plan for {days} days in {destination}...",
    )

    # Compile all available data into a rich context
    context = _compile_full_context(state)

    # Generate itinerary via LLM
    itinerary, raw_response = await _generate_itinerary(
        context, days, destination, llm_router, errors
    )

    # Generate one-paragraph summary
    summary = _generate_summary(request, state, itinerary, raw_response)

    # Return only new items — messages/errors are Annotated[list, operator.add]
    # LangGraph concatenates these onto the existing lists.
    new_messages: list[AgentMessage] = [
        AgentMessage(
            agent="itinerary_finalizer",
            content=f"Itinerary complete: {len(itinerary)} days planned for {destination}",
        )
    ]

    log.info(
        "itinerary_finalizer_completed",
        destination=destination,
        days_planned=len(itinerary),
        budget=total_budget,
    )

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="itinerary_finalizer",
        status="completed",
        message=f"Itinerary generation complete! Planned {len(itinerary)} days for {destination}.",
    )

    return {
        # ONLY return keys this node writes — do NOT spread **state.
        # LangGraph merges node outputs; spreading state would re-write all
        # upstream keys (trip_id, user_id, request, etc.) unnecessarily.
        "itinerary": itinerary,
        "summary": summary,
        "status": "completed",
        "current_agent": "itinerary_finalizer",
        "messages": new_messages,  # only new — LangGraph adds to existing
        "errors": errors,  # only new errors
    }


# ── Private helpers ────────────────────────────────────────────────────────────


def _compile_full_context(state: TripPlanningState) -> str:
    """Build a comprehensive context string from all agent outputs."""
    req = state.get("request", {})
    parts = [
        f"Trip: {req.get('origin', '?')} → {req.get('destination', '?')}, {req.get('days', 3)} days",
        f"Budget: ₹{req.get('budget_inr', 0):,.0f} for {req.get('travelers', 1)} traveler(s)",
        f"Style: {req.get('preferences', {}).get('style', 'budget')}",
    ]

    prefs = req.get("preferences", {})
    if prefs.get("interests"):
        parts.append(f"Interests: {', '.join(prefs['interests'])}")

    weather = state.get("weather")
    if weather:
        advisory = weather.get("advisory", "")
        forecasts = weather.get("forecasts", [])
        if forecasts:
            temp_summary = ", ".join(
                [
                    f"Day {i + 1}: {f['temp_min']}-{f['temp_max']}C"
                    for i, f in enumerate(forecasts[:5])
                ]
            )
            parts.append(f"\nWeather: {temp_summary}")
        if advisory:
            parts.append(f"Advisory: {advisory}")

    places = state.get("places_of_interest", [])
    if places:
        place_list = "\n".join(
            [
                f"  - {p.get('name', '')} ({p.get('type', '')}, "
                f"₹{p.get('entry_fee_inr', 0)} entry, best: {p.get('best_time', 'anytime')})"
                for p in places[:8]
            ]
        )
        parts.append(f"\nTop Places:\n{place_list}")

    research = state.get("reviews_summary", "")
    if research:
        parts.append(f"\nResearch Brief:\n{research[:800]}")

    hotels = state.get("hotel_options", [])
    if hotels:
        best_hotel = hotels[0]
        parts.append(
            f"\nRecommended Hotel: {best_hotel.get('name', 'N/A')} "
            f"(₹{best_hotel.get('price_per_night_inr', 0):,.0f}/night, "
            f"rating: {best_hotel.get('rating', 'N/A')})"
        )

    transport = state.get("transport_options", [])
    if transport:
        best_transport = transport[0]
        parts.append(
            f"Recommended Transport: {best_transport.get('type', 'bus')} "
            f"(₹{best_transport.get('price_inr', 0):,.0f}, "
            f"{best_transport.get('duration_hours', '?')} hrs)"
        )

    budget_breakdown = state.get("budget_breakdown")
    if budget_breakdown:
        parts.append(
            f"\nBudget Breakdown: Transport ₹{budget_breakdown.get('transport_inr', 0):,.0f}, "
            f"Hotel ₹{budget_breakdown.get('accommodation_inr', 0):,.0f}, "
            f"Food ₹{budget_breakdown.get('food_inr', 0):,.0f}, "
            f"Activities ₹{budget_breakdown.get('activities_inr', 0):,.0f}"
        )
        tips = budget_breakdown.get("savings_tips", [])
        if tips:
            parts.append("Savings Tips: " + "; ".join(tips))

    return "\n".join(parts)


async def _generate_itinerary(
    context: str,
    days: int,
    destination: str,
    llm_router: LLMRouter,
    errors: list[str],
) -> tuple[list[DayPlan], str]:
    """Call LLM and parse the day-by-day itinerary JSON."""
    try:
        response = await llm_router.generate(
            prompt=f"Create a {days}-day itinerary for this trip:\n\n{context}",
            system=ITINERARY_SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=8192,
        )
        raw = _extract_json_array(response.content)
        parsed = json.loads(raw)

        if not isinstance(parsed, list):
            raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")

        day_plans = [
            DayPlan(**{k: v for k, v in day.items() if k in DayPlan.__annotations__})
            for day in parsed
        ]
        return day_plans, response.content

    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.error("itinerary_parse_failed", error=str(exc)[:100])
        errors.append(f"Itinerary generation returned unexpected format: {exc}")

        # If we got a response but couldn't parse JSON, try to salvage:
        # 1. Return raw response as summary so user gets something useful
        # 2. Generate a minimal fallback itinerary from available data
        raw_content = response.content if (response and hasattr(response, "content")) else ""
        if raw_content:
            # Try one more time: extract individual day objects from markdown
            minimal = _extract_days_from_markdown(raw_content, days, destination)
            if minimal:
                return minimal, raw_content
            return [], raw_content
        return [], ""


def _generate_summary(
    request: dict,
    state: TripPlanningState,
    itinerary: list[DayPlan],
    raw_response: str,
) -> str:
    """Generate a one-paragraph human-readable trip summary."""
    dest = request.get("destination", "your destination")
    days = request.get("days", 3)
    budget = float(request.get("budget_inr", 0))
    travelers = request.get("travelers", 1)

    hotel_options = state.get("hotel_options", [])
    transport_options = state.get("transport_options", [])

    hotel_name = hotel_options[0].get("name", "a comfortable hotel") if hotel_options else "a hotel"
    transport_type = transport_options[0].get("type", "bus") if transport_options else "transport"

    if itinerary:
        return (
            f"Your {days}-day trip to {dest} is ready! "
            f"Traveling {'solo' if travelers == 1 else f'with {travelers} people'} "
            f"on a budget of ₹{budget:,.0f}, you'll stay at {hotel_name} "
            f"and travel by {transport_type}. "
            f"The itinerary covers {len(itinerary)} days of curated activities, "
            f"local food, and memorable experiences."
        )
    else:
        # LLM returned non-JSON (markdown) — use raw response as summary
        return (
            raw_response[:1000]
            if raw_response
            else (
                f"Your {days}-day trip to {dest} has been planned within your ₹{budget:,.0f} budget."
            )
        )


def _extract_days_from_markdown(text: str, days: int, destination: str) -> list[DayPlan]:
    """Best-effort extraction of day plans from markdown-formatted LLM response.

    When JSON parsing fails, this tries to find 'Day N:' patterns and build
    minimal DayPlan objects so the user still gets a usable itinerary.
    """
    import re as _re

    day_pattern = _re.compile(
        r"Day\s+(\d+)\s*[:\-]\s*(.+?)(?=Day\s+\d+|\Z)", _re.DOTALL | _re.IGNORECASE
    )
    matches = day_pattern.findall(text)

    if not matches:
        return []

    plans: list[DayPlan] = []
    for day_num, content in matches[:days]:
        # Extract first line as title
        lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
        title = lines[0] if lines else f"Day {day_num}: Explore {destination}"
        # Remove markdown formatting from title
        title = _re.sub(r"[*#_`]", "", title).strip()

        plans.append(
            DayPlan(
                title=title,
                activities=[],
                meals=[],
                accommodation={"hotel": ""},
                estimated_cost_inr=0,
                tips=[lines[1]] if len(lines) > 1 else [],
            )
        )

    return plans


def _extract_json_array(text: str) -> str:
    """Extract JSON array from LLM response, stripping any markdown.

    Handles truncated JSON by attempting to close open brackets/braces
    when the response was cut off (finish_reason='length').
    """
    text = text.strip()

    # Try 1: Direct parse (LLM returned clean JSON)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return text
    except json.JSONDecodeError:
        pass

    # Try 2: Strip markdown code fences
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Try 3: Find the outermost JSON array [...]
    match = re.search(r"(\[[\s\S]*)", text)
    if match:
        extracted = match.group(0)
        # Try parsing as-is first
        try:
            json.loads(extracted)
            return extracted
        except json.JSONDecodeError:
            pass

        # Attempt to fix truncated JSON by closing open structures
        try:
            # Find the last complete object
            last_complete = extracted.rfind("}")
            if last_complete > 0:
                truncated = extracted[: last_complete + 1]
                # Count unclosed brackets
                open_brackets = truncated.count("[") - truncated.count("]")
                open_braces = truncated.count("{") - truncated.count("}")
                truncated += "]" * max(0, open_brackets)
                truncated += "}" * max(0, open_braces)
                json.loads(truncated)  # validate
                return truncated
        except (json.JSONDecodeError, ValueError):
            pass

        # Try removing trailing comma before closing bracket
        try:
            cleaned = re.sub(r",\s*([}\]])", r"\1", extracted)
            open_brackets = cleaned.count("[") - cleaned.count("]")
            open_braces = cleaned.count("{") - cleaned.count("}")
            cleaned += "]" * max(0, open_brackets)
            cleaned += "}" * max(0, open_braces)
            json.loads(cleaned)
            return cleaned
        except (json.JSONDecodeError, ValueError):
            pass

    return text
