# Phase 4: Multi-Agent System (LangGraph)

## Overview

Phase 4 is the **brain** of PariKrama — the multi-agent orchestration system powered by LangGraph. This is where a user's request like *"Delhi to Manali, 5 days, ₹15,000 budget"* transforms into a comprehensive, validated, day-by-day travel itinerary.

### The Agent Team
| Agent | Role | Tools | Runs In |
|-------|------|-------|---------|
| **Orchestrator** | Parses intent, routes work, synthesizes results | NLP parsing | Always first |
| **Research** | Gathers weather, places, reviews | Weather API, Google Places, RAG | Parallel with Booking |
| **Booking** | Finds hotels and transport | Hotel APIs, Transport APIs | Parallel with Research |
| **Budget** | Optimizes costs, checks feasibility | Calculator, RAG (budget tips) | After Research + Booking |
| **Itinerary** | Generates final day-by-day plan | PDF generator | Last agent |

### LangGraph Flow
```
User Request
    ↓
[Orchestrator] → parse intent, validate
    ↓
[Research] ←→ [Booking]   ← run in PARALLEL
    ↓            ↓
    └────┬───────┘
         ↓
     [Budget] → check if within budget
         ↓
    ┌─── budget_ok? ───┐
    ↓ YES              ↓ NO
[Itinerary]    [Budget re-optimize]
    ↓                  ↓
  DONE          [Itinerary] → DONE
```

---

## Architecture Decisions

### Decision 1: LangGraph vs CrewAI
| Feature | LangGraph | CrewAI |
|---------|-----------|--------|
| State management | TypedDict (explicit) | Agent memory (implicit) |
| Flow control | Graph edges + conditionals | Sequential/hierarchical |
| Persistence | Built-in checkpointing | None |
| Human-in-the-loop | `interrupt_before` built-in | Manual implementation |
| Parallel execution | Fan-out/fan-in built-in | Limited |

**Why LangGraph:** Explicit state management via TypedDict means we know exactly what data flows between agents. Built-in checkpointing lets us pause for human approval (Phase 5) and resume later. CrewAI is simpler but lacks the persistence and interrupt primitives we need.

### Decision 2: Parallel vs Sequential Agent Execution
**Research and Booking run in parallel** because they're independent — weather data doesn't depend on hotel availability. This cuts total planning time nearly in half. Budget runs after both because it needs their outputs.

---

## Database Schema

```sql
-- ══════════════════════════════════════════════════════════════════════
-- Phase 4 Database Tables
-- ══════════════════════════════════════════════════════════════════════

-- ── Trips ──────────────────────────────────────────────────────────
CREATE TABLE trips (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    -- pending → planning → awaiting_approval → completed | cancelled | failed

    -- original request
    request JSONB NOT NULL,
    -- {origin, destination, days, budget_inr, travelers, preferences}

    -- generated result
    result JSONB,
    -- {itinerary: [...], budget_breakdown: {...}, summary: "..."}

    -- metadata
    thread_id VARCHAR(64) UNIQUE,         -- LangGraph thread ID for state persistence
    total_tokens_used INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(10, 6) DEFAULT 0,
    planning_duration_ms INTEGER,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_trips_user ON trips(user_id);
CREATE INDEX idx_trips_status ON trips(status);
CREATE INDEX idx_trips_thread ON trips(thread_id);

-- ── Agent Runs (individual agent executions) ───────────────────────
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trip_id UUID NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    agent_name VARCHAR(30) NOT NULL,      -- 'orchestrator', 'research', etc.
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    -- queued → running → completed | failed | interrupted

    input_summary TEXT,                    -- abbreviated input for debugging
    output_summary TEXT,                   -- abbreviated output
    tokens_used INTEGER DEFAULT 0,
    duration_ms INTEGER,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_runs_trip ON agent_runs(trip_id);
CREATE INDEX idx_agent_runs_agent ON agent_runs(agent_name);
```

---

## Key APIs

```
POST   /api/v1/trips                   Start a new trip planning session
GET    /api/v1/trips                   List user's trips (paginated)
GET    /api/v1/trips/{id}              Get trip details + status
GET    /api/v1/trips/{id}/status       Real-time status (polling alternative to WS)
DELETE /api/v1/trips/{id}              Cancel an in-progress trip
GET    /api/v1/trips/{id}/agents       Get agent run history for a trip
POST   /api/v1/trips/{id}/retry        Retry a failed trip
```

