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
        max_tokens: int = 4096,
        max_retries: int = 2,
    ) -> LLMResponse:
        """Generate text from Groq/Llama-3.1.

        Args:
            prompt: User message.
            system: System instruction (sent as system message in chat format).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response (default 4096).
            max_retries: Max retries on 429 rate limit (default 2).

        Returns:
            LLMResponse with content, latency, and token counts.

        Raises:
            groq.APITimeoutError: On timeout.
            groq.APIError: On API error (after retries exhausted).
        """
        import asyncio

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            start = time.monotonic()
            try:
                response = await self._client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
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
            except Exception as exc:
                last_error = exc
                is_rate_limit = "429" in str(exc) or "rate" in str(exc).lower()
                if is_rate_limit and attempt < max_retries:
                    wait_s = 15 * (attempt + 1)  # 15s, 30s
                    logger.warning(
                        "groq_rate_limited_retrying",
                        attempt=attempt + 1,
                        wait_s=wait_s,
                        error=str(exc)[:120],
                    )
                    await asyncio.sleep(wait_s)
                    continue
                raise

        raise last_error  # type: ignore[misc]
