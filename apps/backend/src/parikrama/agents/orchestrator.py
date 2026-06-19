"""
OrchestratorAgent — the entry point of the PariKrama multi-agent pipeline.

Responsibilities:
1. Parse natural language input (English / Hindi / Hinglish) → TripRequest
2. Validate: days 1-30, budget >= Rs.1,000, origin + destination present
3. Enrich initial TripPlanningState for downstream agents

This is a graph NODE function (not a self-contained graph like Phase 3 agents).
It is called by LangGraph with the current TripPlanningState.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

from parikrama.agents.trip_state import AgentMessage, TripPlanningState, TripRequest

if TYPE_CHECKING:
    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

ORCHESTRATOR_SYSTEM_PROMPT = """You are the Orchestrator Agent for PariKrama, an Indian travel planning system.

Your job: parse the user's travel request into a structured JSON object.
The user may write in English, Hindi, or Hinglish (mixed language).

Extract these fields:
- origin: starting city (string)
- destination: target city/place (string)
- days: number of days as integer (1-30)
- budget_inr: total budget in Indian Rupees as number
- travelers: number of travelers as integer (default: 1)
- preferences: object with {interests: list, food: string, style: "budget"|"mid"|"premium"}
- language: detected language code "en", "hi", or "hinglish"

Important parsing rules:
- If budget has no currency → assume INR
- "5 din" = 5 days, "ek hafte" = 7 days
- "sasta" = budget style, "accha hotel" = mid style
- "family trip" or "hum 4 log" → multiple travelers
- "15k", "15 hazar", "fifteen thousand" → 15000
- "Mumbai se Goa" → origin: Mumbai, destination: Goa
- Remove "trip", "travel", "jaana hai" etc. from place names

Return ONLY valid JSON with no markdown fencing, no explanation.

Example:
{"origin":"Delhi","destination":"Manali","days":5,"budget_inr":15000,"travelers":1,"preferences":{"interests":["sightseeing","adventure"],"food":"any","style":"budget"},"language":"en"}"""


async def orchestrator_node(
    state: TripPlanningState,
    llm_router: LLMRouter,
) -> TripPlanningState:
    """
    LangGraph node: parse raw input → structured TripRequest.

    Args:
        state: Current pipeline state (must have raw_input, trip_id, user_id).
        llm_router: LLMRouter instance injected by the graph builder.

    Returns:
        Updated state with `request` populated and `status` set to "planning".
    """
    log = logger.bind(agent="orchestrator", trip_id=state.get("trip_id"))
    log.info("orchestrator_started", raw_input=state.get("raw_input", "")[:80])

    raw_input = state.get("raw_input", "").strip()
    if not raw_input:
        raise ValueError("raw_input is empty — cannot parse trip request")

    # Broadcast to WebSocket
    from parikrama.api.websocket.manager import ws_manager
    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="orchestrator",
        status="running",
        message="Orchestrator Agent starting: Parsing natural language request...",
    )

    # Call LLM to extract structured intent
    response = await llm_router.generate(
        prompt=f"Parse this travel request into the required JSON:\n\n{raw_input}",
        system=ORCHESTRATOR_SYSTEM_PROMPT,
        temperature=0.1,  # Low temperature — deterministic parsing
    )

    # Extract JSON (strip any accidental markdown)
    raw_json = _extract_json(response.content)

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        log.error("orchestrator_json_parse_failed", error=str(exc), raw=response.content[:300])
        await ws_manager.broadcast_agent_update(
            user_id=state["user_id"],
            trip_id=state["trip_id"],
            agent="orchestrator",
            status="failed",
            message="Orchestrator Agent failed to parse request.",
        )
        raise ValueError(f"OrchestratorAgent: LLM returned invalid JSON: {exc}") from exc

    # Build typed TripRequest
    trip_request: TripRequest = {
        "origin": str(parsed.get("origin", "")).strip(),
        "destination": str(parsed.get("destination", "")).strip(),
        "days": int(parsed.get("days", 3)),
        "budget_inr": float(parsed.get("budget_inr", 10000)),
        "travelers": int(parsed.get("travelers", 1)),
        "preferences": parsed.get(
            "preferences", {"interests": [], "food": "any", "style": "budget"}
        ),
        "language": str(parsed.get("language", "en")),
    }

    # Validation
    _validate_trip_request(trip_request)

    # Return only new messages — Annotated[list, operator.add] concatenates.
    new_messages: list[AgentMessage] = [
        AgentMessage(
            agent="orchestrator",
            content=(
                f"Parsed: {trip_request['days']}-day trip from {trip_request['origin']} "
                f"to {trip_request['destination']}, budget ₹{trip_request['budget_inr']:,.0f}, "
                f"{trip_request['travelers']} traveler(s)"
            ),
        )
    ]

    log.info(
        "orchestrator_completed",
        origin=trip_request["origin"],
        destination=trip_request["destination"],
        days=trip_request["days"],
        budget=trip_request["budget_inr"],
    )

    await ws_manager.broadcast_agent_update(
        user_id=state["user_id"],
        trip_id=state["trip_id"],
        agent="orchestrator",
        status="completed",
        message=f"Orchestration parsed request: {trip_request['days']}-day trip from {trip_request['origin']} to {trip_request['destination']}.",
    )

    return {
        **state,
        "request": trip_request,
        "current_agent": "orchestrator",
        "status": "planning",
        "messages": new_messages,  # only new — LangGraph adds to existing
        "errors": [],              # no new errors from orchestrator at this point
    }


# ── Private helpers ────────────────────────────────────────────────────────────


def _extract_json(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped the JSON."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    # Try to find the first { ... } block
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        return match.group(0)
    return text


def _validate_trip_request(req: TripRequest) -> None:
    """Validate extracted TripRequest fields."""
    errors = []

    if not req.get("origin"):
        errors.append("Could not determine the starting city (origin)")
    if not req.get("destination"):
        errors.append("Could not determine the destination")

    days = req.get("days", 0)
    if not (1 <= days <= 30):
        errors.append(f"Trip duration must be 1-30 days, got {days}")

    budget = req.get("budget_inr", 0)
    if budget < 1000:
        errors.append(f"Budget ₹{budget:,.0f} is too low — minimum ₹1,000 required")

    if errors:
        raise ValueError("Invalid trip request: " + "; ".join(errors))
