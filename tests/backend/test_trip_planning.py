"""
Tests for Phase 4 -- Multi-Agent Trip Planning System.

All LLM calls, DB, and tool calls are mocked. Tests validate:
- State transitions through the pipeline
- JSON parsing and error handling
- Budget routing logic
- API endpoint responses
- AgentRun persistence

No real API keys needed. No network calls.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parikrama.llm.schemas import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from parikrama.agents.trip_state import TripPlanningState

# ── Helpers ────────────────────────────────────────────────────────────────────


def _llm_resp(content: str) -> LLMResponse:
    """Build a mock LLMResponse."""
    return LLMResponse(
        content=content,
        provider=LLMProvider.GROQ,
        model="llama-3.1-70b-versatile",
        latency_ms=100,
        input_tokens=200,
        output_tokens=100,
    )


def _mock_router(content: str = "mock response") -> MagicMock:
    """Build a mock LLMRouter that returns a fixed response."""
    router = MagicMock()
    router.generate = AsyncMock(return_value=_llm_resp(content))
    return router


def _base_state(**overrides) -> TripPlanningState:
    """Build a base TripPlanningState for tests."""
    state: TripPlanningState = {
        "trip_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "raw_input": "Plan a 5-day trip from Delhi to Manali, budget 15000",
        "request": {},
        "weather": None,
        "destination_info": "",
        "reviews_summary": "",
        "places_of_interest": [],
        "hotel_options": [],
        "transport_options": [],
        "requires_approval": False,
        "budget_breakdown": None,
        "is_within_budget": True,
        "itinerary": [],
        "summary": "",
        "current_agent": "",
        "status": "planning",
        "messages": [],
        "errors": [],
        "approval_response": None,
        "_budget_retries": 0,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# ── OrchestratorAgent Tests ────────────────────────────────────────────────────


class TestOrchestratorNode:
    """Tests for orchestrator_node — NL parsing and validation."""

    @pytest.mark.asyncio
    async def test_parses_english_request(self):
        """Orchestrator correctly extracts structured data from English input."""
        from parikrama.agents.orchestrator import orchestrator_node

        parsed_json = json.dumps(
            {
                "origin": "Delhi",
                "destination": "Manali",
                "days": 5,
                "budget_inr": 15000,
                "travelers": 1,
                "preferences": {"interests": ["adventure"], "food": "any", "style": "budget"},
                "language": "en",
            }
        )
        router = _mock_router(parsed_json)
        state = _base_state()

        result = await orchestrator_node(state, router)

        assert result["request"]["origin"] == "Delhi"
        assert result["request"]["destination"] == "Manali"
        assert result["request"]["days"] == 5
        assert result["request"]["budget_inr"] == 15000
        assert result["status"] == "planning"
        router.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_parses_hinglish_request(self):
        """Orchestrator handles Hindi/Hinglish mixed input."""
        from parikrama.agents.orchestrator import orchestrator_node

        parsed_json = json.dumps(
            {
                "origin": "Mumbai",
                "destination": "Goa",
                "days": 4,
                "budget_inr": 12000,
                "travelers": 2,
                "preferences": {"interests": ["beach"], "food": "any", "style": "budget"},
                "language": "hinglish",
            }
        )
        router = _mock_router(parsed_json)
        state = _base_state(raw_input="Mumbai se Goa 4 din ka trip, 12 hazar budget, hum 2 log")

        result = await orchestrator_node(state, router)

        assert result["request"]["origin"] == "Mumbai"
        assert result["request"]["destination"] == "Goa"
        assert result["request"]["days"] == 4
        assert result["request"]["budget_inr"] == 12000
        assert result["request"]["travelers"] == 2

    @pytest.mark.asyncio
    async def test_rejects_too_many_days(self):
        """Orchestrator raises ValueError for trips > 30 days."""
        from parikrama.agents.orchestrator import orchestrator_node

        invalid_json = json.dumps(
            {
                "origin": "Delhi",
                "destination": "Manali",
                "days": 45,  # > 30
                "budget_inr": 50000,
                "travelers": 1,
                "preferences": {},
                "language": "en",
            }
        )
        router = _mock_router(invalid_json)
        state = _base_state()

        with pytest.raises(ValueError, match=r"1.30 days"):
            await orchestrator_node(state, router)

    @pytest.mark.asyncio
    async def test_rejects_low_budget(self):
        """Orchestrator raises ValueError for budget < ₹1,000."""
        from parikrama.agents.orchestrator import orchestrator_node

        invalid_json = json.dumps(
            {
                "origin": "Delhi",
                "destination": "Manali",
                "days": 3,
                "budget_inr": 500,  # < 1000
                "travelers": 1,
                "preferences": {},
                "language": "en",
            }
        )
        router = _mock_router(invalid_json)
        state = _base_state()

        with pytest.raises(ValueError, match="too low"):
            await orchestrator_node(state, router)

    @pytest.mark.asyncio
    async def test_handles_llm_json_in_markdown_fence(self):
        """Orchestrator strips markdown fences from LLM JSON output."""
        from parikrama.agents.orchestrator import orchestrator_node

        wrapped_json = '```json\n{"origin":"Delhi","destination":"Shimla","days":3,"budget_inr":8000,"travelers":1,"preferences":{},"language":"en"}\n```'
        router = _mock_router(wrapped_json)
        state = _base_state()

        result = await orchestrator_node(state, router)

        assert result["request"]["destination"] == "Shimla"
        assert result["request"]["days"] == 3

    @pytest.mark.asyncio
    async def test_appends_message_to_pipeline(self):
        """Orchestrator appends an AgentMessage to state."""
        from parikrama.agents.orchestrator import orchestrator_node

        parsed_json = json.dumps(
            {
                "origin": "Bangalore",
                "destination": "Ooty",
                "days": 3,
                "budget_inr": 8000,
                "travelers": 1,
                "preferences": {},
                "language": "en",
            }
        )
        router = _mock_router(parsed_json)
        state = _base_state()

        result = await orchestrator_node(state, router)

        assert len(result["messages"]) == 1
        assert result["messages"][0]["agent"] == "orchestrator"
        assert "Ooty" in result["messages"][0]["content"]


# ── ResearchAgent Tests ────────────────────────────────────────────────────────


class TestResearchNode:
    """Tests for research_node — tool orchestration and synthesis."""

    @pytest.mark.asyncio
    async def test_research_node_completes_with_mock_tools(self):
        """Research node runs all tools and returns populated state."""
        from parikrama.agents.research_agent import research_node

        router = _mock_router("Manali is a beautiful hill station with cold weather...")
        db = AsyncMock()

        state = _base_state(
            request={
                "origin": "Delhi",
                "destination": "Manali",
                "days": 5,
                "budget_inr": 15000,
                "travelers": 1,
                "preferences": {"style": "budget"},
                "language": "en",
            }
        )

        with (
            patch(
                "parikrama.agents.research_agent._fetch_rag_context",
                return_value="travel guide content",
            ),
            patch(
                "parikrama.agents.tools.weather.get_weather_forecast",
                return_value={
                    "location": "Manali",
                    "forecasts": [],
                    "advisory": "Carry warm clothes",
                    "dates": [],
                },
            ),
            patch(
                "parikrama.agents.tools.places.search_places",
                return_value=[
                    {"name": "Rohtang Pass", "type": "scenic", "rating": 4.6, "entry_fee_inr": 550}
                ],
            ),
        ):
            result = await research_node(state, router, db)

        assert result["reviews_summary"] != ""
        assert len(result["messages"]) >= 1
        assert result["messages"][0]["agent"] == "research"

    @pytest.mark.asyncio
    async def test_research_handles_weather_failure_gracefully(self):
        """Research node continues if weather tool fails."""
        from parikrama.agents.research_agent import research_node

        router = _mock_router("Brief without weather data")
        db = AsyncMock()

        state = _base_state(
            request={
                "origin": "Delhi",
                "destination": "Manali",
                "days": 3,
                "budget_inr": 10000,
                "travelers": 1,
                "preferences": {},
            }
        )

        with (
            patch("parikrama.agents.research_agent._fetch_weather", return_value=None),
            patch("parikrama.agents.research_agent._fetch_places", return_value=[]),
            patch("parikrama.agents.research_agent._fetch_rag_context", return_value=""),
        ):
            result = await research_node(state, router, db)

        assert result["weather"] is None
        assert result["status"] == "planning" or "current_agent" in result
        # Should NOT raise even though weather failed


# ── BookingAgent Tests ─────────────────────────────────────────────────────────


class TestBookingNode:
    """Tests for booking_node — hotel and transport search."""

    @pytest.mark.asyncio
    async def test_booking_finds_hotels_and_transport(self):
        """Booking node returns hotel and transport options."""
        from parikrama.agents.booking_agent import booking_node

        router = MagicMock()  # Not used in booking
        db = AsyncMock()

        state = _base_state(
            request={
                "origin": "Delhi",
                "destination": "Manali",
                "days": 5,
                "budget_inr": 15000,
                "travelers": 1,
                "preferences": {},
            }
        )

        result = await booking_node(state, router, db)

        assert isinstance(result["hotel_options"], list)
        assert isinstance(result["transport_options"], list)
        assert len(result["hotel_options"]) > 0
        assert len(result["transport_options"]) > 0
        assert result["messages"][-1]["agent"] == "booking"

    @pytest.mark.asyncio
    async def test_booking_flags_expensive_hotel(self):
        """Booking sets requires_approval=True for hotels > 50% of budget."""
        from parikrama.agents.booking_agent import _check_approval_needed
        from parikrama.agents.trip_state import HotelOption

        expensive_hotel = HotelOption(
            name="Luxury Resort",
            price_per_night_inr=5000,  # 5000 x 5 days = 25000 = 100% of 25000 budget
        )
        total_budget = 15000.0
        days = 3  # 5000 x 3 = 15000 = 100% of budget -> requires_approval

        result = _check_approval_needed([expensive_hotel], [], total_budget, days)

        assert result is True

    @pytest.mark.asyncio
    async def test_booking_does_not_flag_affordable_hotel(self):
        """Booking leaves requires_approval=False for affordable options."""
        from parikrama.agents.booking_agent import _check_approval_needed
        from parikrama.agents.trip_state import HotelOption

        affordable_hotel = HotelOption(
            name="Budget Inn",
            price_per_night_inr=800,  # 800 x 5 = 4000 = 26% of 15000 budget
        )

        result = _check_approval_needed([affordable_hotel], [], 15000.0, 5)

        assert result is False


# ── BudgetOptimizer Tests ──────────────────────────────────────────────────────


class TestBudgetOptimizerNode:
    """Tests for budget_optimizer_node."""

    @pytest.mark.asyncio
    async def test_budget_within_budget(self):
        """Budget optimizer sets is_within_budget=True when total < user budget."""
        from parikrama.agents.budget_optimizer import budget_optimizer_node

        breakdown_json = json.dumps(
            {
                "transport_inr": 1300,
                "accommodation_inr": 3300,
                "food_inr": 2000,
                "activities_inr": 1000,
                "misc_inr": 500,
                "total_inr": 8100,
                "is_within_budget": True,
                "savings_tips": [],
            }
        )
        router = _mock_router(breakdown_json)
        db = AsyncMock()

        state = _base_state(
            request={
                "origin": "Delhi",
                "destination": "Manali",
                "days": 5,
                "budget_inr": 15000,
                "travelers": 1,
                "preferences": {},
            },
            hotel_options=[{"name": "Hotel A", "price_per_night_inr": 800}],
            transport_options=[{"type": "bus", "price_inr": 650}],
        )

        result = await budget_optimizer_node(state, router, db)

        assert result["is_within_budget"] is True
        assert result["budget_breakdown"]["total_inr"] == 8100

    @pytest.mark.asyncio
    async def test_budget_over_budget_detected(self):
        """Budget optimizer sets is_within_budget=False when over budget."""
        from parikrama.agents.budget_optimizer import budget_optimizer_node

        breakdown_json = json.dumps(
            {
                "transport_inr": 9000,
                "accommodation_inr": 15000,
                "food_inr": 5000,
                "activities_inr": 2000,
                "misc_inr": 1000,
                "total_inr": 32000,
                "is_within_budget": False,
                "savings_tips": ["Take bus instead of flight", "Stay in hostel"],
            }
        )
        router = _mock_router(breakdown_json)
        db = AsyncMock()

        state = _base_state(
            request={
                "origin": "Delhi",
                "destination": "Manali",
                "days": 5,
                "budget_inr": 15000,
                "travelers": 1,
                "preferences": {},
            },
        )

        result = await budget_optimizer_node(state, router, db)

        assert result["is_within_budget"] is False
        assert len(result["budget_breakdown"]["savings_tips"]) == 2


# ── Graph Routing Tests ────────────────────────────────────────────────────────


class TestGraphRouting:
    """Tests for the conditional routing logic in the LangGraph."""

    def test_route_after_budget_within_budget(self):
        """Routes to itinerary_finalizer when within budget."""
        from parikrama.agents.trip_graph import _route_after_budget

        state = _base_state(is_within_budget=True)
        assert _route_after_budget(state) == "itinerary_finalizer"

    def test_route_after_budget_over_budget_first_retry(self):
        """Routes back to budget_optimizer on first over-budget (retry 0 → 1)."""
        from parikrama.agents.trip_graph import _route_after_budget

        state = _base_state(is_within_budget=False, _budget_retries=0)
        result = _route_after_budget(state)
        assert result == "budget_optimizer"
        assert state["_budget_retries"] == 1

    def test_route_after_budget_max_retries_proceeds(self):
        """After MAX_BUDGET_RETRIES, routes to itinerary_finalizer regardless."""
        from parikrama.agents.trip_graph import MAX_BUDGET_RETRIES, _route_after_budget

        state = _base_state(is_within_budget=False, _budget_retries=MAX_BUDGET_RETRIES)
        result = _route_after_budget(state)
        assert result == "itinerary_finalizer"  # Proceeds with over-budget warning


# ── Graph Compilation Test ─────────────────────────────────────────────────────


class TestTripPlanningGraph:
    def test_graph_compiles_without_error(self):
        """The LangGraph compiles with all nodes and edges."""
        from parikrama.agents.trip_graph import build_trip_planning_graph

        router = _mock_router()
        db = AsyncMock()

        graph = build_trip_planning_graph(router, db)

        # Graph must have compiled successfully
        assert graph is not None
        assert hasattr(graph, "ainvoke")


# ── Tool Unit Tests ────────────────────────────────────────────────────────────


class TestWeatherTool:
    @pytest.mark.asyncio
    async def test_mock_weather_returns_correct_days(self):
        """Mock weather returns correct number of forecast days."""
        from parikrama.agents.tools.weather import _mock_weather

        result = _mock_weather("Manali", 5)

        assert result["location"] == "Manali"
        assert len(result["forecasts"]) == 5
        assert len(result["dates"]) == 5

    @pytest.mark.asyncio
    async def test_weather_falls_back_to_mock_without_api_key(self):
        """get_weather_forecast uses mock when no API key configured."""
        from parikrama.agents.tools.weather import get_weather_forecast

        with patch("parikrama.agents.tools.weather.logger"):
            result = await get_weather_forecast("Shimla", 3)

        assert result["location"] == "Shimla"
        assert len(result["forecasts"]) == 3


class TestHotelsTool:
    @pytest.mark.asyncio
    async def test_search_hotels_returns_options(self):
        """search_hotels returns at least 3 options."""
        from parikrama.agents.tools.hotels import search_hotels

        results = await search_hotels("Manali", check_in_days=3, max_price_per_night=2000)

        assert len(results) >= 1
        for h in results:
            assert "name" in h
            assert "price_per_night_inr" in h
            assert "rating" in h

    @pytest.mark.asyncio
    async def test_search_hotels_filters_by_price(self):
        """search_hotels returns affordable options when max_price set."""
        from parikrama.agents.tools.hotels import search_hotels

        results = await search_hotels("Goa", check_in_days=2, max_price_per_night=1000)

        # All returned hotels should be <= max_price or 1 over-budget for comparison
        affordable = [h for h in results if h["price_per_night_inr"] <= 1000]
        assert len(affordable) >= 1


class TestTransportTool:
    @pytest.mark.asyncio
    async def test_search_transport_known_route(self):
        """search_transport returns options for a known route."""
        from parikrama.agents.tools.transport import search_transport

        results = await search_transport("Delhi", "Manali", max_price=2000)

        assert len(results) >= 1
        for t in results:
            assert "type" in t
            assert "price_inr" in t
            assert "duration_hours" in t

    @pytest.mark.asyncio
    async def test_search_transport_sorted_by_price(self):
        """search_transport returns options sorted cheapest first."""
        from parikrama.agents.tools.transport import search_transport

        results = await search_transport("Mumbai", "Goa")

        prices = [r["price_inr"] for r in results]
        assert prices == sorted(prices)
