"""
Voice Pipeline orchestrator — connects VAD, STT, and TTS.

Manages the full lifecycle of a single voice interaction:
1. Receive audio frames from the WebSocket or LiveKit room
2. Detect speech boundaries with Silero VAD
3. Transcribe completed utterances with Whisper STT
4. Pass transcript through the agent pipeline callback
5. Stream TTS audio back to the user

Full-duplex interrupt handling:
  If the user speaks while TTS is playing, the _cancel_tts event is set,
  the TTS generator stops at the next chunk boundary, and the new speech
  takes priority immediately.

Pipeline latency target: < 800ms from speech end to first audio byte.
"""

from __future__ import annotations

import asyncio
import io
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

import structlog

from parikrama.voice.stt import WhisperSTT
from parikrama.voice.tts import BaseTTSEngine, create_tts_engine
from parikrama.voice.vad import SileroVAD

logger = structlog.get_logger(__name__)

# Minimum audio buffer size before we attempt transcription (~100ms at 16kHz/16-bit)
MIN_AUDIO_BYTES = 3200


class VoicePipeline:
    """
    Full-duplex voice interaction pipeline.

    Callbacks:
        on_transcript: async (text: str) -> str
            Called when user speech is transcribed.
            Should invoke the agent pipeline and return the response text.

        on_audio_chunk: async (pcm_bytes: bytes) -> None
            Called with each TTS audio chunk to stream back to user.
    """

    def __init__(
        self,
        on_transcript: Callable[[str], Coroutine[Any, Any, str]],
        on_audio_chunk: Callable[[bytes], Coroutine[Any, Any, None]],
        vad: SileroVAD | None = None,
        stt: WhisperSTT | None = None,
        tts: BaseTTSEngine | None = None,
    ) -> None:
        self.vad = vad or SileroVAD()
        self.stt = stt or WhisperSTT()
        self.tts = tts or create_tts_engine()

        self._on_transcript = on_transcript
        self._on_audio_chunk = on_audio_chunk

        # state machine
        self._is_speaking = False  # user is currently speaking
        self._is_responding = False  # TTS is currently playing
        self._audio_buffer = io.BytesIO()
        self._cancel_tts = asyncio.Event()

    async def process_audio_frame(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
    ) -> None:
        """
        Process a single audio frame from LiveKit or the WebSocket bridge.

        Called for every ~20ms audio frame. VAD determines if the user is speaking.
        When speech ends, transcription and response generation are kicked off.

        Args:
            audio_data: Raw 16-bit signed mono PCM bytes.
            sample_rate: Must be 16000 for Silero VAD.
        """
        import numpy as np

        # convert raw PCM bytes → float32 numpy array for VAD
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        is_speech = self.vad.is_speech(audio_array, sample_rate)

        if is_speech and not self._is_speaking:
            # ── speech just started ─────────────────────────────────────────
            self._is_speaking = True
            self._audio_buffer = io.BytesIO()

            # user interrupting ongoing TTS response
            if self._is_responding:
                self._cancel_tts.set()
                self._is_responding = False
                logger.info("tts_interrupted_by_user")

        if is_speech:
            self._audio_buffer.write(audio_data)

        if not is_speech and self._is_speaking:
            # ── speech just ended ───────────────────────────────────────────
            self._is_speaking = False
            audio_bytes = self._audio_buffer.getvalue()

            if len(audio_bytes) > MIN_AUDIO_BYTES:
                # fire and forget — store task to prevent GC
                self._active_tasks: set = getattr(self, "_active_tasks", set())
                task = asyncio.create_task(
                    self._handle_speech_end(audio_bytes, sample_rate),
                    name="voice_handle_speech",
                )
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)

    async def _handle_speech_end(self, audio_bytes: bytes, sample_rate: int) -> None:
        """
        Full pipeline: transcribe → agent → TTS → stream audio.

        Latency breakdown (approx, CPU, base model):
          STT (Whisper base): 300-600ms
          Agent pipeline:     500-2000ms (LLM dependent)
          TTS first chunk:    200-300ms (Coqui, first sentence)
        """
        pipeline_start = time.perf_counter()

        # Step 1: STT
        try:
            transcript = await self.stt.transcribe(audio_bytes, sample_rate)
        except Exception as exc:
            logger.error("stt_failed", error=str(exc))
            return

        if not transcript or not transcript.strip():
            logger.debug("stt_empty_transcript")
            return

        stt_ms = (time.perf_counter() - pipeline_start) * 1000
        logger.info("voice_transcript", text=transcript[:100], stt_ms=round(stt_ms, 1))

        # Step 2: Agent pipeline
        try:
            response_text = await self._on_transcript(transcript)
        except Exception as exc:
            logger.error("agent_pipeline_failed", error=str(exc))
            return

        if not response_text or not response_text.strip():
            return

        agent_ms = (time.perf_counter() - pipeline_start) * 1000
        logger.info("voice_response_ready", agent_ms=round(agent_ms, 1))

        # Step 3: TTS streaming
        self._is_responding = True
        self._cancel_tts.clear()

        await self._stream_tts(response_text)

        total_ms = (time.perf_counter() - pipeline_start) * 1000
        logger.info(
            "voice_pipeline_complete",
            stt_ms=round(stt_ms, 1),
            agent_ms=round(agent_ms, 1),
            total_ms=round(total_ms, 1),
        )

    async def _stream_tts(self, text: str) -> None:
        """
        Stream TTS audio chunks to the caller via the on_audio_chunk callback.
        Stops immediately if _cancel_tts is set (user interrupted).
        """
        try:
            async for audio_chunk in self.tts.synthesize_stream(text):
                if self._cancel_tts.is_set():
                    logger.info("tts_stream_cancelled")
                    break
                try:
                    await self._on_audio_chunk(audio_chunk)
                except Exception as exc:
                    logger.warning("audio_chunk_send_failed", error=str(exc))
                    break
        except Exception as exc:
            logger.error("tts_stream_error", error=str(exc))
        finally:
            self._is_responding = False

    def reset(self) -> None:
        """Reset pipeline state. Call between sessions."""
        self._is_speaking = False
        self._is_responding = False
        self._audio_buffer = io.BytesIO()
        self._cancel_tts.clear()
        self.vad.reset()
        logger.debug("voice_pipeline_reset")
