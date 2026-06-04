# Phase 6: Voice Pipeline (Full Duplex)

## Overview

Phase 6 adds the **voice interface** — users can speak their travel requests and hear the agent respond, just like talking to a travel advisor. This is full-duplex: the user can interrupt the agent mid-sentence, and the agent stops to listen. The entire pipeline targets **<800ms latency** from user speech to agent response start.

### The Voice Pipeline
```
User Speaks → [Microphone] → [WebRTC/LiveKit] → [VAD/Silero]
                                                      ↓
                                              (speech detected)
                                                      ↓
                                            [STT/Whisper] → Text
                                                      ↓
                                            [Agent Pipeline] → Response text
                                                      ↓
                                            [TTS/Coqui] → Audio stream
                                                      ↓
                                    [WebRTC/LiveKit] → [Speaker]
```

---

## Architecture Decisions

### Decision 1: LiveKit vs Direct WebSocket Audio
| Approach | Audio Quality | NAT Traversal | Interrupt Handling |
|----------|-------------|-------------|-------------------|
| **LiveKit (chosen)** | Excellent (Opus codec) | Built-in TURN/STUN | Native track mute/unmute |
| Raw WebSocket + PCM | Variable | Manual | Complex |
| Daily.co | Excellent | Managed | Built-in |

**Why LiveKit:** Open-source, self-hosted, handles all WebRTC complexity (ICE negotiation, codec selection, bandwidth adaptation). The LiveKit Agents SDK provides native Python integration for our voice pipeline.

### Decision 2: Whisper Model Size
| Model | Speed (RTX 3060) | Speed (CPU) | Accuracy | VRAM |
|-------|-----------------|-------------|----------|------|
| tiny | 32x realtime | 10x | Fair | 1GB |
| **base (chosen)** | 16x realtime | 5x | Good | 1GB |
| small | 6x realtime | 2x | Great | 2GB |
| medium | 2x realtime | 0.5x | Excellent | 5GB |

**Why base:** Best balance of speed and accuracy for Indian English + Hindi. The base model handles accented English well and processes a 10-second audio clip in ~600ms on CPU. For production with GPU, use small/medium.

### Decision 3: TTS Choice
| Engine | Quality | Languages | Latency | Cost |
|--------|---------|-----------|---------|------|
| **Coqui TTS (chosen)** | Good | English, Hindi | ~200ms | Free (open source) |
| ElevenLabs | Excellent | Many | ~300ms | Free tier: 10K chars/month |
| Google Cloud TTS | Excellent | Hindi native | ~150ms | $16/M chars |

**Why Coqui:** Open source, runs locally, supports Hindi. Quality is acceptable for a travel assistant. ElevenLabs is the recommended upgrade for premium voice quality.

---

## Implementation

### Voice Pipeline Orchestrator

```python
# apps/backend/src/parikrama/voice/pipeline.py
"""
Voice pipeline orchestrator — connects VAD, STT, and TTS.

Manages the full lifecycle of a voice interaction:
1. Receive audio stream from LiveKit
2. Detect speech with Silero VAD
3. Transcribe with Whisper
4. Process through agent pipeline
5. Generate speech response with TTS
6. Stream audio back to user

Handles interrupts: if user speaks while TTS is playing, stop TTS immediately.
"""
import asyncio
import io
import time

import numpy as np
import structlog

from parikrama.voice.stt import WhisperSTT
from parikrama.voice.tts import TTSEngine
from parikrama.voice.vad import SileroVAD

logger = structlog.get_logger()


class VoicePipeline:
    """Full-duplex voice interaction pipeline."""

    def __init__(self, on_transcript: callable, on_response: callable) -> None:
        self.vad = SileroVAD()
        self.stt = WhisperSTT()
        self.tts = TTSEngine()

        # callbacks
        self._on_transcript = on_transcript    # called when user speech is transcribed
        self._on_response = on_response         # called with TTS audio chunks

        # state
        self._is_speaking = False               # user is currently speaking
        self._is_responding = False              # TTS is currently playing
        self._audio_buffer = io.BytesIO()        # accumulate audio during speech
        self._cancel_tts = asyncio.Event()       # signal to stop TTS

    async def process_audio_frame(self, audio_data: bytes, sample_rate: int = 16000) -> None:
        """
        Process a single audio frame from LiveKit.

        Called for every audio frame (~20ms of audio at 16kHz).
        VAD determines if the user is speaking.
        """
        # convert bytes to numpy array for VAD
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        is_speech = self.vad.is_speech(audio_array, sample_rate)

        if is_speech and not self._is_speaking:
            # speech started
            self._is_speaking = True
            self._audio_buffer = io.BytesIO()

            # if TTS is playing, interrupt it (user wants to speak)
            if self._is_responding:
                self._cancel_tts.set()
                self._is_responding = False
                logger.info("tts_interrupted_by_user")

        if is_speech:
            # accumulate audio data
            self._audio_buffer.write(audio_data)

        if not is_speech and self._is_speaking:
            # speech ended — transcribe the accumulated audio
            self._is_speaking = False
            audio_bytes = self._audio_buffer.getvalue()

            if len(audio_bytes) > 3200:  # minimum ~100ms of audio
                asyncio.create_task(self._handle_speech_end(audio_bytes, sample_rate))

    async def _handle_speech_end(self, audio_bytes: bytes, sample_rate: int) -> None:
        """Process completed speech: transcribe → respond → speak."""
        start = time.perf_counter()

        # step 1: transcribe with Whisper
        transcript = await self.stt.transcribe(audio_bytes, sample_rate)

        if not transcript or not transcript.strip():
            return

        stt_time = (time.perf_counter() - start) * 1000
        logger.info("voice_transcribed", text=transcript[:100], latency_ms=round(stt_time, 1))

        # step 2: send transcript to agent pipeline
        response_text = await self._on_transcript(transcript)

        if not response_text:
            return

        # step 3: generate and stream TTS audio
        self._is_responding = True
        self._cancel_tts.clear()

        total_latency = (time.perf_counter() - start) * 1000
        logger.info(
            "voice_pipeline_latency",
            stt_ms=round(stt_time, 1),
            total_ms=round(total_latency, 1),
        )

        await self._stream_tts(response_text)

    async def _stream_tts(self, text: str) -> None:
        """Generate TTS audio and stream it chunk by chunk."""
        try:
            async for audio_chunk in self.tts.synthesize_stream(text):
                if self._cancel_tts.is_set():
                    logger.info("tts_cancelled")
                    break
                await self._on_response(audio_chunk)
        finally:
            self._is_responding = False
```

