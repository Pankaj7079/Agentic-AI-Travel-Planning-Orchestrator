"""
LLM Router — intelligent request routing with automatic fallback and circuit breaker.

Routing strategy:
  1. Primary: Gemini 2.5 Flash Lite (best quality, low cost)
  2. Fallback: Groq/Llama-3.1-70b (fast, free tier available)

Fallback triggers:
  - Response latency > LLM_FALLBACK_LATENCY_THRESHOLD_MS (default 10s)
  - >= LLM_FALLBACK_ERROR_THRESHOLD errors in LLM_FALLBACK_ERROR_WINDOW_SECONDS (default 3 in 60s)

Circuit breaker:
  - CLOSED → OPEN: After threshold errors
  - OPEN → HALF_OPEN: After LLM_HEALTH_CHECK_INTERVAL_SECONDS (30s)
  - HALF_OPEN → CLOSED: On first successful probe
  - HALF_OPEN → OPEN: On probe failure

If both providers are unavailable (no API keys), raises LLMUnavailableError.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from parikrama.llm.schemas import CircuitState, LLMProvider, LLMResponse, ProviderHealth

if TYPE_CHECKING:
    from parikrama.llm.providers.gemini import GeminiProvider
    from parikrama.llm.providers.groq import GroqProvider

logger = structlog.get_logger(__name__)


class LLMUnavailableError(RuntimeError):
    """Raised when all configured LLM providers fail."""


class LLMRouter:
    """Routes LLM requests between Gemini (primary) and Groq (fallback).

    Implements a sliding-window circuit breaker. Thread-safe for async use
    (uses asyncio.Lock for state mutations).

    Usage::

        router = LLMRouter.from_settings(settings)
        response = await router.generate("Plan a 5-day trip to Manali")
    """

    def __init__(
        self,
        gemini: GeminiProvider | None,
        groq: GroqProvider | None,
        latency_threshold_ms: int = 10_000,
        error_threshold: int = 3,
        error_window_seconds: int = 60,
        recovery_interval_seconds: int = 30,
    ) -> None:
        if not gemini and not groq:
            raise LLMUnavailableError(
                "At least one LLM provider must be configured. "
                "Set GEMINI_API_KEY or GROQ_API_KEY in .env"
            )

        self._gemini = gemini
        self._groq = groq
        self._latency_threshold_ms = latency_threshold_ms
        self._error_threshold = error_threshold
        self._error_window_seconds = error_window_seconds
        self._recovery_interval_seconds = recovery_interval_seconds

        self._gemini_health = ProviderHealth(provider=LLMProvider.GEMINI)
        self._groq_health = ProviderHealth(provider=LLMProvider.GROQ)

        self._gemini_open_since: float | None = None
        self._lock = asyncio.Lock()

    # ── Public interface ────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        force_provider: LLMProvider | None = None,
    ) -> LLMResponse:
        """Generate text using the best available provider.

        Args:
            prompt: User message / query text.
            system: Optional system prompt injected before the user message.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens in the response (default 4096).
            force_provider: Skip routing logic and use this provider directly.

        Returns:
            LLMResponse from whichever provider handled the request.

        Raises:
            LLMUnavailableError: When all available providers fail.
        """
        if force_provider == LLMProvider.GROQ:
            return await self._call_groq(prompt, system, temperature, max_tokens)
        if force_provider == LLMProvider.GEMINI:
            return await self._call_gemini_or_raise(prompt, system, temperature)

        # Normal routing: try Gemini → fallback to Groq
        if self._gemini and self._should_use_gemini():
            try:
                return await self._call_gemini_with_timeout(prompt, system, temperature)
            except Exception as exc:
                logger.warning("gemini_failed_routing_to_groq", error=str(exc)[:120])
                await self._record_gemini_error()

        if self._groq:
            return await self._call_groq(prompt, system, temperature, max_tokens)

        raise LLMUnavailableError(
            "Gemini circuit is open and no Groq fallback is configured. Add GROQ_API_KEY to .env"
        )

    def health_status(self) -> dict:
        """Return current router health for the /agents/health endpoint."""
        g = self._gemini_health
        q = self._groq_health
        return {
            "gemini": {
                "configured": self._gemini is not None,
                "circuit_state": g.state,
                "consecutive_errors": g.consecutive_errors,
                "last_latency_ms": g.last_latency_ms,
                "total_requests": g.total_requests,
                "total_errors": g.total_errors,
            },
            "groq": {
                "configured": self._groq is not None,
                "circuit_state": q.state,
                "consecutive_errors": q.consecutive_errors,
                "last_latency_ms": q.last_latency_ms,
                "total_requests": q.total_requests,
                "total_errors": q.total_errors,
            },
            "active_provider": self._active_provider_name(),
        }

    # ── Circuit breaker logic ───────────────────────────────────────────────

    def _should_use_gemini(self) -> bool:
        """Return True if Gemini's circuit is CLOSED or ready for a probe."""
        h = self._gemini_health
        if h.state == CircuitState.CLOSED:
            return True
        if h.state == CircuitState.OPEN:
            if self._gemini_open_since is not None:
                elapsed = time.monotonic() - self._gemini_open_since
                if elapsed >= self._recovery_interval_seconds:
                    h.state = CircuitState.HALF_OPEN
                    logger.info("gemini_circuit_half_open", elapsed_s=round(elapsed, 1))
                    return True  # allow a probe
            return False
        # HALF_OPEN — allow one probe
        return True

    async def _record_gemini_error(self) -> None:
        async with self._lock:
            h = self._gemini_health
            now = time.monotonic()
            h.total_errors += 1
            h.consecutive_errors += 1
            h.error_timestamps = [
                t for t in h.error_timestamps if now - t < self._error_window_seconds
            ]
            h.error_timestamps.append(now)

            if (
                len(h.error_timestamps) >= self._error_threshold
                or h.state == CircuitState.HALF_OPEN
            ):
                if h.state != CircuitState.OPEN:
                    logger.warning(
                        "gemini_circuit_opened",
                        errors_in_window=len(h.error_timestamps),
                    )
                h.state = CircuitState.OPEN
                self._gemini_open_since = now

    async def _record_gemini_success(self, latency_ms: int) -> None:
        async with self._lock:
            h = self._gemini_health
            h.total_requests += 1
            h.last_latency_ms = latency_ms
            h.consecutive_errors = 0
            h.error_timestamps.clear()
            if h.state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
                logger.info("gemini_circuit_closed")
                h.state = CircuitState.CLOSED
                self._gemini_open_since = None

    async def _record_groq_call(self, latency_ms: int, *, error: bool = False) -> None:
        async with self._lock:
            h = self._groq_health
            h.total_requests += 1
            h.last_latency_ms = latency_ms
            if error:
                h.total_errors += 1
                h.consecutive_errors += 1
            else:
                h.consecutive_errors = 0

    # ── Provider call helpers ───────────────────────────────────────────────

    async def _call_gemini_with_timeout(
        self, prompt: str, system: str, temperature: float
    ) -> LLMResponse:
        """Call Gemini; raise if latency exceeds threshold."""
        assert self._gemini is not None
        response = await self._gemini.generate(prompt, system, temperature)
        if response.latency_ms > self._latency_threshold_ms:
            await self._record_gemini_error()
            raise TimeoutError(
                f"Gemini latency {response.latency_ms}ms exceeds "
                f"threshold {self._latency_threshold_ms}ms"
            )
        await self._record_gemini_success(response.latency_ms)
        return response

    async def _call_gemini_or_raise(
        self, prompt: str, system: str, temperature: float
    ) -> LLMResponse:
        if not self._gemini:
            raise LLMUnavailableError("Gemini is not configured")
        return await self._gemini.generate(prompt, system, temperature)

    async def _call_groq(
        self, prompt: str, system: str, temperature: float, max_tokens: int = 4096
    ) -> LLMResponse:
        if not self._groq:
            raise LLMUnavailableError("Groq is not configured")
        start = time.monotonic()
        try:
            response = await self._groq.generate(prompt, system, temperature, max_tokens)
            await self._record_groq_call(int((time.monotonic() - start) * 1000))
            return response
        except Exception:
            await self._record_groq_call(int((time.monotonic() - start) * 1000), error=True)
            raise

    def _active_provider_name(self) -> str:
        if not self._gemini:
            return LLMProvider.GROQ
        if self._gemini_health.state == CircuitState.CLOSED:
            return LLMProvider.GEMINI
        return LLMProvider.GROQ if self._groq else "none"

    # ── Factory ─────────────────────────────────────────────────────────────

    @classmethod
    def from_settings(cls, settings) -> LLMRouter:  # type: ignore[no-untyped-def]
        """Build a router from app Settings. Gracefully handles missing API keys."""
        from parikrama.llm.providers.gemini import GeminiProvider
        from parikrama.llm.providers.groq import GroqProvider

        gemini = None
        if settings.GEMINI_API_KEY:
            try:
                gemini = GeminiProvider(
                    api_key=settings.GEMINI_API_KEY,
                    model=settings.GEMINI_MODEL,
                    timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
                )
                logger.info("gemini_provider_configured", model=settings.GEMINI_MODEL)
            except Exception as exc:
                logger.warning("gemini_provider_failed", error=str(exc))

        groq = None
        if settings.GROQ_API_KEY:
            try:
                groq = GroqProvider(
                    api_key=settings.GROQ_API_KEY,
                    model=settings.GROQ_PRIMARY_MODEL,
                    timeout_seconds=settings.GROQ_TIMEOUT_SECONDS,
                )
                logger.info("groq_provider_configured", model=settings.GROQ_PRIMARY_MODEL)
            except Exception as exc:
                logger.warning("groq_provider_failed", error=str(exc))

        if not gemini and not groq:
            logger.error(
                "no_llm_provider_configured",
                hint="Set GEMINI_API_KEY or GROQ_API_KEY in .env",
            )
            raise LLMUnavailableError(
                "No LLM provider is configured. Add GEMINI_API_KEY or GROQ_API_KEY to .env"
            )

        return cls(
            gemini=gemini,
            groq=groq,
            latency_threshold_ms=settings.LLM_FALLBACK_LATENCY_THRESHOLD_MS,
            error_threshold=settings.LLM_FALLBACK_ERROR_THRESHOLD,
            error_window_seconds=settings.LLM_FALLBACK_ERROR_WINDOW_SECONDS,
            recovery_interval_seconds=settings.LLM_HEALTH_CHECK_INTERVAL_SECONDS,
        )
