"""
Hotels tool — searches for accommodation options at a destination.

Uses LLM to generate realistic, destination-specific hotels with accurate
pricing based on the location's actual market rates. Falls back to curated
mock data if LLM is unavailable.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)

HOTEL_SYSTEM_PROMPT = """You are a hotel pricing expert for Indian travel destinations.

Given a destination, number of nights, and budget constraints, generate exactly 5 realistic hotel options.

IMPORTANT: Each hotel MUST be unique to this specific destination. Use real-sounding hotel names that reflect the local culture, geography, or landmarks. DO NOT use generic templates.

Pricing rules (INR per night):
- Hostel/Dorm: 300-900 (depending on destination popularity)
- Budget Hotel: 800-2000 (basic amenities, clean)
- Mid-Range: 1500-4000 (good location, restaurant, WiFi)
- Premium: 3000-7000 (great amenities, views, service)
- Luxury: 5000-15000 (resort, spa, premium location)

Location-specific pricing:
- Hill stations (Manali, Shimla, Ooty): +20-40% markup over plains
- Beach destinations (Goa, Pondicherry): wide range, backpacker-friendly
- Metro cities (Delhi, Mumbai): higher base prices
- Tier-2 cities (Jaipur, Varanasi): moderate prices
- Remote areas (Leh, Spiti): limited options, premium for comfort

Return ONLY a JSON array with 5 objects, each having:
- name: realistic hotel name (unique to this destination)
- location: specific area/neighborhood in the destination
- price_per_night_inr: number (realistic for this destination)
- rating: number (3.2 to 4.8)
- type: one of "hostel", "budget_hotel", "3_star", "3_star_plus", "4_star"
- amenities: list of 3-6 realistic amenities
- booking_url: "https://makeMyTrip.com/mock" (placeholder)

Example for Manali:
[
  {"name":"Snow Peak Hostel","location":"Old Manali","price_per_night_inr":550,"rating":4.2,"type":"hostel","amenities":["WiFi","Common area","Mountain view"],"booking_url":"https://makeMyTrip.com/mock"},
  ...
]

