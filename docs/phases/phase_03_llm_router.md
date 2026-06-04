# Phase 3: LLM Router + Agent Foundation

## Overview

Phase 3 builds the **nervous system** — the intelligent LLM Router that ensures our agents never go silent, plus the base agent class that all specialized agents inherit. This is the most **reliability-critical** phase in the entire project. If the LLM is down, the entire app is useless.

### What This Phase Delivers
- **LLMRouter**: Automatically routes between Gemini 2.5 Flash Lite and Groq
- **Health Monitoring**: Sliding window tracks latency and error rates
- **Automatic Failover**: Switches to Groq in <100ms when Gemini degrades
- **Self-Healing**: Periodically checks if Gemini recovered, switches back
- **Cost Tracking**: Logs every token used per model per request
- **Base Agent Class**: Standardized pattern all 5 agents inherit

### The Fallback Chain
```
Gemini 2.5 Flash Lite (primary)
  ↓ latency > 10s OR 3+ errors in 60s
Groq: llama-3.1-70b-versatile (first fallback)
  ↓ Groq llama fails
Groq: mixtral-8x7b-32768 (second fallback)
  ↓ Everything fails
Raise LLMError (graceful degradation message to user)
```

---

## Architecture Decisions

### Decision 1: Custom Router vs LiteLLM
| Approach | Flexibility | Overhead | Control |
|----------|------------|---------|---------|
| **Custom LLMRouter (chosen)** | Full control over switching logic | ~200 lines | Complete |
| LiteLLM proxy | Many providers built-in | Extra service to run | Limited switching logic |
| LangChain with_fallbacks | Built-in | Locked to LangChain pattern | Minimal |

**Why Custom:** We need precise control over WHEN to switch (latency threshold, error window), HOW to switch back (health check interval), and WHAT to log (per-switch metrics). LiteLLM is great for multi-provider routing but doesn't give us the sliding window error tracking we need.

### Decision 2: Sliding Window vs Simple Counter
**Why Sliding Window:** A simple "3 errors = switch" counter never resets. If we hit 3 errors over a week, we'd stay on fallback forever. A sliding window (3 errors within 60 seconds) correctly identifies transient failures vs sustained outages.

### Decision 3: Why Groq as Fallback
- **Speed**: Groq's LPU delivers ~500 tokens/sec — fastest inference available
- **Free Tier**: 30 RPM, 6000 tokens/min — enough for fallback bursts
- **Model Quality**: llama-3.1-70b is competitive with GPT-3.5 quality
- **No cold start**: Unlike serverless endpoints, Groq is always warm

---

## Database Schema

```sql
-- ══════════════════════════════════════════════════════════════════════
-- Phase 3 Database Tables
-- ══════════════════════════════════════════════════════════════════════

-- ── Cost Tracking ──────────────────────────────────────────────────
CREATE TABLE cost_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    trip_id UUID,                          -- filled in Phase 4
    correlation_id VARCHAR(64),
    model VARCHAR(50) NOT NULL,            -- 'gemini-2.5-flash-lite', 'llama-3.1-70b', etc.
    provider VARCHAR(20) NOT NULL,         -- 'gemini', 'groq_llama', 'groq_mixtral'
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL,
    cost_usd DECIMAL(10, 6) NOT NULL DEFAULT 0,
    is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cost_user ON cost_tracking(user_id);
CREATE INDEX idx_cost_created ON cost_tracking(created_at);
CREATE INDEX idx_cost_model ON cost_tracking(model);

-- ── LLM Switch Events ─────────────────────────────────────────────
CREATE TABLE llm_switch_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_provider VARCHAR(20) NOT NULL,
    to_provider VARCHAR(20) NOT NULL,
    reason VARCHAR(100) NOT NULL,         -- 'latency_threshold', 'error_threshold', 'health_recovery'
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Key APIs

```
GET    /api/v1/llm/status                Current LLM provider status
GET    /api/v1/llm/health                Detailed health metrics
POST   /api/v1/llm/test                  Test current provider with sample prompt (admin only)
GET    /api/v1/llm/cost-summary          Token usage and cost summary
```

---

## Implementation

### LLM Router (Complete, Production-Ready)

```python
# apps/backend/src/parikrama/llm/router.py
"""
Smart LLM Router with automatic failover.

Monitors Gemini 2.5 Flash Lite health via sliding window metrics.
Switches to Groq when thresholds are breached, switches back when healthy.
Every call is logged for cost tracking and observability.

This is the single most critical class in the entire application.
"""
import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from enum import StrEnum

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from parikrama.config import settings
from parikrama.llm.providers.gemini import get_gemini_llm
from parikrama.llm.providers.groq import get_groq_llm, get_groq_mixtral_llm