### Speech-to-Text (Whisper)

```python
# apps/backend/src/parikrama/voice/stt.py
"""
Whisper-based Speech-to-Text.

Uses OpenAI's Whisper base model running locally.
Supports English and Hindi (important for Indian users).
"""
import asyncio
import io
import tempfile
import wave
from functools import lru_cache

import structlog
import whisper

logger = structlog.get_logger()


class WhisperSTT:
    """Local Whisper model for speech-to-text."""

    def __init__(self, model_size: str = "base") -> None:
        self._model = None
        self._model_size = model_size

    @property
    def model(self):
        """Lazy load the Whisper model — takes ~2s on first call."""
        if self._model is None:
            logger.info("loading_whisper_model", size=self._model_size)
            self._model = whisper.load_model(self._model_size)
            logger.info("whisper_model_loaded")
        return self._model

    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """
        Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw PCM audio (16-bit, mono)
            sample_rate: Audio sample rate (16kHz for LiveKit)
            language: Force language detection ('en', 'hi') or None for auto
        """
        # write audio to a temp WAV file (Whisper expects file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)      # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            # run transcription in thread pool (Whisper is CPU-bound)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.model.transcribe(
                    tmp.name,
                    language=language,
                    task="transcribe",
                    fp16=False,         # CPU mode
                ),
            )

        text = result.get("text", "").strip()
        detected_lang = result.get("language", "unknown")

        logger.info(
            "whisper_transcribed",
            text_length=len(text),
            language=detected_lang,
        )

        return text
```

### Voice Activity Detection (Silero VAD)

```python
# apps/backend/src/parikrama/voice/vad.py
"""
Voice Activity Detection using Silero VAD.

Detects when the user starts and stops speaking.
Much more accurate than energy-based VAD — handles background noise well.
"""
import torch
import structlog

logger = structlog.get_logger()


class SileroVAD:
    """Silero VAD — knows when the user is speaking."""

    def __init__(self, threshold: float = 0.5) -> None:
        self._model = None
        self._threshold = threshold

    @property
    def model(self):
        if self._model is None:
            logger.info("loading_silero_vad")
            model, utils = torch.hub.load(
                "snakers4/silero-vad", "silero_vad", trust_repo=True
            )
            self._model = model
            logger.info("silero_vad_loaded")
        return self._model

    def is_speech(self, audio_chunk: "np.ndarray", sample_rate: int = 16000) -> bool:
        """
        Check if an audio chunk contains speech.

        Args:
            audio_chunk: Float32 numpy array of audio samples
            sample_rate: Must be 16000 for Silero VAD
        """
        tensor = torch.from_numpy(audio_chunk)
        confidence = self.model(tensor, sample_rate).item()
        return confidence > self._threshold

    def reset(self) -> None:
        """Reset VAD state between sessions."""
        if self._model is not None:
            self._model.reset_states()
```

### Text-to-Speech Engine

