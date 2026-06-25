"""
Trip schemas — request/response models for trip planning endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ── Requests ──────────────────────────────────────────────────────────


class TripPreferences(BaseModel):
    """Optional user preferences for trip customization."""

    interests: list[str] = []  # ["trekking", "temple", "food"]
    food_preference: str = "any"  # "veg" | "non-veg" | "any"
    accommodation_type: str = "any"  # "hotel" | "hostel" | "homestay" | "any"
    transport_preference: str = "any"  # "bus" | "train" | "flight" | "any"
    pace: str = "moderate"  # "relaxed" | "moderate" | "packed"
    special_requirements: str = ""  # "wheelchair accessible", etc.
    language: str = "en"  # "en" | "hi"


class CreateTripRequest(BaseModel):
    """Create a new trip planning request."""

    origin: str = Field(min_length=2, max_length=100, examples=["Delhi"])
    destination: str = Field(min_length=2, max_length=100, examples=["Manali"])
    days: int = Field(ge=1, le=30, examples=[5])
    budget_inr: int = Field(ge=500, le=10_000_000, examples=[15000])
    travelers: int = Field(ge=1, le=20, default=1)
    start_date: str | None = Field(default=None, examples=["2024-12-25"])
    preferences: TripPreferences = Field(default_factory=TripPreferences)


class VoiceTripRequest(BaseModel):
    """Trip created from voice input — raw transcript provided."""

    transcript: str = Field(min_length=5)
    language: str = "en"


# ── Responses ─────────────────────────────────────────────────────────


class TransportOptionResponse(BaseModel):
    """Transport option in trip response."""

    type: str  # "bus" | "train" | "flight"
    operator: str
    departure: str
    arrival: str
    price_inr: int
    duration_hours: float
    transport_class: str | None = None  # "sleeper", "3A", "economy", etc.
    source: str


class HotelOptionResponse(BaseModel):
    """Hotel option in trip response."""

    name: str
    price_per_night_inr: int
    rating: float
    location: str
    type: str | None = None
    amenities: list[str]
    booking_url: str | None = None
    source: str


class BudgetBreakdownResponse(BaseModel):
    """Cost breakdown from budget agent."""

    transport_inr: int
    accommodation_inr: int
    food_inr: int
    activities_inr: int
    misc_inr: int
    total_inr: int
    savings_tips: list[str]


class DayPlanResponse(BaseModel):
    """A single day in the itinerary."""

    day: int
    date: str | None
    title: str
    activities: list[dict]
    meals: list[dict]
    accommodation: dict
    travel: dict | None = None
    tips: list[str]


class TripResultResponse(BaseModel):
    """Full trip planning result."""

    hotel_options: list[HotelOptionResponse]
    transport_options: list[TransportOptionResponse]
    budget_breakdown: BudgetBreakdownResponse | None
    itinerary: list[DayPlanResponse]
    summary: str


class TripResponse(BaseModel):
    """Trip resource — minimal view for listing."""

    id: UUID
    status: str
    request: dict
    result: dict | None
    created_at: datetime
    updated_at: datetime
    planning_duration_ms: int | None
    total_cost_usd: float

    model_config = {"from_attributes": True}


class TripDetailResponse(TripResponse):
    """Full trip detail including agent run history."""

    agent_runs: list[dict] = []


class AgentRunResponse(BaseModel):
    """Individual agent execution record."""

    id: UUID
    agent_name: str
    status: str
    tokens_used: int
    duration_ms: int | None
    # BUG-06 fix: these were in the model but missing from schema
    input_summary: str | None = None
    output_summary: str | None = None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class TripStatusResponse(BaseModel):
    """Live trip planning status — sent via WebSocket / polling."""

    trip_id: str
    status: str
    current_agent: str | None
    progress_percent: int
    message: str
    is_complete: bool
    # BUG-01 fix: these were returned by the service but missing from schema
    approval_id: str | None = None
    has_result: bool = False
    error: str | None = None  # Error details when status="failed"
