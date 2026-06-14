"""
BudgetOptimizer — calculates a realistic cost breakdown and checks feasibility.

Takes research (destination costs) + booking (hotel + transport prices) data
and produces a detailed budget breakdown in INR. If total > user's budget,
suggests specific cost-cutting tips and sets is_within_budget=False.

The graph's conditional edge routes:
    - is_within_budget=True  → ItineraryFinalizer
    - is_within_budget=False → BudgetOptimizer again (max 2 retries, then proceed)
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

from parikrama.agents.trip_state import AgentMessage, BudgetBreakdown, TripPlanningState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

BUDGET_SYSTEM_PROMPT = """You are the Budget Optimizer for PariKrama, an Indian travel planning system.

Analyze the trip data and produce a realistic, itemized budget breakdown in INR.

Categories (all amounts in INR):
- transport_inr: Getting to/from destination (one-way x 2)
- accommodation_inr: Total hotel cost for all nights
- food_inr: Meals for all days (Rs.150-300/meal in budget, Rs.300-600 in mid, Rs.600+ premium)
- activities_inr: Entry fees + guided tours + adventure sports
- misc_inr: Local transport, tips, souvenirs, emergency buffer (add 10% of subtotal)
- total_inr: Sum of all above
- is_within_budget: true if total_inr <= user's budget
- savings_tips: List of 2-4 specific cost-cutting suggestions if over budget

Indian travel context:
- Hill stations cost 20-30% more for food than plains
- ATM fees add Rs.200-500 in remote areas
- Shared jeeps and local buses cut transport costs by 60% vs private cabs
- Dhabas and local restaurants: Rs.80-150/meal
- Tourist restaurants: Rs.200-400/meal

Return ONLY valid JSON, no markdown, no explanation."""


async def budget_optimizer_node(
    state: TripPlanningState,
    llm_router: LLMRouter,
    db: AsyncSession,
) -> TripPlanningState:
    """
    LangGraph node: calculate budget breakdown and feasibility.

    Args:
        state: Current pipeline state (must have request, hotel_options, transport_options).
        llm_router: LLMRouter for LLM call.
        db: Not used — kept for interface consistency.

    Returns:
        Updated state with budget_breakdown and is_within_budget.
    """
    log = logger.bind(agent="budget_optimizer", trip_id=state.get("trip_id"))
    log.info("budget_optimizer_started")

    request = state.get("request", {})
    total_budget = float(request.get("budget_inr", 10000))
    days = int(request.get("days", 3))
    errors: list[str] = list(state.get("errors", []))

    # Broadcast to WebSocket
    from parikrama.api.websocket.manager import ws_manager
    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="budget_optimizer",
        status="running",
        message=f"Budget Optimizer starting: Calculating detailed cost breakdown for ₹{total_budget:,.0f} budget...",
    )

    # Build context from all available data
    context = _build_budget_context(state, request, total_budget, days)

    # Call LLM for breakdown
    breakdown = await _generate_breakdown(context, total_budget, llm_router, errors)
    is_within = breakdown.get("is_within_budget", True) if breakdown else True

    messages: list[AgentMessage] = list(state.get("messages", []))
    retry_num = state.get("_budget_retries", 0)
    if retry_num > 0:
        messages.append(
            AgentMessage(
                agent="budget_optimizer", content=f"Budget re-optimization attempt #{retry_num}"
            )
        )

    total_est = breakdown.get("total_inr", 0) if breakdown else 0
    messages.append(
        AgentMessage(
            agent="budget_optimizer",
            content=(
                f"Budget: ₹{total_est:,.0f} / ₹{total_budget:,.0f} — "
                f"{'✓ within budget' if is_within else '⚠️ over budget'}"
            ),
        )
    )

    log.info(
        "budget_optimizer_completed",
        estimated_total=total_est,
        user_budget=total_budget,
        is_within_budget=is_within,
    )

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="budget_optimizer",
        status="completed",
        message=f"Budget calculation complete: Estimated ₹{total_est:,.0f} (" +
                ("within budget" if is_within else "exceeds budget, applied cost-saving tips") + ").",
    )

    return {
        **state,
        "budget_breakdown": BudgetBreakdown(**breakdown) if breakdown else None,
        "is_within_budget": is_within,
        "current_agent": "budget_optimizer",
        "messages": messages,
        "errors": errors,
    }


# ── Private helpers ────────────────────────────────────────────────────────────


def _build_budget_context(state: dict, request: dict, total_budget: float, days: int) -> str:
    """Compile trip data into a context string for the LLM."""
    parts = [
        f"Trip: {request.get('origin', '?')} → {request.get('destination', '?')}, {days} days",
        f"Total budget: ₹{total_budget:,.0f}",
        f"Travelers: {request.get('travelers', 1)}",
        f"Style: {request.get('preferences', {}).get('style', 'budget')}",
    ]

    hotels = state.get("hotel_options", [])
    if hotels:
        cheapest_hotel = min(hotels, key=lambda h: h.get("price_per_night_inr", 999999))
        parts.append(
            f"Cheapest hotel: {cheapest_hotel.get('name', 'N/A')} "
            f"at ₹{cheapest_hotel.get('price_per_night_inr', 0):,.0f}/night"
        )

    transport = state.get("transport_options", [])
    if transport:
        cheapest_transport = min(transport, key=lambda t: t.get("price_inr", 999999))
        parts.append(
            f"Cheapest transport: {cheapest_transport.get('type', 'bus')} "
            f"at ₹{cheapest_transport.get('price_inr', 0):,.0f} one-way"
        )

    return "\n".join(parts)


async def _generate_breakdown(
    context: str,
    total_budget: float,
    llm_router: LLMRouter,
    errors: list[str],
) -> dict | None:
    """Call LLM to generate budget breakdown JSON."""
    try:
        response = await llm_router.generate(
            prompt=f"Generate a budget breakdown for this trip. User budget: ₹{total_budget:,.0f}\n\n{context}",
            system=BUDGET_SYSTEM_PROMPT,
            temperature=0.2,
        )
        raw = _extract_json(response.content)
        breakdown = json.loads(raw)

        # Ensure required fields exist
        return {
            "transport_inr": float(breakdown.get("transport_inr", 0)),
            "accommodation_inr": float(breakdown.get("accommodation_inr", 0)),
            "food_inr": float(breakdown.get("food_inr", 0)),
            "activities_inr": float(breakdown.get("activities_inr", 0)),
            "misc_inr": float(breakdown.get("misc_inr", 0)),
            "total_inr": float(breakdown.get("total_inr", 0)),
            "is_within_budget": bool(breakdown.get("is_within_budget", True)),
            "savings_tips": list(breakdown.get("savings_tips", [])),
        }
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error("budget_parse_failed", error=str(exc)[:100])
        errors.append(f"Budget calculation failed: {exc}")
        # Return a fallback estimate
        transport_est = total_budget * 0.30
        hotel_est = total_budget * 0.35
        food_est = total_budget * 0.20
        activities_est = total_budget * 0.10
        misc_est = total_budget * 0.05
        total_est = transport_est + hotel_est + food_est + activities_est + misc_est
        return {
            "transport_inr": transport_est,
            "accommodation_inr": hotel_est,
            "food_inr": food_est,
            "activities_inr": activities_est,
            "misc_inr": misc_est,
            "total_inr": total_est,
            "is_within_budget": total_est <= total_budget,
            "savings_tips": ["Book transport in advance", "Choose budget guesthouses over hotels"],
        }


def _extract_json(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped the JSON."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        return match.group(0)
    return text
