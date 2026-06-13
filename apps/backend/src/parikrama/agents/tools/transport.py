"""
Transport tool — searches for travel options between two Indian cities.

Covers: Volvo bus, sleeper bus, train (various IRCTC classes), and flights.
Mock data uses realistic Indian transport pricing and durations.
Real API integration (IRCTC, RedBus, IndiGo) planned for Phase 5.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Approximate distance/duration lookup for common Indian routes (km, hours)
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
) -> list[dict]:
    """
    Search for transport options between two cities.

    Args:
        origin: Departure city.
        destination: Arrival city.
        max_price: Max one-way price in INR (filter).
        travel_date: Date string (unused in mock — for real API).

    Returns:
        List of transport option dicts, sorted by price (cheapest first).
        Never raises — returns mock data on failure.
    """
    logger.info("transport_search_started", origin=origin, destination=destination)

    options = _generate_mock_transport(origin, destination)

    if max_price is not None:
        affordable = [o for o in options if o["price_inr"] <= max_price]
        # Always include at least one option even if over budget
        if not affordable and options:
            affordable = [options[0]]  # cheapest option regardless
        options = affordable

    options.sort(key=lambda o: o["price_inr"])
    logger.info("transport_search_complete", count=len(options))
    return options


def _generate_mock_transport(origin: str, destination: str) -> list[dict]:
    """Generate realistic transport options for any Indian route."""
    route_key = f"{origin.lower()}_{destination.lower()}"
    profile = _ROUTE_PROFILES.get(route_key, _DEFAULT_PROFILE)

    options: list[dict] = []

    # ── Bus options ──────────────────────────────────────────────────────────
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

    # ── Train options (if route supports it) ────────────────────────────────
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

    # ── Flight options (if route supports it) ────────────────────────────────
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