---

## Implementation

### Orchestrator Agent

```python
# apps/backend/src/parikrama/agents/orchestrator.py
"""
Orchestrator Agent — the master coordinator.

Responsibilities:
1. Parse the user's natural language request into structured TripRequest
2. Validate the request (reasonable dates, valid locations, etc.)
3. Set initial state for downstream agents
4. Handle Hindi + English mixed input
"""
import json

import structlog

from parikrama.agents.base import BaseAgent
from parikrama.agents.state import TripPlanningState, TripRequest

logger = structlog.get_logger()

ORCHESTRATOR_PROMPT = """You are the Orchestrator Agent for PariKrama, an Indian travel planning system.

Your job is to parse the user's travel request into a structured format.
The user may write in English, Hindi, or Hinglish (mixed).

Extract these fields:
- origin: starting city
- destination: target city/place
- days: number of days
- budget_inr: total budget in Indian Rupees (INR)
- travelers: number of travelers (default: 1)
- preferences: interests, food preferences, travel style

IMPORTANT:
- If budget is mentioned without currency, assume INR
- "5 din" means 5 days
- "sasta" means budget/economy
- "family trip" implies multiple travelers
- Convert any mentions like "15k" or "15 hazar" to 15000

Return ONLY valid JSON, no markdown, no explanation.

Example output:
{
    "origin": "Delhi",
    "destination": "Manali",
    "days": 5,
    "budget_inr": 15000,
    "travelers": 1,
    "preferences": {"interests": ["sightseeing", "adventure"], "food": "any", "style": "budget"},
    "language": "en"
}
"""


class OrchestratorAgent(BaseAgent):
    """Parses user intent and initializes the planning pipeline."""

    def __init__(self) -> None:
        super().__init__(name="orchestrator", system_prompt=ORCHESTRATOR_PROMPT)

    async def execute(self, state: TripPlanningState) -> TripPlanningState:
        """Parse user request and set initial state."""
        user_message = state.get("raw_input", "")

        # call LLM to extract structured intent
        response = await self.call_llm(
            user_message=f"Parse this travel request:\n\n{user_message}",
            user_id=state.get("user_id"),
            trip_id=state.get("trip_id"),
        )

        # parse the JSON response
        try:
            parsed = json.loads(response.strip())
            trip_request = TripRequest(
                origin=parsed["origin"],
                destination=parsed["destination"],
                days=parsed["days"],
                budget_inr=parsed["budget_inr"],
                travelers=parsed.get("travelers", 1),
                preferences=parsed.get("preferences", {}),
                language=parsed.get("language", "en"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            self.log.error("orchestrator_parse_failed", error=str(e), raw=response[:200])
            raise ValueError(f"Failed to parse trip request: {e}")

        # validation
        if trip_request["days"] < 1 or trip_request["days"] > 30:
            raise ValueError(f"Trip duration must be 1-30 days, got {trip_request['days']}")
        if trip_request["budget_inr"] < 1000:
            raise ValueError(f"Budget too low: ₹{trip_request['budget_inr']}. Minimum ₹1,000.")

        state["request"] = trip_request
        state["current_agent"] = "orchestrator"
        state["status"] = "planning"
        state["messages"] = state.get("messages", []) + [{
            "agent": "orchestrator",
            "content": f"Planning {trip_request['days']}-day trip from {trip_request['origin']} to {trip_request['destination']}, budget ₹{trip_request['budget_inr']:,}",
        }]

        self.log.info(
            "trip_parsed",
            origin=trip_request["origin"],
            destination=trip_request["destination"],
            days=trip_request["days"],
            budget=trip_request["budget_inr"],
        )

        return state
```

### Research Agent

