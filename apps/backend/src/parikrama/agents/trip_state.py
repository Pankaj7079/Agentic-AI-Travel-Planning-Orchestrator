"""
TripPlanningState — the shared TypedDict for the Phase 4 multi-agent pipeline.

This is SEPARATE from AgentState (used by Phase 3 single agents).
It flows through the entire orchestration graph:
    OrchestratorAgent → [ResearchAgent ‖ BookingAgent] → BudgetOptimizer → ItineraryFinalizer
"""

from __future__ import annotations

from typing import Any, TypedDict


class TripRequest(TypedDict, total=False):
    """Structured trip request extracted by the OrchestratorAgent from raw user input."""

    origin: str  # Starting city (e.g., "Delhi")
    destination: str  # Target destination (e.g., "Manali")
    days: int  # Trip duration in days (1-30)
    budget_inr: float  # Total budget in Indian Rupees
    travelers: int  # Number of travelers (default: 1)
    preferences: dict[str, Any]  # {interests, food, style}
    language: str  # Detected language: "en", "hi", "hinglish"


class HotelOption(TypedDict, total=False):
    """A single hotel search result."""

    name: str
    location: str
    price_per_night_inr: float
    rating: float
    amenities: list[str]
    booking_url: str


class TransportOption(TypedDict, total=False):
    """A single transport search result."""

    type: str  # "bus", "train", "flight"
    operator: str
    origin: str
    destination: str
    price_inr: float
    duration_hours: float
    departure_time: str


class BudgetBreakdown(TypedDict, total=False):
    """Detailed cost breakdown produced by the BudgetOptimizer."""

    transport_inr: float
    accommodation_inr: float
    food_inr: float
    activities_inr: float
    misc_inr: float
    total_inr: float
    is_within_budget: bool
    savings_tips: list[str]


class DayPlan(TypedDict, total=False):
    """A single day's itinerary."""

    day: int
    title: str
    activities: list[dict[str, Any]]
    meals: list[dict[str, Any]]
    accommodation: dict[str, Any]
    estimated_cost_inr: float
    tips: list[str]


class AgentMessage(TypedDict):
    """A message logged by an agent node during execution."""

    agent: str
    content: str


class TripPlanningState(TypedDict, total=False):
    """
    Shared state dict flowing through the entire trip planning LangGraph.

    All fields are optional (total=False) to allow incremental population
    by each agent node. Agents read from upstream fields and write to their
    own output fields.
    """

    # ── Input ────────────────────────────────────────────────────────────────
    trip_id: str  # UUID of the Trip DB record
    user_id: str  # UUID of the authenticated user
    raw_input: str  # Original natural language request

    # ── Orchestrator outputs ─────────────────────────────────────────────────
    request: TripRequest  # Parsed structured trip request

    # ── Research Agent outputs ───────────────────────────────────────────────
    weather: dict[str, Any] | None  # Weather forecast + advisory
    destination_info: str  # RAG-retrieved travel knowledge
    places_of_interest: list[dict[str, Any]]  # Top places to visit
    reviews_summary: str  # LLM-synthesized research brief

    # ── Booking Agent outputs ────────────────────────────────────────────────
    hotel_options: list[HotelOption]  # Ranked hotel options
    transport_options: list[TransportOption]  # Ranked transport options
    requires_approval: bool  # True if any item > 50% of budget

    # ── Budget Optimizer outputs ─────────────────────────────────────────────
    budget_breakdown: BudgetBreakdown | None
    is_within_budget: bool

    # ── Final Itinerary outputs ──────────────────────────────────────────────
    itinerary: list[DayPlan]  # Day-by-day plan
    summary: str  # One-paragraph trip summary

    # ── Pipeline control ─────────────────────────────────────────────────────
    current_agent: str  # Name of the currently running agent
    status: str  # "planning" | "completed" | "failed" | "awaiting_approval"
    messages: list[AgentMessage]  # Audit trail of agent messages
    errors: list[str]  # Non-fatal errors (agent continues)
    approval_response: str | None  # Human approval decision (Phase 5)

    # ── Internal budget retry counter ────────────────────────────────────────
    _budget_retries: int
