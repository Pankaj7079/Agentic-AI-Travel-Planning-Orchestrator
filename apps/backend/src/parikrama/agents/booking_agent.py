"""
BookingAgent — finds accommodation and transport options for a trip.

Runs 2 tools concurrently (asyncio.gather):
    1. Hotel search (mock with realistic Indian pricing)
    2. Transport search (bus/train/flight options)

Sets `requires_approval=True` if any option exceeds 50% of total budget.
Runs in PARALLEL with ResearchAgent in the LangGraph graph.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from parikrama.agents.tools.hotels import search_hotels
from parikrama.agents.tools.transport import search_transport
from parikrama.agents.trip_state import (
    AgentMessage,
    HotelOption,
    TransportOption,
    TripPlanningState,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)


async def booking_node(
    state: TripPlanningState,
    llm_router: LLMRouter,
    db: AsyncSession,  # accepted for interface consistency (unused)
) -> TripPlanningState:
    """
    LangGraph node: find accommodation and transport options.

    Args:
        state: Current pipeline state (must have `request` from orchestrator).
        llm_router: Not used directly — kept for interface consistency.
        db: Not used — kept for interface consistency.

    Returns:
        Updated state with hotel_options, transport_options, requires_approval.
    """
    log = logger.bind(agent="booking", trip_id=state.get("trip_id"))
    log.info("booking_started")

    request = state.get("request", {})
    origin = request.get("origin", "")
    destination = request.get("destination", "")
    days = request.get("days", 3)
    total_budget = float(request.get("budget_inr", 10000))
    errors: list[str] = []  # only NEW errors from this node

    # Broadcast to WebSocket
    from parikrama.api.websocket.manager import ws_manager

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="booking",
        status="running",
        message=f"Booking Agent started: Searching hotels and transport options from {origin} to {destination}...",
    )

    # Allocate budget portions for search filtering
    transport_budget = total_budget * 0.35  # ~35% for transport
    hotel_budget_per_night = (total_budget * 0.35) / max(days, 1)  # ~35% for hotel

    # ── Run hotel + transport search concurrently ─────────────────────────────
    hotels_result, transport_result = await asyncio.gather(
        _search_hotels_safe(destination, days, hotel_budget_per_night, errors, llm_router),
        _search_transport_safe(origin, destination, transport_budget, errors, llm_router),
    )

    # ── Flag expensive items requiring approval ───────────────────────────────
    # Skip approval check if pipeline was resumed after a previous approval
    approval_response = state.get("approval_response")
    if approval_response and "approved" in str(approval_response).lower():
        requires_approval = False
        log.info("approval_already_granted", trip_id=state.get("trip_id"))
    else:
        requires_approval = _check_approval_needed(hotels_result, transport_result, total_budget, days)

    # Only return NEW messages — LangGraph's operator.add reducer concatenates
    # them onto the existing list. Returning the full list causes duplication
    # when parallel nodes (research + booking) both read and extend it.
    new_messages: list[AgentMessage] = [
        AgentMessage(
            agent="booking",
            content=(
                f"Found {len(hotels_result)} hotel options and "
                f"{len(transport_result)} transport options. "
                f"{'Approval needed for expensive items.' if requires_approval else 'All within budget.'}"
            ),
        )
    ]

    log.info(
        "booking_completed",
        hotels=len(hotels_result),
        transport=len(transport_result),
        requires_approval=requires_approval,
    )

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="booking",
        status="completed",
        message=f"Booking complete: found {len(hotels_result)} hotels and {len(transport_result)} transport options. "
        + (
            "Requires approval for higher-tier options."
            if requires_approval
            else "All options within budget."
        ),
    )

    return {
        # ONLY return keys this node writes — do NOT spread **state
        # Same fix as research_node: parallel nodes must not write to shared keys.
        "hotel_options": hotels_result,
        "transport_options": transport_result,
        "requires_approval": requires_approval,
        "current_agent": "booking",
        "messages": new_messages,
        "errors": errors,
    }


# ── Private helpers ────────────────────────────────────────────────────────────


async def _search_hotels_safe(
    destination: str,
    nights: int,
    max_per_night: float,
    errors: list[str],
    llm_router: LLMRouter | None = None,
) -> list[HotelOption]:
    """Search hotels with error capture. Returns exactly 3 options: budget, mid, premium."""
    try:
        results = await search_hotels(destination, nights, max_per_night, llm_router=llm_router)
        hotels = [
            HotelOption(**{k: v for k, v in h.items() if k in HotelOption.__annotations__})
            for h in results
        ]
        # Ensure exactly 3 options: budget, mid, premium
        if len(hotels) >= 3:
            # Pick cheapest, middle, most expensive
            sorted_by_price = sorted(hotels, key=lambda h: h.get("price_per_night_inr", 0))
            return [
                sorted_by_price[0],
                sorted_by_price[len(sorted_by_price) // 2],
                sorted_by_price[-1],
            ]
        return hotels[:3]
    except Exception as exc:
        logger.warning("hotel_search_error", error=str(exc)[:100])
        errors.append(f"Hotel search failed: {exc}")
        return []


async def _search_transport_safe(
    origin: str,
    destination: str,
    max_price: float,
    errors: list[str],
    llm_router: LLMRouter | None = None,
) -> list[TransportOption]:
    """Search transport with error capture. Returns exactly 3 options: bus, train, flight (or cheapest 3)."""
    try:
        results = await search_transport(origin, destination, max_price, llm_router=llm_router)
        transport = [
            TransportOption(**{k: v for k, v in t.items() if k in TransportOption.__annotations__})
            for t in results
        ]
        # Ensure exactly 3 options: pick by type diversity if possible
        if len(transport) >= 3:
            # Try to get one of each type: bus, train, flight
            by_type: dict[str, TransportOption] = {}
            for t in transport:
                t_type = t.get("type", "")
                if t_type not in by_type:
                    by_type[t_type] = t
            if len(by_type) >= 3:
                return list(by_type.values())[:3]
            # Fallback: cheapest 3
            sorted_by_price = sorted(transport, key=lambda t: t.get("price_inr", 0))
            return sorted_by_price[:3]
        return transport[:3]
    except Exception as exc:
        logger.warning("transport_search_error", error=str(exc)[:100])
        errors.append(f"Transport search failed: {exc}")
        return []


def _check_approval_needed(
    hotels: list[HotelOption],
    transport: list[TransportOption],
    total_budget: float,
    days: int,
) -> bool:
    """Return True if any single option costs more than 50% of total budget."""
    threshold = total_budget * 0.5

    for hotel in hotels:
        total_hotel_cost = float(hotel.get("price_per_night_inr", 0)) * days
        if total_hotel_cost > threshold:
            logger.info(
                "expensive_hotel_flagged",
                hotel=hotel.get("name"),
                total_cost=total_hotel_cost,
                threshold=threshold,
            )
            return True

    for t_option in transport:
        if float(t_option.get("price_inr", 0)) > threshold:
            logger.info(
                "expensive_transport_flagged",
                transport_type=t_option.get("type"),
                price=t_option.get("price_inr"),
                threshold=threshold,
            )
            return True

    return False
