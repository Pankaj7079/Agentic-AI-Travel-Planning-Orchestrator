"""
Web search tool — fetches live travel info from Tavily (primary) or DuckDuckGo (fallback).

Used by the ResearchAgent to get real-time travel data:
  - Best time to visit, weather tips
  - Top attractions, hidden gems
  - Food recommendations, local transport
  - Budget tips, safety advice

Tavily: AI-optimized search, returns clean content (requires API key).
DuckDuckGo: Free, no API key, used as fallback when Tavily is unavailable.
"""

from __future__ import annotations

import structlog

from parikrama.config import settings

logger = structlog.get_logger(__name__)

# Lazy-loaded clients
_tavily_client = None
_ddgs_client = None


def _get_tavily():
    """Lazy-load Tavily client."""
    global _tavily_client
    if _tavily_client is None:
        from tavily import TavilyClient

        _tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    return _tavily_client


def _get_ddgs():
    """Lazy-load DuckDuckGo client."""
    global _ddgs_client
    if _ddgs_client is None:
        from ddgs import DDGS

        _ddgs_client = DDGS()
    return _ddgs_client


async def search_web(
    destination: str,
    max_results: int = 8,
) -> str:
    """Search the web for travel information about a destination.

    Tries Tavily first (AI-optimized, clean results).
    Falls back to DuckDuckGo if Tavily is not configured or fails.

    Args:
        destination: City or region to search for (e.g., "Goa", "Manali").
        max_results: Maximum number of search results to return.

    Returns:
        Combined text from search results, or empty string on failure.
    """
    # Try Tavily first
    if settings.TAVILY_API_KEY:
        try:
            result = await _search_tavily(destination, max_results)
            if result:
                return result
        except Exception as exc:
            logger.warning(
                "tavily_search_failed", error=str(exc)[:100], falling_back_to="duckduckgo"
            )

    # Fallback to DuckDuckGo
    try:
        return await _search_duckduckgo(destination, max_results)
    except Exception as exc:
        logger.warning("duckduckgo_search_failed", error=str(exc)[:100])
        return ""


async def _search_tavily(destination: str, max_results: int = 8) -> str:
    """Search using Tavily — AI-optimized web search."""
    import asyncio

    queries = [
        f"best places to visit in {destination} travel guide India",
        f"{destination} travel budget tips food recommendations local transport",
        f"{destination} weather best time to visit how to reach from Patna Delhi",
    ]

    all_results: list[str] = []

    for query in queries:
        try:

            def _sync_tavily(q: str = query):
                client = _get_tavily()
                response = client.search(
                    query=q,
                    max_results=max(max_results // len(queries), 2),
                    search_depth="basic",
                    include_answer=False,
                )
                results = response.get("results", [])
                texts = []
                for r in results:
                    content = r.get("content", "")
                    title = r.get("title", "")
                    if content:
                        texts.append(f"{title}: {content}" if title else content)
                return texts

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, _sync_tavily)
            all_results.extend(results)
        except Exception as exc:
            logger.warning("tavily_query_failed", query=query[:60], error=str(exc)[:80])

    if not all_results:
        return ""

    # Deduplicate
    seen = set()
    unique: list[str] = []
    for r in all_results:
        key = r[:50].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info("tavily_search_complete", destination=destination, results=len(unique))
    return "\n\n".join(unique[:max_results])


async def _search_duckduckgo(destination: str, max_results: int = 8) -> str:
    """Search using DuckDuckGo — free fallback."""
    import asyncio

    queries = [
        f"best places to visit in {destination} travel guide",
        f"{destination} travel budget tips food recommendations",
        f"{destination} weather best time to visit how to reach",
    ]

    all_results: list[str] = []

    for query in queries:
        try:

            def _sync_ddgs(q: str = query):
                client = _get_ddgs()
                results = client.text(q, max_results=max_results // len(queries) + 1)
                texts = []
                for r in results:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    if body:
                        texts.append(f"{title}: {body}" if title else body)
                return texts

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, _sync_ddgs)
            all_results.extend(results)
        except Exception as exc:
            logger.warning("ddgs_query_failed", query=query[:60], error=str(exc)[:80])

    if not all_results:
        return ""

    # Deduplicate
    seen = set()
    unique: list[str] = []
    for r in all_results:
        key = r[:50].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info("ddgs_search_complete", destination=destination, results=len(unique))
    return "\n\n".join(unique[:max_results])
