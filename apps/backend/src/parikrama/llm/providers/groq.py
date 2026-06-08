"""
Groq (Llama-3.1) async provider — fallback LLM for PariKrama.

Uses the official groq SDK with async support.
Primary model: llama-3.1-70b-versatile
Secondary: mixtral-8x7b-32768 (if primary fails)
"""

from __future__ import annotations

import time

import structlog

from parikrama.llm.schemas import LLMProvider, LLMResponse

logger = structlog.get_logger(__name__)


class GroqProvider:
    """Async Groq/Llama-3.1 provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.1-70b-versatile",
        timeout_seconds: int = 15,
    ) -> None:
        if not api_key:
            raise ValueError("GROQ_API_KEY is required for GroqProvider")

        from groq import AsyncGroq  # lazy import

        self._client = AsyncGroq(api_key=api_key, timeout=timeout_seconds)
        self._model_name = model
        self._timeout = timeout_seconds
        self.is_configured = True

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate text from Groq/Llama-3.1.

        Args:
            prompt: User message.
            system: System instruction (sent as system message in chat format).
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content, latency, and token counts.

        Raises:
            groq.APITimeoutError: On timeout.
            groq.APIError: On API error.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        start = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        latency = int((time.monotonic() - start) * 1000)

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage

        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        logger.info(
            "groq_generate",
            model=self._model_name,
            latency_ms=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=choice.finish_reason,
        )

        return LLMResponse(
            content=content,
            provider=LLMProvider.GROQ,
            model=self._model_name,
            latency_ms=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=choice.finish_reason or "stop",
        )