Return ONLY the JSON array, no markdown, no explanation."""


async def search_hotels(
    location: str,
    check_in_days: int = 2,
    max_price_per_night: float | None = None,
    llm_router: LLMRouter | None = None,
) -> list[dict]:
    """
    Search for hotel options at a destination.

    Uses LLM to generate destination-specific hotels when available.
    Falls back to curated mock data if LLM is unavailable.

    Args:
        location: City/destination name.
        check_in_days: Number of nights.
        max_price_per_night: Filter by max price per night (INR).
        llm_router: Optional LLMRouter for generating realistic hotels.

    Returns:
        List of hotel option dicts, sorted by value (price/rating).
        Never raises — returns mock data on any failure.
    """
    logger.info("hotel_search_started", location=location, nights=check_in_days)

    hotels = []

    # Try LLM-generated hotels first (destination-specific, realistic)
    if llm_router:
        try:
            hotels = await _generate_llm_hotels(location, check_in_days, llm_router)
        except Exception as exc:
            logger.warning("llm_hotel_generation_failed", error=str(exc)[:100])

    # Fallback to curated mock data
    if not hotels:
        hotels = _generate_mock_hotels(location, check_in_days)

    if max_price_per_night is not None:
        budget_hotels = [h for h in hotels if h["price_per_night_inr"] <= max_price_per_night]
        mid_hotels = [h for h in hotels if h["price_per_night_inr"] > max_price_per_night][:1]
        hotels = budget_hotels + mid_hotels

    hotels.sort(key=lambda h: h["rating"] / max(h["price_per_night_inr"], 1), reverse=True)

    logger.info("hotel_search_complete", location=location, count=len(hotels))
    return hotels


async def _generate_llm_hotels(location: str, nights: int, llm_router: LLMRouter) -> list[dict]:
    """Use LLM to generate realistic, destination-specific hotels."""
    prompt = (
        f"Generate 5 realistic hotel options for {location}, India, "
        f"for {nights} nights. Each hotel must have a unique name that "
        f"reflects the local culture, geography, or landmarks of {location}. "
        f"Prices should be realistic for this specific destination."
    )

    response = await llm_router.generate(
        prompt=prompt,
        system=HOTEL_SYSTEM_PROMPT,
        temperature=0.7,
        max_tokens=2000,
    )

    raw = response.content.strip()
    # Strip markdown fences
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if match:
        raw = match.group(1).strip()
    # Find JSON array
    match = re.search(r"\[[\s\S]+\]", raw)
    if match:
        raw = match.group(0)

    hotels = json.loads(raw)
    if not isinstance(hotels, list) or len(hotels) < 3:
        raise ValueError(f"Expected at least 3 hotels, got {len(hotels) if isinstance(hotels, list) else type(hotels)}")

    # Ensure required fields and add total_cost_inr
    for h in hotels:
        h.setdefault("amenities", ["WiFi"])
        h.setdefault("type", "budget_hotel")
        h.setdefault("rating", 4.0)
        h.setdefault("booking_url", "https://makeMyTrip.com/mock")
        h.setdefault("location", f"Near City Centre, {location}")
        h["total_cost_inr"] = h["price_per_night_inr"] * nights

    return hotels[:5]


def _generate_mock_hotels(location: str, nights: int) -> list[dict]:
    """Generate realistic mock hotels for any Indian destination (fallback)."""
    dest = location.title()

    # Destination-specific pricing adjustments
    _priceMultiplier = 1.0
    lower = location.lower()
    if lower in ("manali", "shimla", "ooty", "munnar", "darjeeling", "leh", "spiti"):
        _priceMultiplier = 1.3  # Hill station premium
    elif lower in ("mumbai", "delhi", "bangalore"):
        _priceMultiplier = 1.2  # Metro premium
    elif lower in ("goa", "pondicherry", "varanasi", "rishikesh"):
        _priceMultiplier = 0.9  # Budget-friendly destinations

    def _p(base: float) -> int:
        return int(base * _priceMultiplier)

    return [
        {
            "name": f"Backpacker's Den {dest}",
            "location": f"Old Town Area, {dest}",
            "price_per_night_inr": _p(500),
            "total_cost_inr": _p(500) * nights,
            "rating": 4.1,
            "type": "hostel",
            "amenities": ["WiFi", "Common kitchen", "Lockers", "Terrace"],
            "booking_url": "https://makeMyTrip.com/mock",
        },
        {
            "name": f"Hotel Valley View {dest}",
            "location": f"Main Road, {dest}",
            "price_per_night_inr": _p(1200),
            "total_cost_inr": _p(1200) * nights,
            "rating": 3.9,
            "type": "budget_hotel",
            "amenities": ["WiFi", "Hot water", "Room service", "Parking"],
            "booking_url": "https://makeMyTrip.com/mock",
        },
        {
            "name": f"The {dest} Grand",
            "location": f"Central Market, {dest}",
            "price_per_night_inr": _p(2500),
            "total_cost_inr": _p(2500) * nights,
            "rating": 4.3,
            "type": "3_star",
            "amenities": ["WiFi", "Restaurant", "Room service", "Garden", "Parking"],
            "booking_url": "https://makeMyTrip.com/mock",
        },
        {
            "name": f"{dest} Heritage Resort",
            "location": f"Near Top Attractions, {dest}",
            "price_per_night_inr": _p(4000),
            "total_cost_inr": _p(4000) * nights,
            "rating": 4.5,
            "type": "3_star_plus",
            "amenities": ["WiFi", "Restaurant", "Spa", "Mountain view", "Bonfire"],
            "booking_url": "https://makeMyTrip.com/mock",
        },
        {
            "name": f"Royal {dest} Palace",
            "location": f"Premium Location, {dest}",
            "price_per_night_inr": _p(7500),
            "total_cost_inr": _p(7500) * nights,
            "rating": 4.7,
            "type": "4_star",
            "amenities": ["WiFi", "Pool", "Spa", "Fine dining", "Concierge", "Gym"],
            "booking_url": "https://makeMyTrip.com/mock",
        },
    ]
