# Phase 8: MCP Server

## Overview

Phase 8 exposes PariKrama's capabilities as **MCP (Model Context Protocol) tools** — allowing Claude Desktop, Cursor, and other MCP-compatible clients to directly search travel knowledge, plan trips, and check trip status. This makes PariKrama an AI-native tool that other LLMs can use.

### What MCP Enables
```
Claude Desktop → "Search travel knowledge about Manali"
                        ↓
              MCP Protocol (stdio/SSE)
                        ↓
              PariKrama MCP Server
                        ↓
              RAG Search / Trip API
                        ↓
              Real results returned to Claude
```

---

## Architecture Decisions

### Why FastMCP
**FastMCP** is the official Python MCP SDK — it handles protocol negotiation, tool registration, and serialization. We just define our tools as Python functions with type hints, and FastMCP exposes them correctly.

### Transport: stdio vs SSE
| Transport | Use Case | Security |
|-----------|----------|----------|
| **stdio (chosen for Claude Desktop)** | Local usage | Process-level isolation |
| SSE (HTTP) | Remote access | Requires auth tokens |

We implement both: stdio for local Claude Desktop integration, SSE for remote/programmatic access.

---

## Implementation

### MCP Server

```python
# apps/mcp/src/parikrama_mcp/server.py
"""
PariKrama MCP Server — exposes travel tools for AI assistants.

Tools:
  - search_travel_knowledge: RAG-powered travel knowledge search
  - plan_trip: Start a full trip planning session
  - get_trip_status: Check status of an ongoing trip
  - list_user_trips: View trip history
  - get_weather: Weather forecast for any Indian city
"""
import json
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("parikrama")


@server.tool()
async def search_travel_knowledge(query: str, top_k: int = 5) -> str:
    """
    Search PariKrama's travel knowledge base.

    Uses hybrid search (semantic + keyword) across travel guides,
    reviews, and destination information. Great for answering
    specific questions about Indian travel destinations.

    Args:
        query: Your search query (e.g., "best time to visit Manali")
        top_k: Number of results to return (1-20, default 5)
    """
    import httpx

    api_url = os.getenv("PARIKRAMA_API_URL", "http://localhost:8000")
    api_key = os.getenv("PARIKRAMA_API_KEY", "")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{api_url}/api/v1/rag/search",
            json={"query": query, "top_k": top_k},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        results = response.json()

    if not results:
        return "No relevant information found. Try a different search query."

    # format results for Claude
    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(f"**Result {i}** (score: {r['score']:.3f}):\n{r['content']}")

    return "\n\n---\n\n".join(formatted)


@server.tool()
async def plan_trip(
    origin: str,
    destination: str,
    days: int,
    budget_inr: int,
    preferences: str = "",
) -> str:
    """
    Plan a complete trip with AI agents.

    Spawns multiple AI agents that research weather, find hotels,
    check transport options, optimize budget, and generate a
    day-by-day itinerary.

    Args:
        origin: Starting city (e.g., "Delhi")
        destination: Destination city (e.g., "Manali")
        days: Number of days (1-30)
        budget_inr: Total budget in Indian Rupees
        preferences: Optional preferences (e.g., "adventure, vegetarian food")
    """
    import httpx

    api_url = os.getenv("PARIKRAMA_API_URL", "http://localhost:8000")
    api_key = os.getenv("PARIKRAMA_API_KEY", "")

    raw_input = (
        f"Plan a {days}-day trip from {origin} to {destination}, "
        f"budget ₹{budget_inr:,}. {preferences}"
    )

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{api_url}/api/v1/trips",
            json={"raw_input": raw_input},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        result = response.json()

    trip_id = result.get("trip_id", "")
    status = result.get("status", "unknown")

    if status == "completed":
        itinerary = result.get("result", {})
        return json.dumps(itinerary, indent=2, ensure_ascii=False)
    else:
        return f"Trip planning started (ID: {trip_id}). Status: {status}. Check back with get_trip_status."


@server.tool()
async def get_trip_status(trip_id: str) -> str:
    """
    Check the current status of a trip planning session.

    Args:
        trip_id: The UUID of the trip to check
    """
    import httpx

    api_url = os.getenv("PARIKRAMA_API_URL", "http://localhost:8000")
    api_key = os.getenv("PARIKRAMA_API_KEY", "")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{api_url}/api/v1/trips/{trip_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        trip = response.json()

    return json.dumps(trip, indent=2, ensure_ascii=False)


@server.tool()
async def get_weather(location: str, days: int = 5) -> str:
    """
    Get weather forecast for an Indian city.

    Args:
        location: City name (e.g., "Manali", "Goa", "Jaipur")
        days: Forecast days (1-5, default 5)
    """
    import httpx

    api_key = os.getenv("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        return "Weather API key not configured. Set OPENWEATHERMAP_API_KEY."

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "q": f"{location},IN",
                "appid": api_key,
                "units": "metric",
                "cnt": days * 8,
            },
        )
        response.raise_for_status()
        data = response.json()

    forecasts = []
    seen_dates = set()
    for item in data.get("list", []):
        date = item["dt_txt"].split(" ")[0]
        if date not in seen_dates:
            seen_dates.add(date)
            forecasts.append(
                f"{date}: {item['main']['temp_min']:.0f}-{item['main']['temp_max']:.0f}°C, "
                f"{item['weather'][0]['description']}"
            )

    return f"Weather forecast for {location}:\n" + "\n".join(forecasts[:days])


@server.tool()
async def list_user_trips() -> str:
    """List all trips planned by the current user."""
    import httpx

    api_url = os.getenv("PARIKRAMA_API_URL", "http://localhost:8000")
    api_key = os.getenv("PARIKRAMA_API_KEY", "")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{api_url}/api/v1/trips",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        trips = response.json()

    if not trips:
        return "No trips found. Use plan_trip to create one."

    formatted = []
    for trip in trips:
        req = trip.get("request", {})
        formatted.append(
            f"• {trip['id'][:8]}... | {req.get('origin', '?')} → {req.get('destination', '?')} | "
            f"Status: {trip['status']} | Created: {trip['created_at']}"
        )

    return "Your trips:\n" + "\n".join(formatted)


async def main():
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Claude Desktop Configuration

```json
// Claude Desktop config file
// Location: %APPDATA%/Claude/claude_desktop_config.json (Windows)
//           ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
{
  "mcpServers": {
    "parikrama": {
      "command": "uv",
      "args": [
        "--directory", "D:/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/apps/mcp",
        "run", "python", "-m", "parikrama_mcp.server"
      ],
      "env": {
        "PARIKRAMA_API_URL": "http://localhost:8000",
        "PARIKRAMA_API_KEY": "pk_your_api_key_here",
        "OPENWEATHERMAP_API_KEY": "your_weather_key"
      }
    }
  }
}
```

### MCP pyproject.toml

```toml
# apps/mcp/pyproject.toml
[project]
name = "parikrama-mcp"
version = "0.1.0"
description = "PariKrama MCP Server"
requires-python = ">=3.12"

dependencies = [
    "mcp>=1.0",
    "httpx>=0.27",
    "parikrama-common",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parikrama_mcp"]
```

---

## Environment Variables Required

```bash
# Phase 8:
PARIKRAMA_API_URL=http://localhost:8000
PARIKRAMA_API_KEY=pk_your_api_key_here
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| MCP server starts | Unit | Server initializes without errors |
| search_travel_knowledge returns results | Integration | RAG search via API works |
| plan_trip initiates planning | Integration | Trip created via API |
| get_trip_status returns trip data | Integration | Trip detail retrieval works |
| get_weather returns forecast | Integration | Weather API integration works |
| Claude Desktop config is valid JSON | Lint | Config file parseable |

---

## Definition of Done — Phase 8

- [ ] FastMCP server runs with stdio transport
- [ ] All 5 tools registered and functional
- [ ] Claude Desktop configuration documented and tested
- [ ] API key authentication works for MCP calls
- [ ] Error handling returns helpful messages to the AI client
- [ ] MCP server Dockerfile for containerized deployment

---

*Phase 8 makes PariKrama composable — any AI assistant can now plan trips through our system.*
