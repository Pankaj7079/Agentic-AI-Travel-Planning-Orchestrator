"""
Transport tool — searches for travel options between two Indian cities.

Uses LLM to generate realistic transport options with accurate pricing
for any route. Falls back to curated mock data for well-known routes.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

TRANSPORT_SYSTEM_PROMPT = """You are a transport pricing expert for Indian travel routes.

Given an origin and destination city in India, generate realistic one-way transport options.

Rules:
- Generate exactly 4-5 options covering bus, train (if available), and flight (if available)
- Prices must be realistic for this specific route (not generic)
- Include real operator names (HRTC, MSRTC, KSRTC, IRCTC, IndiGo, SpiceJet, etc.)
- Duration must reflect actual travel time for this route
- Hill stations (Manali, Shimla, Ooty): usually bus only, no train/flight
- Metro to Metro: all 3 modes available
- Short distance (<200km): bus + train, usually no flight

Return ONLY a JSON array with objects having:
- type: "bus" | "train" | "flight"
- operator: realistic operator name
- origin: departure city
- destination: arrival city
- price_inr: number (realistic one-way price)
- duration_hours: number (actual travel time)
- departure_time: "HH:MM" format
- class: "AC Sleeper" | "AC Semi-Sleeper" | "Sleeper (SL)" | "3rd AC (3A)" | "2nd AC (2A)" | "Economy"

Example for Delhi to Manali:
[
  {"type":"bus","operator":"HRTC Volvo AC","origin":"Delhi","destination":"Manali","price_inr":1100,"duration_hours":14,"departure_time":"21:00","class":"AC Sleeper"},
  {"type":"bus","operator":"Himachal Tourist Volvo","origin":"Delhi","destination":"Manali","price_inr":1500,"duration_hours":13,"departure_time":"20:00","class":"AC Semi-Sleeper"},
  {"type":"bus","operator":"Private Sleeper","origin":"Delhi","destination":"Manali","price_inr":800,"duration_hours":15,"departure_time":"22:00","class":"Non-AC Sleeper"}
]

Note: Delhi-Manali has NO train or flight option (realistic).

