"""
Shared LLM types used by providers, router, and agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class LLMProvider(StrEnum):
    """Available LLM providers."""

    GEMINI = "gemini"
    GROQ = "groq"


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # healthy — requests flow normally
    OPEN = "open"  # unhealthy — requests skip to fallback
    HALF_OPEN = "half_open"  # recovery probe in progress


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str
    provider: LLMProvider
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ProviderHealth:
    """Real-time health snapshot for one provider."""

    provider: LLMProvider
    state: CircuitState = CircuitState.CLOSED
    consecutive_errors: int = 0
    last_latency_ms: int = 0
    total_requests: int = 0
    total_errors: int = 0
    error_timestamps: list[float] = field(default_factory=list)