```python
# apps/backend/src/parikrama/voice/tts.py
"""
TTS Engine — generates speech from text.

Primary: Coqui TTS (open source, local)
Fallback: ElevenLabs API (better quality, limited free tier)

Streams audio in chunks for low-latency playback.
"""
import asyncio
import io
from collections.abc import AsyncGenerator

import structlog

from parikrama.config import settings

logger = structlog.get_logger()


class TTSEngine:
    """Text-to-Speech with streaming output."""

    def __init__(self) -> None:
        self._engine = None

    def _load_engine(self):
        """Load Coqui TTS model."""
        from TTS.api import TTS
        self._engine = TTS("tts_models/en/ljspeech/vits")
        logger.info("coqui_tts_loaded")

    async def synthesize_stream(
        self, text: str, language: str = "en",
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text to audio and yield chunks for streaming.

        Splits text into sentences for faster first-byte latency.
        """
        # split text into sentences for streaming
        sentences = self._split_into_sentences(text)

        for sentence in sentences:
            if not sentence.strip():
                continue

            # generate audio for this sentence
            audio_bytes = await self._synthesize_sentence(sentence)
            if audio_bytes:
                yield audio_bytes

    async def _synthesize_sentence(self, text: str) -> bytes | None:
        """Synthesize a single sentence to WAV bytes."""
        if self._engine is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_engine)

        try:
            loop = asyncio.get_event_loop()
            wav = await loop.run_in_executor(
                None,
                lambda: self._engine.tts(text),
            )

            # convert numpy audio to bytes
            import numpy as np
            audio_int16 = (np.array(wav) * 32767).astype(np.int16)
            return audio_int16.tobytes()

        except Exception as e:
            logger.error("tts_synthesis_failed", error=str(e), text=text[:50])
            return None

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text at sentence boundaries for streaming."""
        import re
        sentences = re.split(r'(?<=[.!?।])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
```

### LiveKit Room Management

```python
# apps/backend/src/parikrama/voice/livekit_manager.py
"""
LiveKit room and token management.

Creates rooms for voice sessions and generates access tokens.
Each trip planning session gets its own LiveKit room.
"""
from livekit import api

from parikrama.config import settings


class LiveKitManager:
    """Manage LiveKit rooms and participant tokens."""

    def __init__(self) -> None:
        self.api = api.LiveKitAPI(
            settings.LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://"),
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET,
        )

    def create_token(self, room_name: str, participant_name: str, is_agent: bool = False) -> str:
        """Generate a LiveKit access token for a participant."""
        token = api.AccessToken(
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET,
        )
        token.with_identity(participant_name)
        token.with_name(participant_name)

        grant = api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        )
        token.with_grants(grant)

        return token.to_jwt()

    async def create_room(self, room_name: str) -> dict:
        """Create a LiveKit room for a voice session."""
        room = await self.api.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                empty_timeout=300,      # 5 min auto-close
                max_participants=3,     # user + agent + observer
            )
        )
        return {"name": room.name, "sid": room.sid}


livekit_manager = LiveKitManager()
```

---

## Environment Variables Required

```bash
# Phase 6:
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
WHISPER_MODEL_SIZE=base              # tiny | base | small | medium
TTS_ENGINE=coqui                     # coqui | elevenlabs
ELEVENLABS_API_KEY=                  # optional, for premium TTS
VAD_THRESHOLD=0.5                    # speech detection sensitivity
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| VAD detects speech vs silence | Unit | Silero correctly classifies audio |
| Whisper transcribes English | Unit | English text output correct |
| Whisper transcribes Hindi | Unit | Hindi text output correct |
| TTS generates audio | Unit | Non-empty audio bytes produced |
| Pipeline interrupt works | Integration | TTS stops when user speaks |
| LiveKit token generation | Unit | Valid JWT token created |
| End-to-end voice flow | Integration | Speak → Transcribe → Respond → Audio |

---

## Definition of Done — Phase 6

- [ ] LiveKit server running in Docker
- [ ] Voice session creates a LiveKit room
- [ ] Silero VAD detects speech start/end accurately
- [ ] Whisper transcribes English and Hindi audio
- [ ] Coqui TTS generates speech from agent responses
- [ ] Full-duplex: user can interrupt agent mid-speech
- [ ] Voice pipeline latency < 800ms (first audio byte)
- [ ] Frontend voice button with recording indicator
- [ ] Audio format handling (WebM → WAV conversion)

## Scale-Up Path

| Component | Current | Trigger | Upgrade |
|-----------|---------|---------|---------|
| Whisper | CPU (base model) | Latency > 1s | GPU + small/medium model |
| TTS | Coqui (local) | Quality complaints | ElevenLabs API |
| LiveKit | Single server | >100 concurrent rooms | LiveKit Cloud |
| VAD | Per-connection instance | Memory > 1GB/worker | Shared VAD process |

---

*Phase 6 transforms PariKrama from a text-only tool into a conversational travel advisor. Users can plan trips hands-free while commuting.*
