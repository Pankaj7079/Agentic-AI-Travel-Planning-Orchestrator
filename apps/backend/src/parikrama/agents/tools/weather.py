"""
Weather tool — fetches real forecasts from OpenWeatherMap.

Falls back to realistic mock data when:
- OPENWEATHERMAP_API_KEY is not set (development)
- API call fails (graceful degradation)

Free tier: 1,000 calls/day, 5-day forecast.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import structlog

logger = structlog.get_logger(__name__)

OPENWEATHERMAP_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Hill stations known for temperature drops — extra advisory
_HILL_STATIONS = frozenset(
    ["manali", "shimla", "leh", "ladakh", "darjeeling", "ooty", "mussoorie", "nainital", "kodaikanal"]
)


async def get_weather_forecast(location: str, days: int = 5) -> dict:
    """
    Fetch weather forecast for an Indian travel destination.

    Args:
        location: City/place name (e.g., "Manali").
        days: Number of forecast days (1-7).

    Returns:
        Dict with keys: location, dates, forecasts (list), advisory (str).
        Never raises — returns mock on any failure.
    """
    from parikrama.config import settings  # lazy import to avoid circular deps

    if not getattr(settings, "OPENWEATHERMAP_API_KEY", ""):
        logger.info("weather_api_key_missing", location=location, fallback="mock")
        return _mock_weather(location, days)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                OPENWEATHERMAP_URL,
                params={
                    "q": f"{location},IN",
                    "appid": settings.OPENWEATHERMAP_API_KEY,
                    "units": "metric",
                    "cnt": min(days * 8, 40),  # 8 intervals/day, API max 40
                },
            )
            response.raise_for_status()
            data = response.json()

        forecasts = _parse_forecasts(data, days)
        advisory = _generate_advisory(forecasts, location)
        logger.info("weather_fetched", location=location, days=len(forecasts))
        return {
            "location": location,
            "dates": [f["date"] for f in forecasts],
            "forecasts": forecasts,
            "advisory": advisory,
        }
    except Exception as exc:
        logger.warning("weather_api_failed", location=location, error=str(exc)[:100])
        return _mock_weather(location, days)


# ── Private helpers ────────────────────────────────────────────────────────────


def _parse_forecasts(data: dict, days: int) -> list[dict]:
    """Parse OpenWeatherMap API response into our simplified format."""
    forecasts = []
    seen_dates: set[str] = set()
    for item in data.get("list", []):
        date = item["dt_txt"].split(" ")[0]
        if date not in seen_dates and len(forecasts) < days:
            seen_dates.add(date)
            forecasts.append(
                {
                    "date": date,
                    "temp_min": round(item["main"]["temp_min"], 1),
                    "temp_max": round(item["main"]["temp_max"], 1),
                    "description": item["weather"][0]["description"],
                    "humidity": item["main"]["humidity"],
                    "wind_speed": item["wind"]["speed"],
                }
            )
    return forecasts


def _generate_advisory(forecasts: list[dict], location: str) -> str:
    """Generate practical packing/timing advisory from forecast data."""
    if not forecasts:
        return "Weather data unavailable. Pack for varied conditions."

    avg_max = sum(f["temp_max"] for f in forecasts) / len(forecasts)
    has_rain = any("rain" in f["description"].lower() for f in forecasts)
    has_snow = any("snow" in f["description"].lower() for f in forecasts)

    tips = []
    if has_snow:
        tips.append("Snow expected — pack heavy thermals, woolen socks, and waterproof boots")
    elif avg_max < 10:
        tips.append("Very cold — pack heavy woolens, thermals, gloves, and a balaclava")
    elif avg_max < 20:
        tips.append("Cool weather — carry light jackets and layered clothing")
    else:
        tips.append("Pleasant temperatures — light cotton clothing is fine")

    if has_rain:
        tips.append("carry rain gear and waterproof covers for bags")

    if location.lower() in _HILL_STATIONS:
        tips.append("temperatures drop sharply after sunset even in summer — always carry a jacket")

    return "; ".join(tips).capitalize() + "."


def _mock_weather(location: str, days: int) -> dict:
    """Realistic mock weather data for development without an API key."""
    base = datetime.now(tz=UTC)
    is_hill = location.lower() in _HILL_STATIONS

    forecasts = []
    for i in range(days):
        date = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        temp_min = (5 + i) if is_hill else (22 + i)
        temp_max = (15 + i) if is_hill else (32 + i)
        forecasts.append(
            {
                "date": date,
                "temp_min": temp_min,
                "temp_max": temp_max,
                "description": "partly cloudy" if i % 3 != 0 else "light rain",
                "humidity": 65 + (i * 2),
                "wind_speed": 3.5,
            }
        )

    advisory = _generate_advisory(forecasts, location)
    return {
        "location": location,
        "dates": [f["date"] for f in forecasts],
        "forecasts": forecasts,
        "advisory": f"[Mock data] {advisory}",
    }