```python
# apps/backend/src/parikrama/agents/research.py
"""
Research Agent — gathers destination intelligence.

Uses real tools: weather API, places search, and RAG for travel knowledge.
Runs in parallel with the Booking Agent.
"""
import structlog

from parikrama.agents.base import BaseAgent
from parikrama.agents.state import TripPlanningState
from parikrama.agents.tools.weather import get_weather_forecast
from parikrama.agents.tools.places import search_places
from parikrama.services.rag_service import RAGService

logger = structlog.get_logger()

RESEARCH_PROMPT = """You are the Research Agent for PariKrama travel planner.

You have access to real data:
1. Weather forecasts for the destination
2. Points of interest and attractions
3. Travel guide knowledge (from our knowledge base)

Your job:
- Analyze weather conditions and provide packing/timing advice
- Identify top attractions, hidden gems, and must-visit places
- Summarize relevant travel reviews and tips
- Flag any safety concerns or seasonal warnings

For Indian destinations, consider:
- Festival seasons (Diwali, Holi, etc.) that affect crowds/prices
- Monsoon patterns
- Local food specialties
- Hindi/regional language basics for travelers

Output a comprehensive research brief that other agents can use for planning.
"""


class ResearchAgent(BaseAgent):
    """Gathers weather, places, and destination knowledge."""

    def __init__(self, db_session) -> None:
        super().__init__(name="research", system_prompt=RESEARCH_PROMPT)
        self.rag_service = RAGService(db_session)

    async def execute(self, state: TripPlanningState) -> TripPlanningState:
        """Run all research tools and synthesize findings."""
        request = state["request"]
        destination = request["destination"]
        days = request["days"]

        # tool 1: weather forecast
        try:
            weather = await get_weather_forecast(destination, days)
            state["weather"] = weather
        except Exception as e:
            self.log.warning("weather_fetch_failed", error=str(e))
            state["weather"] = None

        # tool 2: places of interest
        try:
            places = await search_places(destination)
            state["places_of_interest"] = places
        except Exception as e:
            self.log.warning("places_search_failed", error=str(e))
            state["places_of_interest"] = []

        # tool 3: RAG — retrieve travel knowledge
        from parikrama.schemas.rag import SearchRequest
        rag_results = await self.rag_service.search(
            SearchRequest(
                query=f"travel guide {destination} things to do budget tips",
                top_k=5,
                filter_metadata={"destination": destination} if destination else None,
            )
        )
        rag_context = "\n\n".join([r.content for r in rag_results]) if rag_results else ""
        state["destination_info"] = rag_context

        # synthesize all research into a brief
        research_context = self._build_context(state)
        summary = await self.call_llm(
            user_message=f"Synthesize this research for a {days}-day trip to {destination}:\n\n{research_context}",
            user_id=state.get("user_id"),
            trip_id=state.get("trip_id"),
        )

        state["reviews_summary"] = summary
        state["messages"] = state.get("messages", []) + [{
            "agent": "research",
            "content": f"Research completed for {destination}: weather, {len(state.get('places_of_interest', []))} places, travel knowledge gathered",
        }]

        return state

    def _build_context(self, state: TripPlanningState) -> str:
        """Combine all gathered data into a context string for the LLM."""
        parts = []
        if state.get("weather"):
            parts.append(f"Weather: {state['weather']}")
        if state.get("places_of_interest"):
            places_str = ", ".join([p.get("name", "") for p in state["places_of_interest"][:10]])
            parts.append(f"Top Places: {places_str}")
        if state.get("destination_info"):
            parts.append(f"Travel Guide:\n{state['destination_info'][:2000]}")
        return "\n\n".join(parts)
```

### Booking Agent

