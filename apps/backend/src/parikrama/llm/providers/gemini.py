"""
Gemini 2.5 Flash Lite async provider.

Wraps google-generativeai with:
- Consistent LLMResponse return type
- Timeout enforcement via asyncio.wait_for
- Token count extraction from response metadata
- Graceful degradation when API key is absent (raises immediately)
"""

from __future__ import annotations

import asyncio
import time
import warnings

import structlog

from parikrama.llm.schemas import LLMProvider, LLMResponse

logger = structlog.get_logger(__name__)


class GeminiProvider:
    """Async Gemini 2.5 Flash Lite provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-lite-preview-06-17",
        timeout_seconds: int = 30,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiProvider")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import google.generativeai as genai  # lazy import — heavy

        genai.configure(api_key=api_key)
        self._model_name = model
        self._timeout = timeout_seconds
        self._client = genai.GenerativeModel(model)
        self._genai = genai
        self.is_configured = True

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate text from Gemini. Raises on timeout or API error.

        Args:
            prompt: User message / query.
            system: Optional system-level instruction prepended to prompt.
            temperature: Sampling temperature (0.0 = deterministic).

        Returns:
            LLMResponse with content, latency, and token counts.

        Raises:
            asyncio.TimeoutError: If response takes longer than timeout_seconds.
            Exception: Propagated from the Gemini API on error.
        """
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        config = self._genai.GenerationConfig(temperature=temperature)

        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._client.generate_content(full_prompt, generation_config=config),
                ),
                timeout=self._timeout,
            )
        except TimeoutError:
            latency = int((time.monotonic() - start) * 1000)
            logger.warning(
                "gemini_timeout",
                latency_ms=latency,
                timeout_s=self._timeout,
            )
            raise

        latency = int((time.monotonic() - start) * 1000)
        content = response.text or ""

        # Extract token counts from usage_metadata if available
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0

        logger.info(
            "gemini_generate",
            latency_ms=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            content_len=len(content),
        )

        return LLMResponse(
            content=content,
            provider=LLMProvider.GEMINI,
            model=self._model_name,
            latency_ms=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