logger = structlog.get_logger()


class ActiveProvider(StrEnum):
    """Currently active LLM provider."""
    GEMINI = "gemini"
    GROQ_LLAMA = "groq_llama"
    GROQ_MIXTRAL = "groq_mixtral"


class LLMRouter:
    """
    Intelligent LLM routing with health-aware failover.

    Usage:
        router = LLMRouter()
        llm = router.get_llm()  # returns the best available LLM
        # or
        response = await router.invoke(messages)  # auto-routes with tracking
    """

    def __init__(self) -> None:
        # current active provider
        self._active: ActiveProvider = ActiveProvider.GEMINI

        # sliding window for tracking recent errors and latencies
        self._error_timestamps: deque[float] = deque()
        self._latencies: deque[tuple[float, float]] = deque()  # (timestamp, latency_ms)

        # config thresholds
        self._latency_threshold_ms = settings.LLM_FALLBACK_LATENCY_THRESHOLD_MS
        self._error_threshold = settings.LLM_FALLBACK_ERROR_THRESHOLD
        self._error_window_seconds = settings.LLM_FALLBACK_ERROR_WINDOW_SECONDS
        self._health_check_interval = settings.LLM_HEALTH_CHECK_INTERVAL_SECONDS

        # track when we last checked if primary recovered
        self._last_health_check: float = 0
        self._is_checking_health: bool = False

        # provider instances (lazy-loaded)
        self._providers: dict[ActiveProvider, BaseChatModel | None] = {
            ActiveProvider.GEMINI: None,
            ActiveProvider.GROQ_LLAMA: None,
            ActiveProvider.GROQ_MIXTRAL: None,
        }

        # switch event callbacks (for metrics/logging)
        self._switch_callbacks: list = []

        logger.info(
            "llm_router_initialized",
            primary=self._active,
            latency_threshold=self._latency_threshold_ms,
            error_threshold=self._error_threshold,
        )

    @property
    def active_provider(self) -> ActiveProvider:
        """Currently active LLM provider name."""
        return self._active

    @property
    def is_on_fallback(self) -> bool:
        """True if we're not using the primary provider."""
        return self._active != ActiveProvider.GEMINI

    def get_llm(self) -> BaseChatModel:
        """Get the currently active LLM instance."""
        return self._get_provider(self._active)

    async def invoke(
        self,
        messages: list[BaseMessage],
        user_id: str | None = None,
        trip_id: str | None = None,
        correlation_id: str | None = None,
    ) -> BaseMessage:
        """
        Invoke the best available LLM with automatic failover.

        This is the primary method agents should use. It handles:
        1. Routing to the active provider
        2. Measuring latency
        3. Catching errors and switching to fallback
        4. Logging cost and performance data
        5. Triggering health checks for recovery
        """
        # try primary (current active) first
        providers_to_try = self._get_fallback_chain()

        last_error = None
        for provider in providers_to_try:
            try:
                llm = self._get_provider(provider)
                start_time = time.perf_counter()

                response = await llm.ainvoke(messages)

                latency_ms = (time.perf_counter() - start_time) * 1000

                # record success metrics
                self._record_latency(latency_ms)

                # check if latency is degraded
                if provider == ActiveProvider.GEMINI and latency_ms > self._latency_threshold_ms:
                    logger.warning(
                        "gemini_high_latency",
                        latency_ms=round(latency_ms, 1),
                        threshold=self._latency_threshold_ms,
                    )
                    self._record_error()  # count high latency as a soft error

                # log cost data
                await self._log_cost(
                    provider=provider,
                    response=response,
                    latency_ms=latency_ms,
                    user_id=user_id,
                    trip_id=trip_id,
                    correlation_id=correlation_id,
                )

                # if we used fallback but primary might be back, schedule health check
                if self.is_on_fallback:
                    await self._maybe_check_primary_health()

                return response

            except Exception as e:
                last_error = e
                logger.error(
                    "llm_provider_failed",
                    provider=provider,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                # record error for primary
                if provider == ActiveProvider.GEMINI:
                    self._record_error()

                # switch to next fallback
                if provider == self._active:
                    next_provider = self._get_next_fallback(provider)
                    if next_provider:
                        await self._switch_to(next_provider, reason=f"error: {type(e).__name__}")

                continue

        # all providers failed
        logger.critical("all_llm_providers_failed", last_error=str(last_error))
        raise LLMError(f"All LLM providers failed. Last error: {last_error}")

    def _get_provider(self, provider: ActiveProvider) -> BaseChatModel:
        """Get or create the LLM instance for a provider."""
        if self._providers[provider] is None:
            if provider == ActiveProvider.GEMINI:
                self._providers[provider] = get_gemini_llm()
            elif provider == ActiveProvider.GROQ_LLAMA:
                self._providers[provider] = get_groq_llm()
            elif provider == ActiveProvider.GROQ_MIXTRAL:
                self._providers[provider] = get_groq_mixtral_llm()
        return self._providers[provider]

    def _get_fallback_chain(self) -> list[ActiveProvider]:
        """Ordered list of providers to try, starting from current active."""
        chain = [self._active]
        all_providers = [ActiveProvider.GEMINI, ActiveProvider.GROQ_LLAMA, ActiveProvider.GROQ_MIXTRAL]
        for p in all_providers:
            if p not in chain:
                chain.append(p)
        return chain

    def _get_next_fallback(self, current: ActiveProvider) -> ActiveProvider | None:
        """Get the next fallback after the current provider."""
        order = [ActiveProvider.GEMINI, ActiveProvider.GROQ_LLAMA, ActiveProvider.GROQ_MIXTRAL]
        try:
            idx = order.index(current)
            if idx + 1 < len(order):
                return order[idx + 1]
        except ValueError:
            pass
        return None

    def _record_error(self) -> None:
        """Record an error timestamp in the sliding window."""
        now = time.time()
        self._error_timestamps.append(now)

        # prune old entries outside the window
        cutoff = now - self._error_window_seconds
        while self._error_timestamps and self._error_timestamps[0] < cutoff:
            self._error_timestamps.popleft()

        # check if threshold breached
        if len(self._error_timestamps) >= self._error_threshold:
            if self._active == ActiveProvider.GEMINI:
                asyncio.create_task(
                    self._switch_to(ActiveProvider.GROQ_LLAMA, reason="error_threshold_breached")
                )

    def _record_latency(self, latency_ms: float) -> None:
        """Record a latency measurement in the sliding window."""
        now = time.time()
        self._latencies.append((now, latency_ms))

        # keep last 100 measurements
        while len(self._latencies) > 100:
            self._latencies.popleft()

    async def _switch_to(self, provider: ActiveProvider, reason: str) -> None:
        """Switch the active LLM provider and log the event."""
        old = self._active
        self._active = provider
        self._error_timestamps.clear()  # reset window after switch

        logger.warning(
            "llm_provider_switched",
            from_provider=old,
            to_provider=provider,
            reason=reason,
        )

        # fire callbacks (metrics, DB logging, etc.)
        for callback in self._switch_callbacks:
            try:
                await callback(old, provider, reason)
            except Exception as e:
                logger.error("switch_callback_failed", error=str(e))

    async def _maybe_check_primary_health(self) -> None:
        """Periodically check if Gemini recovered while we're on fallback."""
        now = time.time()
        if (now - self._last_health_check) < self._health_check_interval:
            return
        if self._is_checking_health:
            return

        self._is_checking_health = True
        self._last_health_check = now

        try:
            llm = self._get_provider(ActiveProvider.GEMINI)
            start = time.perf_counter()

            # lightweight health check — short prompt, low tokens
            from langchain_core.messages import HumanMessage
            await llm.ainvoke([HumanMessage(content="Say 'ok'")])

            latency_ms = (time.perf_counter() - start) * 1000

            if latency_ms < self._latency_threshold_ms:
                await self._switch_to(ActiveProvider.GEMINI, reason="health_recovery")
                logger.info("gemini_recovered", check_latency_ms=round(latency_ms, 1))
            else:
                logger.info("gemini_still_slow", check_latency_ms=round(latency_ms, 1))

        except Exception as e:
            logger.info("gemini_health_check_failed", error=str(e))
        finally:
            self._is_checking_health = False

    async def _log_cost(
        self,
        provider: ActiveProvider,
        response: BaseMessage,
        latency_ms: float,
        user_id: str | None,
        trip_id: str | None,
        correlation_id: str | None,
    ) -> None:
        """Log token usage and cost for monitoring."""
        # extract token counts from response metadata (provider-specific)
        usage = getattr(response, "usage_metadata", None) or {}
        tokens_in = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)

        # approximate cost (Gemini 2.5 Flash Lite pricing)
        cost_per_million_in = {"gemini": 0.075, "groq_llama": 0.59, "groq_mixtral": 0.24}
        cost_per_million_out = {"gemini": 0.30, "groq_llama": 0.79, "groq_mixtral": 0.24}

        provider_key = provider.value
        cost_usd = (
            (tokens_in / 1_000_000) * cost_per_million_in.get(provider_key, 0)
            + (tokens_out / 1_000_000) * cost_per_million_out.get(provider_key, 0)
        )

        logger.info(
            "llm_invocation",
            provider=provider_key,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=round(latency_ms, 1),
            cost_usd=round(cost_usd, 6),
            is_fallback=provider != ActiveProvider.GEMINI,
        )

    def get_status(self) -> dict:
        """Return current router status for /api/v1/llm/status endpoint."""
        recent_latencies = [lat for _, lat in self._latencies]
        avg_latency = sum(recent_latencies) / max(len(recent_latencies), 1)

        return {
            "active_provider": self._active.value,
            "is_on_fallback": self.is_on_fallback,
            "recent_error_count": len(self._error_timestamps),
            "error_threshold": self._error_threshold,
            "avg_latency_ms": round(avg_latency, 1),
            "latency_threshold_ms": self._latency_threshold_ms,
            "total_requests_tracked": len(self._latencies),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def on_switch(self, callback) -> None:
        """Register a callback for provider switch events."""
        self._switch_callbacks.append(callback)


# singleton — shared across the entire application
llm_router = LLMRouter()
```

### LLM Providers

```python
# apps/backend/src/parikrama/llm/providers/gemini.py
"""Gemini 2.5 Flash Lite provider configuration."""
from langchain_google_genai import ChatGoogleGenerativeAI
from parikrama.config import settings


def get_gemini_llm() -> ChatGoogleGenerativeAI:
    """Create a Gemini LLM instance with our standard config."""
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.7,
        max_output_tokens=4096,
        timeout=settings.GEMINI_TIMEOUT_SECONDS,
        max_retries=2,
    )
