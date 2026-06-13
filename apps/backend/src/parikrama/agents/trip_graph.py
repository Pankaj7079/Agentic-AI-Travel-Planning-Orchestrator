"""
TripPlanningGraph — the LangGraph orchestration pipeline for PariKrama.

Graph flow:
    orchestrator → [research ‖ booking] → budget_optimizer → itinerary_finalizer → END

Key design decisions:
- Research and Booking run in PARALLEL (fan-out via separate edges, fan-in at budget)
- LangGraph handles fan-in: budget_optimizer waits for BOTH before executing
- BudgetOptimizer has a conditional edge: retry if over budget (max 2 times)
- All agent node functions receive (state, llm_router, db) via functools.partial
- No LangGraph checkpointing in Phase 4 (added in Phase 5 for HITL support)
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

import structlog
from langgraph.graph import END, StateGraph

from parikrama.agents.booking_agent import booking_node
from parikrama.agents.budget_optimizer import budget_optimizer_node
from parikrama.agents.final_itinerary_agent import itinerary_finalizer_node
from parikrama.agents.orchestrator import orchestrator_node
from parikrama.agents.research_agent import research_node
from parikrama.agents.trip_state import TripPlanningState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

MAX_BUDGET_RETRIES = 2


# ── Conditional edge router ────────────────────────────────────────────────────


def _route_after_budget(state: TripPlanningState) -> str:
    """
    Conditional edge after budget_optimizer:
    - is_within_budget=True  → proceed to itinerary_finalizer
    - is_within_budget=False → retry budget optimization (max MAX_BUDGET_RETRIES times)
    """
    if state.get("is_within_budget", True):
        return "itinerary_finalizer"

    retries = state.get("_budget_retries", 0)
    if retries >= MAX_BUDGET_RETRIES:
        logger.warning(
            "budget_max_retries_reached",
            trip_id=state.get("trip_id"),
            retries=retries,
        )
        return "itinerary_finalizer"  # proceed with over-budget warning

    # Increment retry counter in state (LangGraph state is immutable — returned as new dict)
    state["_budget_retries"] = retries + 1  # type: ignore[literal-required]
    logger.info("budget_retry", attempt=retries + 1, max=MAX_BUDGET_RETRIES)
    return "budget_optimizer"


# ── Graph factory ──────────────────────────────────────────────────────────────


def build_trip_planning_graph(
    llm_router: LLMRouter,
    db: AsyncSession,
) -> CompiledStateGraph:
    """
    Build and compile the trip planning LangGraph.

    Args:
        llm_router: Shared LLMRouter instance (Gemini + Groq with circuit breaker).
        db: AsyncSession for RAG and DB operations.

    Returns:
        Compiled StateGraph ready for `await graph.ainvoke(state)`.
    """
    graph = StateGraph(TripPlanningState)

    # ── Bind dependencies to each node function ──────────────────────────────
    # Each node receives (state, llm_router, db) — we use partial to pre-bind
    # the dependencies so LangGraph only sees (state,) as required.

    _orchestrator = functools.partial(orchestrator_node, llm_router=llm_router)
    _research = functools.partial(research_node, llm_router=llm_router, db=db)
    _booking = functools.partial(booking_node, llm_router=llm_router, db=db)
    _budget = functools.partial(budget_optimizer_node, llm_router=llm_router, db=db)
    _itinerary = functools.partial(itinerary_finalizer_node, llm_router=llm_router, db=db)

    # ── Add nodes ────────────────────────────────────────────────────────────
    graph.add_node("orchestrator", _orchestrator)
    graph.add_node("research", _research)
    graph.add_node("booking", _booking)
    graph.add_node("budget_optimizer", _budget)
    graph.add_node("itinerary_finalizer", _itinerary)

    # ── Define edges (the flow) ──────────────────────────────────────────────
    graph.set_entry_point("orchestrator")

    # Fan-out: orchestrator → research AND booking (run in parallel)
    graph.add_edge("orchestrator", "research")
    graph.add_edge("orchestrator", "booking")

    # Fan-in: both research and booking → budget_optimizer
    # LangGraph waits for ALL incoming edges before executing the next node
    graph.add_edge("research", "budget_optimizer")
    graph.add_edge("booking", "budget_optimizer")

    # Conditional: budget_optimizer → itinerary_finalizer or retry
    graph.add_conditional_edges(
        "budget_optimizer",
        _route_after_budget,
        {
            "itinerary_finalizer": "itinerary_finalizer",
            "budget_optimizer": "budget_optimizer",
        },
    )

    # Terminal: itinerary_finalizer → END
    graph.add_edge("itinerary_finalizer", END)

    compiled = graph.compile()
    logger.info(
        "trip_planning_graph_compiled",
        nodes=["orchestrator", "research", "booking", "budget_optimizer", "itinerary_finalizer"],
    )
    return compiled