```python
# apps/backend/src/parikrama/agents/booking.py
"""
Booking Agent — finds hotels and transport options.

Searches real APIs for accommodation and transport.
Flags when a booking requires human approval (expensive items).
"""
import structlog

from parikrama.agents.base import BaseAgent
from parikrama.agents.state import TripPlanningState, HotelOption, TransportOption
from parikrama.agents.tools.hotels import search_hotels
from parikrama.agents.tools.transport import search_transport

logger = structlog.get_logger()

BOOKING_PROMPT = """You are the Booking Agent for PariKrama travel planner.

You find the best accommodation and transport options within the user's budget.

For Indian travel:
- Consider different transport types: bus (Volvo/sleeper), train (IRCTC classes), flights
- Budget breakdown: typically 30-40% transport, 30-40% accommodation, rest for food+activities
- Hotels: hostels/guesthouses for budget, 3-star for mid, 4-5 star for premium
- Always provide 2-3 options at different price points

Your job:
1. Search for hotels at the destination
2. Search for transport from origin to destination (and return)
3. Rank options by value-for-money
4. Flag items that cost >50% of total budget (need approval)

Output structured hotel and transport recommendations.
"""


class BookingAgent(BaseAgent):
    """Finds hotels and transport options within budget."""

    def __init__(self) -> None:
        super().__init__(name="booking", system_prompt=BOOKING_PROMPT)

    async def execute(self, state: TripPlanningState) -> TripPlanningState:
        """Search for accommodation and transport options."""
        request = state["request"]
        origin = request["origin"]
        destination = request["destination"]
        days = request["days"]
        budget = request["budget_inr"]

        # allocate budget portions
        transport_budget = int(budget * 0.35)
        hotel_budget = int(budget * 0.35)

        # tool 1: search hotels
        try:
            hotels = await search_hotels(
                location=destination,
                check_in_days=days,
                max_price_per_night=hotel_budget // max(days, 1),
            )
            state["hotel_options"] = hotels[:5]
        except Exception as e:
            self.log.warning("hotel_search_failed", error=str(e))
            state["hotel_options"] = []

        # tool 2: search transport
        try:
            transport = await search_transport(
                origin=origin,
                destination=destination,
                max_price=transport_budget,
            )
            state["transport_options"] = transport[:5]
        except Exception as e:
            self.log.warning("transport_search_failed", error=str(e))
            state["transport_options"] = []

        # check if any option exceeds 50% of budget → flag for approval
        expensive_items = []
        for hotel in state.get("hotel_options", []):
            total_hotel_cost = hotel.get("price_per_night_inr", 0) * days
            if total_hotel_cost > budget * 0.5:
                expensive_items.append(f"Hotel {hotel['name']}: ₹{total_hotel_cost:,}")

        for transport in state.get("transport_options", []):
            if transport.get("price_inr", 0) > budget * 0.5:
                expensive_items.append(f"Transport {transport['type']}: ₹{transport['price_inr']:,}")

        state["requires_approval"] = len(expensive_items) > 0

        state["messages"] = state.get("messages", []) + [{
            "agent": "booking",
            "content": f"Found {len(state.get('hotel_options', []))} hotels and {len(state.get('transport_options', []))} transport options",
        }]

        return state
```

### Budget Agent

```python
# apps/backend/src/parikrama/agents/budget.py
"""
Budget Agent — optimizes costs and checks feasibility.

Takes research + booking data and produces a realistic cost breakdown.
If over budget, suggests optimizations (cheaper transport, different hotel, etc.)
"""
import json
import structlog

from parikrama.agents.base import BaseAgent
from parikrama.agents.state import TripPlanningState, BudgetBreakdown

logger = structlog.get_logger()

BUDGET_PROMPT = """You are the Budget Agent for PariKrama travel planner.

Analyze the trip data and create a detailed budget breakdown in INR.

Categories:
- Transport: getting to and from destination
- Accommodation: hotel/hostel costs
- Food: meals (consider local food prices in India)
- Activities: entry fees, adventure sports, guided tours
- Miscellaneous: tips, souvenirs, emergency buffer (10%)

Rules:
- All amounts in INR (Indian Rupees)
- If total exceeds budget, suggest specific cost-cutting measures
- Consider that food in hill stations costs 20-30% more than plains
- Add buffer for Manali/Shimla/Leh type destinations (ATM availability issues)
- For budget travelers: suggest dhabas, shared transport, dormitories

Return JSON with this structure:
{
    "transport_inr": 0,
    "accommodation_inr": 0,
    "food_inr": 0,
    "activities_inr": 0,
    "misc_inr": 0,
    "total_inr": 0,
    "is_within_budget": true/false,
    "savings_tips": ["tip1", "tip2"]
}
"""


class BudgetAgent(BaseAgent):
    """Calculates costs and optimizes budget allocation."""

    def __init__(self) -> None:
        super().__init__(name="budget", system_prompt=BUDGET_PROMPT)

    async def execute(self, state: TripPlanningState) -> TripPlanningState:
        """Analyze costs and produce budget breakdown."""
        request = state["request"]
        budget = request["budget_inr"]

        # build context from research and booking data
        context_parts = [
            f"Trip: {request['origin']} → {request['destination']}, {request['days']} days",
            f"Budget: ₹{budget:,}",
            f"Travelers: {request['travelers']}",
        ]

        if state.get("hotel_options"):
            cheapest = min(state["hotel_options"], key=lambda h: h.get("price_per_night_inr", 99999))
            context_parts.append(
                f"Cheapest hotel: {cheapest['name']} at ₹{cheapest['price_per_night_inr']:,}/night"
            )

        if state.get("transport_options"):
            cheapest_t = min(state["transport_options"], key=lambda t: t.get("price_inr", 99999))
            context_parts.append(
                f"Cheapest transport: {cheapest_t['type']} at ₹{cheapest_t['price_inr']:,}"
            )

        context = "\n".join(context_parts)

        response = await self.call_llm(
            user_message=f"Create a budget breakdown for this trip:\n{context}",
            user_id=state.get("user_id"),
            trip_id=state.get("trip_id"),
        )

        try:
            breakdown_data = json.loads(response.strip())
            breakdown = BudgetBreakdown(
                transport_inr=breakdown_data.get("transport_inr", 0),
                accommodation_inr=breakdown_data.get("accommodation_inr", 0),
                food_inr=breakdown_data.get("food_inr", 0),
                activities_inr=breakdown_data.get("activities_inr", 0),
                misc_inr=breakdown_data.get("misc_inr", 0),
                total_inr=breakdown_data.get("total_inr", 0),
                savings_tips=breakdown_data.get("savings_tips", []),
            )
            state["budget_breakdown"] = breakdown
            state["is_within_budget"] = breakdown["total_inr"] <= budget
        except (json.JSONDecodeError, KeyError) as e:
            self.log.error("budget_parse_failed", error=str(e))
            state["budget_breakdown"] = None
            state["is_within_budget"] = True  # assume ok to continue

        state["messages"] = state.get("messages", []) + [{
            "agent": "budget",
            "content": f"Budget analysis: ₹{state.get('budget_breakdown', {}).get('total_inr', 0):,} / ₹{budget:,}",
        }]

        return state
```