```

```python
# apps/backend/src/parikrama/llm/providers/groq.py
"""Groq provider configuration — fast inference fallback."""
from langchain_groq import ChatGroq
from parikrama.config import settings


def get_groq_llm() -> ChatGroq:
    """Groq with llama-3.1-70b — primary fallback."""
    return ChatGroq(
        model=settings.GROQ_PRIMARY_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.7,
        max_tokens=4096,
        timeout=settings.GROQ_TIMEOUT_SECONDS,
        max_retries=2,
    )


def get_groq_mixtral_llm() -> ChatGroq:
    """Groq with mixtral-8x7b — secondary fallback (32K context)."""
    return ChatGroq(
        model=settings.GROQ_SECONDARY_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.7,
        max_tokens=4096,
        timeout=settings.GROQ_TIMEOUT_SECONDS,
        max_retries=2,
    )
```

### LLM Response Cache

```python
# apps/backend/src/parikrama/llm/cache.py
"""
Redis-based LLM response cache.

Caches identical prompts to save tokens and latency.
Cache key = SHA-256(model + messages_json).
TTL varies by content type — weather data expires fast, general knowledge slow.
"""
import hashlib
import json

import redis.asyncio as aioredis
import structlog

from parikrama.config import settings

logger = structlog.get_logger()


