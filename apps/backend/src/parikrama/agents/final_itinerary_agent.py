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
    errors: list[str] = list(state.get("errors", []))

    # Compile all available data into a rich context
    context = _compile_full_context(state)

    # Generate itinerary via LLM
    itinerary, raw_response = await _generate_itinerary(
        context, days, destination, llm_router, errors
    )

    # Generate one-paragraph summary
    summary = _generate_summary(request, state, itinerary, raw_response)

    messages: list[AgentMessage] = list(state.get("messages", []))
    messages.append(
        AgentMessage(
            agent="itinerary_finalizer",
            content=f"Itinerary complete: {len(itinerary)} days planned for {destination}",
        )
    )

    log.info(
        "itinerary_finalizer_completed",
        destination=destination,
        days_planned=len(itinerary),
        budget=total_budget,
    )

    return {
        **state,
        "itinerary": itinerary,
        "summary": summary,
        "status": "completed",
        "current_agent": "itinerary_finalizer",
        "messages": messages,
        "errors": errors,
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
        # Return empty itinerary — summary will carry the response
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


def _extract_json_array(text: str) -> str:
    """Extract JSON array from LLM response, stripping any markdown."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"\[[\s\S]+\]", text)
    if match:
        return match.group(0)
    return text