### Itinerary Agent

```python
# apps/backend/src/parikrama/agents/itinerary.py
"""
Itinerary Agent — generates the final day-by-day travel plan.

This is the last agent in the pipeline. It takes all gathered data
and produces a polished, actionable itinerary the user can follow.
"""
import json
import structlog

from parikrama.agents.base import BaseAgent
from parikrama.agents.state import TripPlanningState, DayPlan

logger = structlog.get_logger()

ITINERARY_PROMPT = """You are the Itinerary Agent for PariKrama travel planner.

Create a detailed day-by-day travel itinerary based on the research and booking data provided.

Each day should include:
- Morning, afternoon, evening activities with approximate times
- Meal suggestions (breakfast, lunch, dinner) with local restaurant types
- Travel/transit details if moving between locations
- Estimated costs per activity in INR
- Practical tips (what to carry, best time to visit, etc.)

Style guidelines:
- Write in a friendly, conversational tone
- Include local food recommendations (dal makhani in Manali, maggi at hilltops)
- Mention photography spots
- Consider weather in activity planning
- Buffer time for rest/flexibility

Return as a JSON array of day plans:
[
    {
        "day": 1,
        "date": "Day 1",
        "title": "Arrival & Local Exploration",
        "activities": [
            {"time": "10:00 AM", "activity": "Check into hotel", "location": "Mall Road", "cost_inr": 0}
        ],
        "meals": [
            {"time": "1:00 PM", "suggestion": "Lunch at Johnson Cafe", "estimated_cost_inr": 300}
        ],
        "accommodation": {"hotel": "Hotel Name", "check_in": "11:00 AM"},
        "tips": ["Carry warm jacket even in summer"]
    }
]
"""


class ItineraryAgent(BaseAgent):
    """Generates the final day-by-day itinerary."""

    def __init__(self) -> None:
        super().__init__(name="itinerary", system_prompt=ITINERARY_PROMPT)

    async def execute(self, state: TripPlanningState) -> TripPlanningState:
        """Generate comprehensive day-by-day itinerary."""
        request = state["request"]

        # compile all available info for the itinerary
        context = self._compile_context(state)

        response = await self.call_llm(
            user_message=f"Create a {request['days']}-day itinerary:\n\n{context}",
            user_id=state.get("user_id"),
            trip_id=state.get("trip_id"),
        )

        try:
            itinerary_data = json.loads(response.strip())
            state["itinerary"] = itinerary_data
        except json.JSONDecodeError:
            # if LLM returns markdown or non-JSON, store as summary
            state["itinerary"] = []
            state["summary"] = response

        # generate one-paragraph summary
        if not state.get("summary"):
            dest = request["destination"]
            days = request["days"]
            budget = request["budget_inr"]
            state["summary"] = (
                f"Your {days}-day trip to {dest} with a budget of ₹{budget:,} "
                f"includes {len(state.get('itinerary', []))} days of activities, "
                f"accommodation, and local experiences."
            )

        state["status"] = "completed"
        state["messages"] = state.get("messages", []) + [{
            "agent": "itinerary",
            "content": f"Itinerary generated: {len(state.get('itinerary', []))} days planned",
        }]

        return state

    def _compile_context(self, state: TripPlanningState) -> str:
        """Build comprehensive context from all agent outputs."""
        parts = []
        req = state["request"]

        parts.append(f"Trip: {req['origin']} → {req['destination']}, {req['days']} days")
        parts.append(f"Budget: ₹{req['budget_inr']:,} for {req['travelers']} traveler(s)")

        if req.get("preferences"):
            parts.append(f"Preferences: {json.dumps(req['preferences'])}")

        if state.get("weather"):
            parts.append(f"\nWeather:\n{json.dumps(state['weather'], indent=2)}")

        if state.get("places_of_interest"):
            places = [p.get("name", "") for p in state["places_of_interest"][:10]]
            parts.append(f"\nPlaces: {', '.join(places)}")

        if state.get("reviews_summary"):
            parts.append(f"\nResearch Summary:\n{state['reviews_summary'][:1500]}")

        if state.get("hotel_options"):
            parts.append(f"\nHotels: {json.dumps(state['hotel_options'][:3], indent=2)}")

        if state.get("transport_options"):
            parts.append(f"\nTransport: {json.dumps(state['transport_options'][:3], indent=2)}")

        if state.get("budget_breakdown"):
            parts.append(f"\nBudget Breakdown: {json.dumps(state['budget_breakdown'], indent=2)}")

        return "\n".join(parts)
```

