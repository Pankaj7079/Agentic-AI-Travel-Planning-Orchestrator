"""
Places tool — finds points of interest at a travel destination.

Uses Google Places API when GOOGLE_PLACES_API_KEY is set.
Falls back to curated mock data with realistic Indian destinations.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# ── Mock place database ────────────────────────────────────────────────────────
# Curated attractions for popular Indian destinations
_MOCK_PLACES: dict[str, list[dict]] = {
    "manali": [
        {
            "name": "Rohtang Pass",
            "type": "scenic",
            "rating": 4.6,
            "entry_fee_inr": 550,
            "best_time": "morning",
        },
        {
            "name": "Solang Valley",
            "type": "adventure",
            "rating": 4.5,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Hadimba Devi Temple",
            "type": "temple",
            "rating": 4.4,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Mall Road",
            "type": "shopping",
            "rating": 4.2,
            "entry_fee_inr": 0,
            "best_time": "evening",
        },
        {
            "name": "Beas River Rafting",
            "type": "adventure",
            "rating": 4.5,
            "entry_fee_inr": 600,
            "best_time": "morning",
        },
        {
            "name": "Old Manali",
            "type": "culture",
            "rating": 4.3,
            "entry_fee_inr": 0,
            "best_time": "afternoon",
        },
        {
            "name": "Vashisht Hot Springs",
            "type": "wellness",
            "rating": 4.1,
            "entry_fee_inr": 50,
            "best_time": "morning",
        },
    ],
    "shimla": [
        {
            "name": "The Ridge",
            "type": "scenic",
            "rating": 4.5,
            "entry_fee_inr": 0,
            "best_time": "evening",
        },
        {
            "name": "Mall Road Shimla",
            "type": "shopping",
            "rating": 4.3,
            "entry_fee_inr": 0,
            "best_time": "afternoon",
        },
        {
            "name": "Jakhu Temple",
            "type": "temple",
            "rating": 4.4,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Kufri",
            "type": "scenic",
            "rating": 4.2,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Christ Church",
            "type": "heritage",
            "rating": 4.3,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
    ],
    "goa": [
        {
            "name": "Baga Beach",
            "type": "beach",
            "rating": 4.2,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Dudhsagar Falls",
            "type": "waterfall",
            "rating": 4.6,
            "entry_fee_inr": 400,
            "best_time": "morning",
        },
        {
            "name": "Basilica of Bom Jesus",
            "type": "heritage",
            "rating": 4.5,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Anjuna Flea Market",
            "type": "shopping",
            "rating": 4.1,
            "entry_fee_inr": 0,
            "best_time": "afternoon",
        },
        {
            "name": "Fort Aguada",
            "type": "heritage",
            "rating": 4.3,
            "entry_fee_inr": 35,
            "best_time": "evening",
        },
    ],
    "jaipur": [
        {
            "name": "Amber Fort",
            "type": "heritage",
            "rating": 4.7,
            "entry_fee_inr": 100,
            "best_time": "morning",
        },
        {
            "name": "Hawa Mahal",
            "type": "heritage",
            "rating": 4.5,
            "entry_fee_inr": 50,
            "best_time": "morning",
        },
        {
            "name": "City Palace",
            "type": "heritage",
            "rating": 4.5,
            "entry_fee_inr": 200,
            "best_time": "morning",
        },
        {
            "name": "Jantar Mantar",
            "type": "heritage",
            "rating": 4.3,
            "entry_fee_inr": 50,
            "best_time": "morning",
        },
        {
            "name": "Johari Bazaar",
            "type": "shopping",
            "rating": 4.2,
            "entry_fee_inr": 0,
            "best_time": "afternoon",
        },
    ],
    "kerala": [
        {
            "name": "Alleppey Backwaters",
            "type": "scenic",
            "rating": 4.7,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Munnar Tea Gardens",
            "type": "scenic",
            "rating": 4.6,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Varkala Beach",
            "type": "beach",
            "rating": 4.4,
            "entry_fee_inr": 0,
            "best_time": "morning",
        },
        {
            "name": "Periyar Wildlife Sanctuary",
            "type": "wildlife",
            "rating": 4.5,
            "entry_fee_inr": 300,
            "best_time": "morning",
        },
    ],
}

_DEFAULT_PLACES = [
    {
        "name": "City Centre",
        "type": "general",
        "rating": 4.0,
        "entry_fee_inr": 0,
        "best_time": "morning",
    },
    {
        "name": "Local Market",
        "type": "shopping",
        "rating": 4.0,
        "entry_fee_inr": 0,
        "best_time": "afternoon",
    },
    {
        "name": "Main Temple/Mosque/Church",
        "type": "religious",
        "rating": 4.2,
        "entry_fee_inr": 0,
        "best_time": "morning",
    },
    {
        "name": "Viewpoint / Hilltop",
        "type": "scenic",
        "rating": 4.3,
        "entry_fee_inr": 50,
        "best_time": "sunrise",
    },
    {
        "name": "Local Museum",
        "type": "culture",
        "rating": 3.9,
        "entry_fee_inr": 100,
        "best_time": "afternoon",
    },
]


async def search_places(destination: str, max_results: int = 7) -> list[dict]:
    """
    Search for points of interest at a destination.

    Args:
        destination: City or place name.
        max_results: Maximum number of places to return.

    Returns:
        List of place dicts with name, type, rating, entry_fee_inr, best_time.
    """
    from parikrama.config import settings  # lazy import

    if not getattr(settings, "GOOGLE_PLACES_API_KEY", ""):
        logger.info("places_api_key_missing", destination=destination, fallback="mock")
        return _get_mock_places(destination, max_results)

    try:
        return await _search_google_places(destination, max_results, settings.GOOGLE_PLACES_API_KEY)
    except Exception as exc:
        logger.warning("places_api_failed", destination=destination, error=str(exc)[:100])
        return _get_mock_places(destination, max_results)


async def _search_google_places(destination: str, max_results: int, api_key: str) -> list[dict]:
    """Call Google Places API Text Search."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={
                "query": f"tourist attractions in {destination} India",
                "key": api_key,
                "language": "en",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    api_status = data.get("status")
    if api_status not in ("OK", "ZERO_RESULTS"):
        raise ValueError(
            f"Google Places API error: {api_status} - {data.get('error_message', 'Unknown error')}"
        )

    places = []
    for item in data.get("results", [])[:max_results]:
        places.append(
            {
                "name": item["name"],
                "type": item.get("types", ["general"])[0],
                "rating": item.get("rating", 4.0),
                "entry_fee_inr": 0,  # Google Places doesn't provide pricing
                "best_time": "morning",
                "address": item.get("formatted_address", ""),
            }
        )

    logger.info("places_fetched", destination=destination, count=len(places))
    return places


def _get_mock_places(destination: str, max_results: int) -> list[dict]:
    """Return curated mock places for known destinations."""
    key = destination.lower().strip()
    # Try exact match first, then partial match
    places = _MOCK_PLACES.get(key)
    if not places:
        for known_dest, known_places in _MOCK_PLACES.items():
            if known_dest in key or key in known_dest:
                places = known_places
                break
    if not places:
        places = _DEFAULT_PLACES

    return places[:max_results]