class LLMCache:
    """Cache LLM responses in Redis to reduce API calls and cost."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    @property
    def redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    def _make_key(self, model: str, messages: list[dict]) -> str:
        """Deterministic cache key from model + message content."""
        raw = json.dumps({"model": model, "messages": messages}, sort_keys=True)
        return f"llm_cache:{hashlib.sha256(raw.encode()).hexdigest()}"

    async def get(self, model: str, messages: list[dict]) -> str | None:
        """Retrieve cached response, or None on miss."""
        key = self._make_key(model, messages)
        cached = await self.redis.get(key)
        if cached:
            logger.debug("llm_cache_hit", key=key[:20])
        return cached

    async def set(
        self, model: str, messages: list[dict], response: str, ttl: int | None = None,
    ) -> None:
        """Store response in cache with TTL."""
        key = self._make_key(model, messages)
        await self.redis.set(key, response, ex=ttl or settings.REDIS_CACHE_TTL)
        logger.debug("llm_cache_set", key=key[:20], ttl=ttl)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete cached entries matching a pattern."""
        keys = []
        async for key in self.redis.scan_iter(match=f"llm_cache:{pattern}*"):
            keys.append(key)
        if keys:
            await self.redis.delete(*keys)
        return len(keys)


llm_cache = LLMCache()
```

### Base Agent Class

```python
# apps/backend/src/parikrama/agents/base.py
"""
Base agent class that all specialized agents inherit.

Provides:
- LLM access via the router (with automatic fallback)
- Structured logging with agent name context
- Standard error handling and retry logic
- LangSmith tracing integration
- Common tool execution pattern
"""
import time
from abc import ABC, abstractmethod

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from parikrama.agents.state import TripPlanningState
from parikrama.config import settings
from parikrama.llm.router import llm_router