### LangGraph Definition

```python
# apps/backend/src/parikrama/agents/graph.py
"""
LangGraph graph definition — the orchestration pipeline.

Defines the directed graph of agent nodes, edges, and conditional routing.
This is where the multi-agent system comes together.
"""
import structlog
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from parikrama.agents.state import TripPlanningState
from parikrama.agents.orchestrator import OrchestratorAgent
from parikrama.agents.research import ResearchAgent
from parikrama.agents.booking import BookingAgent
from parikrama.agents.budget import BudgetAgent
from parikrama.agents.itinerary import ItineraryAgent
from parikrama.config import settings

logger = structlog.get_logger()


def should_continue_after_budget(state: TripPlanningState) -> str:
    """
    Conditional edge after Budget Agent.
    Routes to itinerary if within budget, otherwise re-optimizes.
    """
    if state.get("is_within_budget", True):
        return "itinerary"
    else:
        # budget exceeded — loop back to budget for optimization
        # (with a max retry to prevent infinite loops)
        budget_retries = state.get("_budget_retries", 0)
        if budget_retries >= 2:
            logger.warning("budget_max_retries_reached", trip_id=state.get("trip_id"))
            return "itinerary"  # proceed anyway with warnings
        state["_budget_retries"] = budget_retries + 1
        return "budget_reoptimize"


def check_approval_needed(state: TripPlanningState) -> str:
    """
    Conditional edge after Booking Agent.
    If expensive items found, pause for human approval (Phase 5).
    """
    if state.get("requires_approval", False):
        return "await_approval"
    return "budget"


async def build_trip_graph(db_session) -> StateGraph:
    """
    Build the complete trip planning graph.

    Returns a compiled LangGraph with PostgreSQL state persistence.
    """
    # initialize agents
    orchestrator = OrchestratorAgent()
    research = ResearchAgent(db_session)
    booking = BookingAgent()
    budget = BudgetAgent()
    itinerary = ItineraryAgent()

    # build the graph
    graph = StateGraph(TripPlanningState)

    # add nodes (each agent is a node)
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("research", research)
    graph.add_node("booking", booking)
    graph.add_node("budget", budget)
    graph.add_node("itinerary", itinerary)

    # define edges (the flow)
    graph.set_entry_point("orchestrator")

    # orchestrator → research + booking (parallel via fan-out)
    graph.add_edge("orchestrator", "research")
    graph.add_edge("orchestrator", "booking")

    # research → budget (waits for booking too via join)
    graph.add_edge("research", "budget")
    graph.add_edge("booking", "budget")

    # budget → conditional routing
    graph.add_conditional_edges(
        "budget",
        should_continue_after_budget,
        {
            "itinerary": "itinerary",
            "budget_reoptimize": "budget",
        },
    )

    # itinerary → end
    graph.add_edge("itinerary", END)

    # compile with PostgreSQL checkpointer for state persistence
    checkpointer = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
    await checkpointer.setup()

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("trip_graph_compiled", nodes=list(graph.nodes.keys()))

    return compiled
```

