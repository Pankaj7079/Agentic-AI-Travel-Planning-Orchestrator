"""
Tests for the LLM Router circuit breaker and fallback logic.

All tests mock the actual LLM providers — no API keys needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from parikrama.llm.router import LLMRouter, LLMUnavailableError
from parikrama.llm.schemas import CircuitState, LLMProvider, LLMResponse


def _make_response(
    provider: LLMProvider = LLMProvider.GEMINI, latency_ms: int = 500
) -> LLMResponse:
    return LLMResponse(
        content="Test response content",
        provider=provider,
        model="test-model",
        latency_ms=latency_ms,
        input_tokens=100,
        output_tokens=50,
    )


def _make_router(
    has_gemini: bool = True,
    has_groq: bool = True,
    latency_threshold_ms: int = 10_000,
    error_threshold: int = 3,
    error_window_seconds: int = 60,
    recovery_interval_seconds: int = 30,
) -> tuple[LLMRouter, MagicMock | None, MagicMock | None]:
    gemini = MagicMock() if has_gemini else None
    groq = MagicMock() if has_groq else None
    if gemini:
        gemini.generate = AsyncMock(return_value=_make_response(LLMProvider.GEMINI))
    if groq:
        groq.generate = AsyncMock(return_value=_make_response(LLMProvider.GROQ))

    router = LLMRouter(
        gemini=gemini,
        groq=groq,
        latency_threshold_ms=latency_threshold_ms,
        error_threshold=error_threshold,
        error_window_seconds=error_window_seconds,
        recovery_interval_seconds=recovery_interval_seconds,
    )
    return router, gemini, groq


# ── Construction ───────────────────────────────────────────────────────────────


class TestLLMRouterConstruction:
    def test_raises_if_no_providers(self):
        with pytest.raises(LLMUnavailableError, match="At least one"):
            LLMRouter(gemini=None, groq=None)

    def test_ok_with_only_gemini(self):
        gemini = MagicMock()
        router = LLMRouter(gemini=gemini, groq=None)
        assert router._gemini is gemini

    def test_ok_with_only_groq(self):
        groq = MagicMock()
        router = LLMRouter(gemini=None, groq=groq)
        assert router._groq is groq


# ── Normal routing ─────────────────────────────────────────────────────────────


class TestLLMRouterNormalRouting:
    @pytest.mark.asyncio
    async def test_uses_gemini_by_default(self):
        router, gemini, groq = _make_router()
        response = await router.generate("test prompt")
        assert response.provider == LLMProvider.GEMINI
        gemini.generate.assert_called_once()
        groq.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_groq_bypasses_gemini(self):
        router, gemini, _ = _make_router()
        response = await router.generate("test", force_provider=LLMProvider.GROQ)
        assert response.provider == LLMProvider.GROQ
        gemini.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_groq_on_gemini_error(self):
        router, gemini, _groq = _make_router(error_threshold=1)
        gemini.generate = AsyncMock(side_effect=Exception("API Error"))
        response = await router.generate("test prompt")
        assert response.provider == LLMProvider.GROQ

    @pytest.mark.asyncio
    async def test_only_groq_routes_to_groq(self):
        router, _, _groq = _make_router(has_gemini=False)
        response = await router.generate("test prompt")
        assert response.provider == LLMProvider.GROQ


# ── Circuit breaker ────────────────────────────────────────────────────────────


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_error_threshold(self):
        router, gemini, _groq = _make_router(error_threshold=2, error_window_seconds=60)
        gemini.generate = AsyncMock(side_effect=Exception("error"))

        # Two failures should open the circuit
        for _ in range(2):
            await router.generate("test")

        assert router._gemini_health.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_routes_to_groq_without_calling_gemini(self):
        router, gemini, _groq = _make_router(error_threshold=1)
        gemini.generate = AsyncMock(side_effect=Exception("error"))

        # Trigger circuit open
        await router.generate("first call")
        assert router._gemini_health.state == CircuitState.OPEN

        # Second call should skip Gemini entirely
        gemini.generate.reset_mock()
        response = await router.generate("second call")
        assert response.provider == LLMProvider.GROQ
        gemini.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open_after_recovery_interval(self):
        router, gemini, _groq = _make_router(error_threshold=1, recovery_interval_seconds=0)
        gemini.generate = AsyncMock(side_effect=Exception("error"))

        await router.generate("trigger open")
        assert router._gemini_health.state == CircuitState.OPEN

        # Fake that recovery interval has passed
        import time

        router._gemini_open_since = time.monotonic() - 1  # 1s ago

        # Reset gemini to succeed now
        gemini.generate = AsyncMock(return_value=_make_response(LLMProvider.GEMINI))
        response = await router.generate("probe call")
        assert router._gemini_health.state == CircuitState.CLOSED
        assert response.provider == LLMProvider.GEMINI

    def test_health_status_returns_dict(self):
        router, _, _ = _make_router()
        status = router.health_status()
        assert "gemini" in status
        assert "groq" in status
        assert "active_provider" in status
        assert status["gemini"]["configured"] is True
        assert status["groq"]["configured"] is True