Return ONLY the JSON array, no markdown, no explanation."""

# Known route profiles for quick mock generation (no LLM needed)
_ROUTE_PROFILES: dict[str, dict] = {
    "delhi_manali": {
        "distance_km": 545,
        "bus_hours": 14,
        "train_available": False,
        "flight_available": False,
    },
    "delhi_shimla": {
        "distance_km": 370,
        "bus_hours": 10,
        "train_available": True,
        "flight_available": False,
    },
    "delhi_jaipur": {
        "distance_km": 280,
        "bus_hours": 6,
        "train_available": True,
        "flight_available": True,
    },
    "mumbai_goa": {
        "distance_km": 590,
        "bus_hours": 12,
        "train_available": True,
        "flight_available": True,
    },
    "mumbai_pune": {
        "distance_km": 150,
        "bus_hours": 4,
        "train_available": True,
        "flight_available": False,
    },
    "bangalore_mysore": {
        "distance_km": 145,
        "bus_hours": 3,
        "train_available": True,
        "flight_available": False,
    },
    "bangalore_ooty": {
        "distance_km": 270,
        "bus_hours": 6,
        "train_available": False,
        "flight_available": False,
    },
}

_DEFAULT_PROFILE = {
    "distance_km": 400,
    "bus_hours": 10,
    "train_available": True,
    "flight_available": False,
}


async def search_transport(
    origin: str,
    destination: str,
    max_price: float | None = None,
    travel_date: str | None = None,
    llm_router: LLMRouter | None = None,
) -> list[dict]:
    """
    Search for transport options between two cities.

    Uses LLM for unknown routes, mock data for well-known routes.

    Args:
        origin: Departure city.
        destination: Arrival city.
        max_price: Max one-way price in INR (filter).
        travel_date: Date string (unused in mock — for real API).
        llm_router: Optional LLMRouter for generating realistic options.

    Returns:
        List of transport option dicts, sorted by price (cheapest first).
        Never raises — returns mock data on failure.
    """
    logger.info("transport_search_started", origin=origin, destination=destination)

    route_key = f"{origin.lower()}_{destination.lower()}"

    # Try LLM for unknown routes
    if route_key not in _ROUTE_PROFILES and llm_router:
        try:
            options = await _generate_llm_transport(origin, destination, llm_router)
            if options:
                if max_price is not None:
                    affordable = [o for o in options if o["price_inr"] <= max_price]
                    if not affordable and options:
                        affordable = [options[0]]
                    options = affordable
                options.sort(key=lambda o: o["price_inr"])
                logger.info("transport_search_complete", count=len(options), source="llm")
                return options
        except Exception as exc:
            logger.warning("llm_transport_failed", error=str(exc)[:100])

    # Fallback to mock data
    options = _generate_mock_transport(origin, destination)

    if max_price is not None:
        affordable = [o for o in options if o["price_inr"] <= max_price]
        if not affordable and options:
            affordable = [options[0]]
        options = affordable

    options.sort(key=lambda o: o["price_inr"])
    logger.info("transport_search_complete", count=len(options), source="mock")
    return options


async def _generate_llm_transport(
    origin: str, destination: str, llm_router: LLMRouter
) -> list[dict]:
    """Use LLM to generate realistic transport options for any route."""
    prompt = (
        f"Generate realistic one-way transport options from {origin} to {destination}, India. "
        f"Include bus, train (if available), and flight (if available). "
        f"Use real operator names and realistic pricing for this specific route."
    )

    response = await llm_router.generate(
        prompt=prompt,
        system=TRANSPORT_SYSTEM_PROMPT,
        temperature=0.5,
        max_tokens=2000,
    )

    raw = response.content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if match:
        raw = match.group(1).strip()
    match = re.search(r"\[[\s\S]+\]", raw)
    if match:
        raw = match.group(0)

    options = json.loads(raw)
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError(f"Expected at least 2 transport options, got {len(options)}")

    for opt in options:
        opt.setdefault("origin", origin)
        opt.setdefault("destination", destination)
        opt.setdefault("booking_url", "https://redbus.in/mock")

    return options


def _generate_mock_transport(origin: str, destination: str) -> list[dict]:
    """Generate realistic transport options for known Indian routes."""
    route_key = f"{origin.lower()}_{destination.lower()}"
    profile = _ROUTE_PROFILES.get(route_key, _DEFAULT_PROFILE)

    options: list[dict] = []

    options.append(
        {
            "type": "bus",
            "operator": "HRTC Volvo AC",
            "origin": origin,
            "destination": destination,
            "price_inr": 650,
            "duration_hours": profile["bus_hours"],
            "departure_time": "21:00",
            "arrival_time": f"~{profile['bus_hours']} hrs",
            "class": "AC Sleeper",
            "booking_url": "https://redbus.in/mock",
        }
    )
    options.append(
        {
            "type": "bus",
            "operator": "Private Volvo",
            "origin": origin,
            "destination": destination,
            "price_inr": 900,
            "duration_hours": profile["bus_hours"] - 1,
            "departure_time": "20:00",
            "arrival_time": f"~{profile['bus_hours'] - 1} hrs",
            "class": "AC Semi-Sleeper",
            "booking_url": "https://redbus.in/mock",
        }
    )

    if profile.get("train_available"):
        options.append(
            {
                "type": "train",
                "operator": "Indian Railways (IRCTC)",
                "origin": origin,
                "destination": destination,
                "price_inr": 450,
                "duration_hours": profile["bus_hours"] * 0.8,
                "departure_time": "22:30",
                "arrival_time": "morning",
                "class": "Sleeper (SL)",
                "booking_url": "https://irctc.co.in/mock",
            }
        )
        options.append(
            {
                "type": "train",
                "operator": "Indian Railways (IRCTC)",
                "origin": origin,
                "destination": destination,
                "price_inr": 1200,
                "duration_hours": profile["bus_hours"] * 0.7,
                "departure_time": "06:00",
                "arrival_time": "afternoon",
                "class": "3rd AC (3A)",
                "booking_url": "https://irctc.co.in/mock",
            }
        )

    if profile.get("flight_available"):
        options.append(
            {
                "type": "flight",
                "operator": "IndiGo / SpiceJet",
                "origin": origin,
                "destination": destination,
                "price_inr": 4500,
                "duration_hours": 1.5,
                "departure_time": "07:00",
                "arrival_time": "08:30",
                "class": "Economy",
                "booking_url": "https://makemytrip.com/mock",
            }
        )

    return options
