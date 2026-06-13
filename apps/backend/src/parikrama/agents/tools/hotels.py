"""
Hotels tool — searches for accommodation options at a destination.

Currently uses realistic mock data. Real API integration (Goibibo/MakeMyTrip
affiliate) planned for Phase 5. Mock data covers budget, mid-range, and premium
options with realistic Indian pricing.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Pricing tiers (INR per night)
_BUDGET_RANGE = (400, 1200)
_MID_RANGE = (1200, 3500)
_PREMIUM_RANGE = (3500, 10000)


async def search_hotels(
    location: str,
    check_in_days: int = 2,
    max_price_per_night: float | None = None,
) -> list[dict]:
    """
    Search for hotel options at a destination.

    Args:
        location: City/destination name.
        check_in_days: Number of nights.
        max_price_per_night: Filter by max price per night (INR).

    Returns:
        List of hotel option dicts, sorted by value (price/rating).
        Never raises — returns mock data on any failure.
    """
    logger.info("hotel_search_started", location=location, nights=check_in_days)

    hotels = _generate_mock_hotels(location, check_in_days)

    if max_price_per_night is not None:
        # Include all budget options + at least one mid-range for comparison
        budget_hotels = [h for h in hotels if h["price_per_night_inr"] <= max_price_per_night]
        mid_hotels = [h for h in hotels if h["price_per_night_inr"] > max_price_per_night][:1]
        hotels = budget_hotels + mid_hotels

    # Sort by value: rating / price (higher = better value)
    hotels.sort(key=lambda h: h["rating"] / max(h["price_per_night_inr"], 1), reverse=True)

    logger.info("hotel_search_complete", location=location, count=len(hotels))
    return hotels


def _generate_mock_hotels(location: str, nights: int) -> list[dict]:
    """Generate realistic mock hotels for any Indian destination."""
    dest = location.title()

    return [
        # ── Budget ───────────────────────────────────────────────────────────
        {
            "name": f"Backpacker's Inn {dest}",
            "location": f"Near Bus Stand, {dest}",
            "price_per_night_inr": 650,
            "total_cost_inr": 650 * nights,
            "rating": 3.8,
            "type": "hostel",
            "amenities": ["WiFi", "Common kitchen", "Locker"],
            "booking_url": "https://booking.com/mock",
        },
        {
            "name": f"Hotel Shiv Shakti {dest}",
            "location": f"Main Market, {dest}",
            "price_per_night_inr": 1100,
            "total_cost_inr": 1100 * nights,
            "rating": 3.6,
            "type": "budget_hotel",
            "amenities": ["WiFi", "Hot water", "Room service"],
            "booking_url": "https://booking.com/mock",
        },
        # ── Mid-range ────────────────────────────────────────────────────────
        {
            "name": f"Hotel Himalayan View {dest}",
            "location": f"Mall Road, {dest}",
            "price_per_night_inr": 2200,
            "total_cost_inr": 2200 * nights,
            "rating": 4.1,
            "type": "3_star",
            "amenities": ["WiFi", "Restaurant", "Hot water", "Room service", "Parking"],
            "booking_url": "https://booking.com/mock",
        },
        {
            "name": f"The {dest} Retreat",
            "location": f"Riverside, {dest}",
            "price_per_night_inr": 3200,
            "total_cost_inr": 3200 * nights,
            "rating": 4.3,
            "type": "3_star_plus",
            "amenities": ["WiFi", "Restaurant", "Spa", "Mountain view", "Bonfire"],
            "booking_url": "https://booking.com/mock",
        },
        # ── Premium ──────────────────────────────────────────────────────────
        {
            "name": f"Grand {dest} Resort & Spa",
            "location": f"Outskirts, {dest}",
            "price_per_night_inr": 6500,
            "total_cost_inr": 6500 * nights,
            "rating": 4.6,
            "type": "4_star",
            "amenities": [
                "WiFi",
                "Pool",
                "Spa",
                "Fine dining",
                "Helipad view",
                "Bonfire",
                "Adventure activities",
            ],
            "booking_url": "https://booking.com/mock",
        },
    ]