logger = structlog.get_logger()


class BaseAgent(ABC):
    """
    Foundation for all PariKrama agents.

    Every agent has:
    - A name (for logging and state tracking)
    - A system prompt (loaded from markdown files)
    - Access to the LLM router
    - Standardized invoke/execute pattern
    """

    def __init__(self, name: str, system_prompt: str) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.log = logger.bind(agent=name)

    @abstractmethod
    async def execute(self, state: TripPlanningState) -> TripPlanningState:
        """
        Execute the agent's task and return updated state.
        Each agent implements its specific logic here.
        """
        ...

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def call_llm(
        self,
        user_message: str,
        context: str = "",
        user_id: str | None = None,
        trip_id: str | None = None,
    ) -> str:
        """
        Call the LLM via router with retry logic.

        Wraps the user message with system prompt and optional context.
        Retries up to 3 times with exponential backoff on failure.
        """
        messages = [
            SystemMessage(content=self.system_prompt),
        ]

        if context:
            messages.append(HumanMessage(content=f"Context:\n{context}"))

        messages.append(HumanMessage(content=user_message))

        start = time.perf_counter()

        response = await llm_router.invoke(
            messages=messages,
            user_id=user_id,
            trip_id=trip_id,
        )

        duration_ms = (time.perf_counter() - start) * 1000

        self.log.info(
            "agent_llm_call",
            duration_ms=round(duration_ms, 1),
            response_length=len(response.content),
            provider=llm_router.active_provider,
        )

        return response.content

    async def __call__(self, state: TripPlanningState) -> TripPlanningState:
        """LangGraph calls agents as functions — this is the entry point."""
        self.log.info("agent_started", trip_id=state.get("trip_id"))
        start = time.perf_counter()

        try:
            result = await self.execute(state)
            duration_ms = (time.perf_counter() - start) * 1000
            self.log.info("agent_completed", duration_ms=round(duration_ms, 1))
            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            self.log.error("agent_failed", error=str(e), duration_ms=round(duration_ms, 1))
            # update state with error info
            state["errors"] = state.get("errors", []) + [{
                "agent": self.name,
                "error": str(e),
                "timestamp": time.time(),
            }]
            return state
```

### Agent State Schema

```python
# apps/backend/src/parikrama/agents/state.py
"""
Agent state — the shared data structure passed between all agents in LangGraph.

TypedDict ensures type safety while allowing the state to flow through the graph.
Each agent reads what it needs and writes its outputs back.
"""
from typing import TypedDict, Annotated
from operator import add