### Agent Tools — Weather

```python
# apps/backend/src/parikrama/agents/tools/weather.py
"""
Weather tool — fetches real weather forecasts.

Uses OpenWeatherMap free tier (1000 calls/day).
Falls back to mock data for development/testing.
"""
from datetime import datetime, timedelta

import httpx
import structlog

from parikrama.config import settings

logger = structlog.get_logger()

OPENWEATHERMAP_URL = "https://api.openweathermap.org/data/2.5/forecast"


async def get_weather_forecast(location: str, days: int = 5) -> dict:
    """
    Fetch weather forecast for a location.

    Returns structured weather data with advisory.
    Free tier supports 5-day forecast with 3-hour intervals.
    """
    if not settings.OPENWEATHERMAP_API_KEY:
        logger.info("weather_api_key_missing_using_mock")
        return _mock_weather(location, days)

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            OPENWEATHERMAP_URL,
            params={
                "q": f"{location},IN",  # assume Indian locations
                "appid": settings.OPENWEATHERMAP_API_KEY,
                "units": "metric",
                "cnt": min(days * 8, 40),  # 8 intervals per day, max 40
            },
        )
        response.raise_for_status()
        data = response.json()

    # parse into our format
    forecasts = []
    seen_dates = set()
    for item in data.get("list", []):
        date = item["dt_txt"].split(" ")[0]
        if date not in seen_dates:
            seen_dates.add(date)
            forecasts.append({
                "date": date,
                "temp_min": item["main"]["temp_min"],
                "temp_max": item["main"]["temp_max"],
                "description": item["weather"][0]["description"],
                "humidity": item["main"]["humidity"],
                "wind_speed": item["wind"]["speed"],
            })

    # generate advisory based on conditions
    advisory = _generate_advisory(forecasts, location)

    return {
        "location": location,
        "dates": [f["date"] for f in forecasts[:days]],
        "forecasts": forecasts[:days],
        "advisory": advisory,
    }


def _generate_advisory(forecasts: list[dict], location: str) -> str:
    """Generate practical weather advisory."""
    if not forecasts:
        return "Weather data unavailable. Pack for various conditions."

    avg_temp = sum(f["temp_max"] for f in forecasts) / len(forecasts)
    has_rain = any("rain" in f["description"].lower() for f in forecasts)

    tips = []
    if avg_temp < 10:
        tips.append("Pack heavy woolens, thermals, and gloves")
    elif avg_temp < 20:
        tips.append("Carry light jackets and layered clothing")
    else:
        tips.append("Light cotton clothing recommended")

    if has_rain:
        tips.append("Carry rain gear and waterproof bags")

    if location.lower() in ["manali", "shimla", "leh", "darjeeling", "ooty"]:
        tips.append("Expect temperature drops at night, even in summer")

    return ". ".join(tips) + "."


def _mock_weather(location: str, days: int) -> dict:
    """Mock weather for development without API key."""
    base_date = datetime.now()
    return {
        "location": location,
        "dates": [(base_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)],
        "forecasts": [
            {
                "date": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "temp_min": 8 + i,
                "temp_max": 18 + i,
                "description": "partly cloudy",
                "humidity": 65,
                "wind_speed": 3.5,
            }
            for i in range(days)
        ],
        "advisory": "Mock data — configure OPENWEATHERMAP_API_KEY for real forecasts.",
    }
```

