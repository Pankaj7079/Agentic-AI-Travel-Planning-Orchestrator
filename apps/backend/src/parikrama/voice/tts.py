"""
TTS Engine — generates speech from text.

Supports two backends, selected via TTS_ENGINE env var:
  - coqui     : Open-source, runs locally, no API key required (default)
  - elevenlabs: Premium quality, requires ELEVENLABS_API_KEY

Both backends implement the same interface: synthesize_stream() yields
raw PCM audio chunks (16-bit signed, mono) for low-latency streaming.

Text is split at sentence boundaries so the first sentence is returned
quickly while the rest is still being synthesized.
"""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import structlog

from parikrama.config import settings

logger = structlog.get_logger(__name__)


class BaseTTSEngine(ABC):
    """Abstract TTS engine interface."""

    @abstractmethod
    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncGenerator[bytes, None]:
        """Yield raw 16-bit PCM audio chunks for the given text."""
        return
        yield  # pragma: no cover

    def split_sentences(self, text: str) -> list[str]:
        """
        Split text at sentence boundaries for streaming.

        Handles English and Hindi sentence endings (। is Hindi danda).
        """
        sentences = re.split(r"(?<=[.!?।])\s+", text)
        return [s.strip() for s in sentences if s.strip()]


class CoquiTTSEngine(BaseTTSEngine):
    """
    Coqui TTS — open-source, runs entirely locally.

    Model: tts_models/en/ljspeech/vits (fast, good quality English)
    First call downloads the model (~70MB), subsequent calls use cache.
    Synthesis runs in a thread pool executor (CPU-bound).
    """

    def __init__(self) -> None:
        self._engine = None

    def _load_engine(self) -> None:
        """Load Coqui TTS model (lazy, called once)."""
        from TTS.api import TTS  # type: ignore[import]

        logger.info("loading_coqui_tts")
        self._engine = TTS("tts_models/en/ljspeech/vits", progress_bar=False)
        logger.info("coqui_tts_loaded")

    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize text → stream PCM bytes, one sentence at a time."""
        loop = asyncio.get_event_loop()

        # ensure model is loaded
        if self._engine is None:
            await loop.run_in_executor(None, self._load_engine)

        for sentence in self.split_sentences(text):
            chunk = await loop.run_in_executor(None, self._synthesize_sentence, sentence)
            if chunk:
                yield chunk

    def _synthesize_sentence(self, sentence: str) -> bytes | None:
        """Synthesize one sentence synchronously (runs in thread pool)."""
        try:
            import numpy as np

            wav = self._engine.tts(sentence)  # returns list of floats
            audio_int16 = (np.array(wav) * 32767).astype(np.int16)
            return audio_int16.tobytes()
        except Exception as exc:
            logger.error("coqui_tts_synthesis_failed", error=str(exc), sentence=sentence[:60])
            return None


class ElevenLabsTTSEngine(BaseTTSEngine):
    """
    ElevenLabs TTS — high-quality cloud voice synthesis.

    Requires ELEVENLABS_API_KEY. Falls back to CoquiTTSEngine when key is absent.
    Streams audio directly from the ElevenLabs streaming API.
    """

    def __init__(self) -> None:
        self._client = None
        self._fallback = CoquiTTSEngine()

    def _get_client(self):
        if self._client is None:
            from elevenlabs.client import ElevenLabs  # type: ignore[import]

            self._client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
        return self._client

    async def synthesize_stream(
        self, text: str, language: str = "en"
    ) -> AsyncGenerator[bytes, None]:
        """Stream audio from ElevenLabs. Falls back to Coqui if no API key."""
        if not settings.ELEVENLABS_API_KEY:
            logger.warning("elevenlabs_no_api_key_falling_back_to_coqui")
            async for chunk in self._fallback.synthesize_stream(text, language):
                yield chunk
            return

        loop = asyncio.get_event_loop()
        try:
            client = self._get_client()
            chunks = await loop.run_in_executor(
                None,
                lambda: list(
                    client.generate(
                        text=text,
                        voice=settings.ELEVENLABS_VOICE_ID,
                        model="eleven_turbo_v2",
                        stream=True,
                    )
                ),
            )
            for chunk in chunks:
                if chunk:
                    yield chunk
        except Exception as exc:
            logger.error("elevenlabs_tts_failed", error=str(exc))
            async for chunk in self._fallback.synthesize_stream(text, language):
                yield chunk


def create_tts_engine() -> BaseTTSEngine:
    """
    Factory — return the configured TTS engine.

    Uses TTS_ENGINE env var:
        coqui       → CoquiTTSEngine (default, open source)
        elevenlabs  → ElevenLabsTTSEngine (requires API key)
    """
    engine_name = settings.TTS_ENGINE.lower()
    if engine_name == "elevenlabs":
        logger.info("tts_engine_selected", engine="elevenlabs")
        return ElevenLabsTTSEngine()
    logger.info("tts_engine_selected", engine="coqui")
    return CoquiTTSEngine()