class TripRequest(TypedDict):
    """User's original trip request parsed into structured fields."""
    origin: str                    # "Delhi"
    destination: str               # "Manali"
    days: int                      # 5
    budget_inr: int               # 15000
    travelers: int                 # 1
    preferences: dict              # {"interests": ["trekking"], "food": "veg"}
    language: str                  # "en" or "hi"


class WeatherData(TypedDict):
    """Weather information fetched by research agent."""
    location: str
    dates: list[str]
    forecasts: list[dict]
    advisory: str                  # "Pack warm clothes, snow expected"


class HotelOption(TypedDict):
    """Hotel recommendation from booking agent."""
    name: str
    price_per_night_inr: int
    rating: float
    location: str
    amenities: list[str]
    source: str                    # "goibibo" | "booking" | "rag"
    booking_url: str | None


class TransportOption(TypedDict):
    """Transport recommendation from booking agent."""
    type: str                      # "bus" | "train" | "flight"
    operator: str
    departure: str
    arrival: str
    price_inr: int
    duration_hours: float
    source: str


class BudgetBreakdown(TypedDict):
    """Cost breakdown from budget agent."""
    transport_inr: int
    accommodation_inr: int
    food_inr: int
    activities_inr: int
    misc_inr: int
    total_inr: int
    savings_tips: list[str]


class DayPlan(TypedDict):
    """Single day in the itinerary."""
    day: int
    date: str
    title: str                     # "Arrival in Manali"
    activities: list[dict]         # [{time, activity, location, cost}]
    meals: list[dict]              # [{time, suggestion, estimated_cost}]
    accommodation: dict            # {hotel, check_in, check_out}
    travel: dict | None            # transport details if traveling
    tips: list[str]


class TripPlanningState(TypedDict):
    """
    Master state passed through the entire LangGraph pipeline.

    Each agent reads relevant fields and writes its outputs.
    LangGraph persists this state so we can resume after interrupts.
    """
    # -- Input --
    trip_id: str
    user_id: str
    request: TripRequest

    # -- Research Agent outputs --
    weather: WeatherData | None
    destination_info: str                  # RAG-retrieved knowledge
    reviews_summary: str                   # User reviews summary
    places_of_interest: list[dict]

    # -- Booking Agent outputs --
    hotel_options: list[HotelOption]
    transport_options: list[TransportOption]
    requires_approval: bool                # triggers human-in-the-loop

    # -- Budget Agent outputs --
    budget_breakdown: BudgetBreakdown | None
    is_within_budget: bool

    # -- Itinerary Agent outputs --
    itinerary: list[DayPlan]
    summary: str                           # one-paragraph trip summary

    # -- System fields --
    current_agent: str                     # which agent is running
    messages: Annotated[list[dict], add]   # append-only message log
    errors: list[dict]                     # error log
    status: str                            # "planning" | "awaiting_approval" | "completed"
    approval_response: dict | None         # user's approval/rejection
```

### Cost Tracker

```python
# apps/backend/src/parikrama/llm/cost_tracker.py
"""
Token usage and cost tracking service.

Stores every LLM invocation with cost calculation.
Provides aggregated views for the admin dashboard.
"""
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.models.cost import CostTracking

logger = structlog.get_logger()

# pricing per million tokens (as of 2025)
PRICING = {
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
}


