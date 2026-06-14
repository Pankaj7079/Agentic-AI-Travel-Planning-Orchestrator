"""
Whisper-based Speech-to-Text.

Uses OpenAI's Whisper model running locally (no API key required).
Supports English and Hindi — critical for Indian users.

The model is lazy-loaded on first transcription call.
Whisper is CPU-bound, so transcription runs in a thread pool executor
to avoid blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
import wave

import structlog

from parikrama.config import settings

logger = structlog.get_logger(__name__)


class WhisperSTT:
    """
    Local Whisper model for speech-to-text.

    Model sizes and their trade-offs:
        tiny   — fastest (~32x realtime), lower accuracy
        base   — good balance (~16x realtime), good Hindi/English support  ← default
        small  — better accuracy (~6x realtime)
        medium — best accuracy, slow on CPU (~2x realtime)
    """

    def __init__(self, model_size: str | None = None) -> None:
        self._model_size = model_size or settings.WHISPER_MODEL_SIZE
        self._model = None

    @property
    def model(self):
        """Lazy-load the Whisper model (2-5s on first call, cached after)."""
        if self._model is None:
            import whisper  # lazy import — ~500ms import time

            logger.info("loading_whisper_model", size=self._model_size)
            self._model = whisper.load_model(self._model_size)
            logger.info("whisper_model_loaded", size=self._model_size)
        return self._model

    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """
        Transcribe raw PCM audio bytes to text.

        Runs Whisper in a thread pool executor (CPU-bound, non-blocking).

        Args:
            audio_bytes: Raw PCM audio (16-bit signed, mono).
            sample_rate: Audio sample rate (default 16kHz for LiveKit).
            language: Force language ('en', 'hi') or None for auto-detect.

        Returns:
            Transcribed text string (empty string if nothing detected).
        """
        if not audio_bytes:
            return ""

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._transcribe_sync, audio_bytes, sample_rate, language
        )

    def _transcribe_sync(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        language: str | None,
    ) -> str:
        """Synchronous transcription — runs in thread pool."""
        # Write raw PCM bytes into a proper WAV container
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)  # mono
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

        try:
            result = self.model.transcribe(
                wav_path,
                language=language,  # None = auto-detect
                task="transcribe",
                fp16=False,  # use fp32 on CPU
                verbose=False,
            )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(wav_path)

        text = result.get("text", "").strip()
        detected_lang = result.get("language", "unknown")

        logger.info(
            "whisper_transcribed",
            text_preview=text[:80],
            detected_language=detected_lang,
            audio_bytes=len(audio_bytes),
        )
        return text