### Trip Service (API Layer)

```python
# apps/backend/src/parikrama/services/trip_service.py
"""
Trip service — starts and manages trip planning sessions.

Connects the API layer to the LangGraph agent pipeline.
"""
import uuid
import time

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.agents.graph import build_trip_graph
from parikrama.agents.state import TripPlanningState
from parikrama.models.trip import Trip
from parikrama_common.enums import TripStatus

logger = structlog.get_logger()


class TripService:
    """Manages trip planning lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def start_trip(self, user_id: str, raw_input: str) -> dict:
        """
        Start a new trip planning session.

        Creates a Trip record and runs the LangGraph pipeline.
        Returns the trip ID immediately; results stream via WebSocket.
        """
        trip_id = str(uuid.uuid4())
        thread_id = f"trip_{trip_id}"

        # create trip record
        trip = Trip(
            id=uuid.UUID(trip_id),
            user_id=uuid.UUID(user_id),
            status=TripStatus.PLANNING,
            request={"raw_input": raw_input},
            thread_id=thread_id,
        )
        self.db.add(trip)
        await self.db.flush()

        # initial state for the graph
        initial_state: TripPlanningState = {
            "trip_id": trip_id,
            "user_id": user_id,
            "raw_input": raw_input,
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
            "messages": [],
            "errors": [],
            "status": "planning",
            "approval_response": None,
        }

        # run the graph
        start_time = time.perf_counter()
        graph = await build_trip_graph(self.db)

        config = {"configurable": {"thread_id": thread_id}}
        final_state = await graph.ainvoke(initial_state, config=config)

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # update trip with results
        trip.status = TripStatus.COMPLETED
        trip.result = {
            "itinerary": final_state.get("itinerary", []),
            "budget_breakdown": final_state.get("budget_breakdown"),
            "summary": final_state.get("summary", ""),
            "hotel_options": final_state.get("hotel_options", []),
            "transport_options": final_state.get("transport_options", []),
        }
        trip.planning_duration_ms = duration_ms

        logger.info(
            "trip_planning_completed",
            trip_id=trip_id,
            duration_ms=duration_ms,
            status=final_state.get("status"),
        )

        return {
            "trip_id": trip_id,
            "status": trip.status,
            "result": trip.result,
            "duration_ms": duration_ms,
        }
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| Orchestrator parses English request | Unit | Correct extraction of fields |
| Orchestrator parses Hindi request | Unit | "5 din" = 5 days, "15 hazar" = 15000 |
| Research agent handles API failures | Unit | Graceful fallback with partial data |
| Booking agent flags expensive items | Unit | `requires_approval` set correctly |
| Budget agent detects over-budget | Unit | `is_within_budget` = false triggers re-optimize |
| Full graph executes end-to-end | Integration | All agents run, state persists |
| Parallel execution of research + booking | Integration | Both agents run concurrently |
| Graph recovery from checkpoint | Integration | Resume after interrupt works |

---

## Definition of Done — Phase 4

- [ ] All 5 agents implemented with system prompts
- [ ] LangGraph graph compiles and runs end-to-end
- [ ] Research and Booking agents run in parallel
- [ ] Budget conditional routing works (within budget → itinerary)
- [ ] State persisted in PostgreSQL via checkpointer
- [ ] Weather tool fetches real data from OpenWeatherMap
- [ ] Trip API endpoint starts planning and returns results
- [ ] Agent run history stored in `agent_runs` table
- [ ] Hindi/Hinglish input parsing works in orchestrator
- [ ] Error handling prevents single agent failure from crashing pipeline

## Scale-Up Path

| Component | Current | Trigger | Upgrade |
|-----------|---------|---------|---------|
| Agent Execution | Async in API process | >50 concurrent trips | Celery task per trip |
| State Persistence | PostgreSQL checkpointer | >1000 concurrent threads | Redis checkpointer |
| Weather API | OpenWeatherMap free (1K/day) | Daily limit hit | WeatherAPI.com or cache aggressively |
| Hotel Search | Mock/basic API | Real bookings needed | Integrate Goibibo/MakeMyTrip affiliate APIs |

---

*Phase 4 delivers the core value proposition. After this phase, a user can send a message and receive a complete travel itinerary.*