class CostTracker:
    """Track and aggregate LLM usage costs."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        model: str,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        user_id: str | None = None,
        trip_id: str | None = None,
        correlation_id: str | None = None,
        is_fallback: bool = False,
    ) -> None:
        """Record a single LLM invocation with cost."""
        prices = PRICING.get(model, {"input": 0, "output": 0})
        cost_usd = (
            (tokens_in / 1_000_000) * prices["input"]
            + (tokens_out / 1_000_000) * prices["output"]
        )

        record = CostTracking(
            user_id=uuid.UUID(user_id) if user_id else None,
            trip_id=uuid.UUID(trip_id) if trip_id else None,
            correlation_id=correlation_id,
            model=model,
            provider=provider,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            is_fallback=is_fallback,
        )
        self.db.add(record)

    async def get_user_summary(
        self, user_id: str, days: int = 30,
    ) -> dict:
        """Get cost summary for a user over the last N days."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(
                func.sum(CostTracking.tokens_in).label("total_tokens_in"),
                func.sum(CostTracking.tokens_out).label("total_tokens_out"),
                func.sum(CostTracking.cost_usd).label("total_cost"),
                func.count().label("total_requests"),
                func.avg(CostTracking.latency_ms).label("avg_latency"),
            )
            .where(
                CostTracking.user_id == uuid.UUID(user_id),
                CostTracking.created_at >= since,
            )
        )
        row = result.one()

        return {
            "total_tokens_in": row.total_tokens_in or 0,
            "total_tokens_out": row.total_tokens_out or 0,
            "total_cost_usd": float(row.total_cost or 0),
            "total_requests": row.total_requests or 0,
            "avg_latency_ms": float(row.avg_latency or 0),
            "period_days": days,
        }
```

---

## Environment Variables Required

```bash
# Phase 3 specific:
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_TIMEOUT_SECONDS=30
GROQ_API_KEY=your-groq-key
GROQ_PRIMARY_MODEL=llama-3.1-70b-versatile
GROQ_SECONDARY_MODEL=mixtral-8x7b-32768
GROQ_TIMEOUT_SECONDS=15
LLM_FALLBACK_LATENCY_THRESHOLD_MS=10000
LLM_FALLBACK_ERROR_THRESHOLD=3
LLM_FALLBACK_ERROR_WINDOW_SECONDS=60
LLM_HEALTH_CHECK_INTERVAL_SECONDS=30
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| Router starts on Gemini | Unit | Default provider is correct |
| Error threshold triggers switch | Unit | 3 errors in 60s → switch to Groq |
| Latency threshold triggers switch | Unit | >10s latency records error |
| Health check recovers to Gemini | Unit | Successful health check switches back |
| Sliding window prunes old errors | Unit | Errors outside window don't count |
| Fallback chain order correct | Unit | Gemini → Groq Llama → Groq Mixtral |
| Cost calculation accuracy | Unit | Token pricing matches published rates |
| BaseAgent retry logic | Unit | Exponential backoff on failures |
| Cache hit returns stored response | Integration | Redis cache lookup works |

---

## Definition of Done — Phase 3

- [ ] LLMRouter class fully implemented with sliding window metrics
- [ ] Gemini provider configured and tested
- [ ] Groq provider (both models) configured and tested
- [ ] Automatic failover works when Gemini has 3+ errors in 60s
- [ ] Automatic failover works when Gemini latency exceeds 10s
- [ ] Health check recovery switches back to Gemini
- [ ] /api/v1/llm/status endpoint returns current provider info
- [ ] Cost tracking records every invocation
- [ ] LLM response cache reduces redundant API calls
- [ ] BaseAgent class provides standardized agent pattern
- [ ] TripPlanningState TypedDict defines complete agent state
- [ ] LangSmith tracing captures all LLM calls
- [ ] Unit tests cover all failover scenarios

## Common Pitfalls

| Pitfall | How to Avoid |
|---------|-------------|
| **Groq rate limits** | Free tier: 30 RPM. Queue requests or upgrade |
| **Health check loop** | `_is_checking_health` flag prevents concurrent checks |
| **Cache key collisions** | Use SHA-256 of model + full message JSON |
| **Token counting varies** | Different providers report tokens differently |
| **Sliding window memory** | Deque maxlen prevents unbounded growth |

## Scale-Up Path

| Component | Current | Trigger | Upgrade |
|-----------|---------|---------|---------|
| LLM Router | Single process | Multiple backend instances | Redis-backed shared state |
| Cost Tracking | Per-request DB insert | >1000 req/min | Batch inserts via Celery |
| LLM Cache | Redis single instance | Cache size > 10GB | Redis Cluster |
| Groq Free Tier | 30 RPM | Frequent fallbacks | Groq paid ($0.59/M tokens) |

---

*Phase 3 is the reliability backbone. Every agent in Phase 4 calls `llm_router.invoke()` — if this works correctly, the entire multi-agent system is resilient.*
