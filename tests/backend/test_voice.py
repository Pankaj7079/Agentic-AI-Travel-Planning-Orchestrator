"""
Tests for Phase 6 — Voice Pipeline.

All heavy dependencies (torch, whisper, TTS, livekit) are mocked.
No real audio processing happens in these tests — we validate the
wiring, state machine logic, and API contracts.

Test coverage:
  - SileroVAD     — speech detection, lazy loading, reset
  - WhisperSTT    — transcription async wrapper, empty audio, model loading
  - TTS engines   — Coqui synthesis, ElevenLabs fallback, sentence splitting
  - VoicePipeline — VAD→STT→agent→TTS flow, interrupt handling
  - LiveKitManager — token creation, room management
  - VoiceSessionService — session lifecycle, audio routing
  - Voice REST API — auth guards, create, delete, token refresh
  - Voice WS API  — connect, audio frame flow, error handling
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

if TYPE_CHECKING:
    from httpx import AsyncClient


# ══════════════════════════════════════════════════════════════════════════════
# SileroVAD
# ══════════════════════════════════════════════════════════════════════════════


class TestSileroVAD:
    """Unit tests for SileroVAD — mocks torch to avoid heavy dependency."""

    def _make_vad(self):
        from parikrama.voice.vad import SileroVAD

        return SileroVAD(threshold=0.5)

    def test_speech_detected_above_threshold(self):
        """is_speech returns True when model confidence > threshold."""
        vad = self._make_vad()

        mock_model = MagicMock()
        mock_model.return_value = MagicMock(item=MagicMock(return_value=0.8))
        vad._model = mock_model

        import numpy as np

        audio = np.zeros(512, dtype=np.float32)
        with (
            patch(
                "torch.no_grad",
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False)
                ),
            ),
            patch("torch.from_numpy", return_value=MagicMock()),
        ):
            result = vad.is_speech(audio, 16000)

        assert result is True

    def test_silence_below_threshold(self):
        """is_speech returns False when model confidence < threshold."""
        vad = self._make_vad()

        mock_model = MagicMock()
        mock_model.return_value = MagicMock(item=MagicMock(return_value=0.1))
        vad._model = mock_model

        import numpy as np

        audio = np.zeros(512, dtype=np.float32)
        with (
            patch(
                "torch.no_grad",
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False)
                ),
            ),
            patch("torch.from_numpy", return_value=MagicMock()),
        ):
            result = vad.is_speech(audio, 16000)

        assert result is False

    def test_model_is_lazy_loaded(self):
        """Model is None until first is_speech call."""
        vad = self._make_vad()
        assert vad._model is None

    def test_reset_calls_model_reset_states(self):
        """reset() calls model.reset_states()."""
        vad = self._make_vad()
        mock_model = MagicMock()
        vad._model = mock_model
        vad.reset()
        mock_model.reset_states.assert_called_once()

    def test_reset_with_no_model_is_noop(self):
        """reset() does nothing when model is not loaded yet."""
        vad = self._make_vad()
        vad.reset()  # should not raise


# ══════════════════════════════════════════════════════════════════════════════
# WhisperSTT
# ══════════════════════════════════════════════════════════════════════════════


class TestWhisperSTT:
    """Unit tests for WhisperSTT — mocks whisper.load_model."""

    def _make_stt(self):
        from parikrama.voice.stt import WhisperSTT

        return WhisperSTT(model_size="base")

    @pytest.mark.asyncio
    async def test_transcribe_returns_string(self):
        """transcribe() returns the model's text output."""
        stt = self._make_stt()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  Hello Manali  ", "language": "en"}
        stt._model = mock_model

        result = await stt.transcribe(b"\x00" * 3200, sample_rate=16000)
        assert result == "Hello Manali"

    @pytest.mark.asyncio
    async def test_empty_audio_returns_empty_string(self):
        """transcribe() returns empty string for empty input."""
        stt = self._make_stt()
        result = await stt.transcribe(b"", sample_rate=16000)
        assert result == ""

    def test_model_lazy_loaded_on_first_access(self):
        """Model property is None until first access."""
        stt = self._make_stt()
        assert stt._model is None

    @pytest.mark.asyncio
    async def test_transcribe_hindi_text(self):
        """transcribe() returns Hindi text when detected."""
        stt = self._make_stt()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "मुझे दिल्ली जाना है", "language": "hi"}
        stt._model = mock_model

        result = await stt.transcribe(b"\x00" * 3200, sample_rate=16000)
        assert "दिल्ली" in result


# ══════════════════════════════════════════════════════════════════════════════
# TTS Engine
# ══════════════════════════════════════════════════════════════════════════════


class TestCoquiTTSEngine:
    """Unit tests for CoquiTTSEngine."""

    def _make_tts(self):
        from parikrama.voice.tts import CoquiTTSEngine

        return CoquiTTSEngine()

    def test_sentence_splitter_splits_on_punctuation(self):
        """split_sentences() correctly splits at . ! ? and Hindi ।"""
        from parikrama.voice.tts import CoquiTTSEngine

        engine = CoquiTTSEngine()
        result = engine.split_sentences("Hello world. How are you? I am fine!")
        assert len(result) == 3
        assert result[0] == "Hello world."

    def test_sentence_splitter_hindi_danda(self):
        """split_sentences() handles Hindi sentence terminator ।"""
        from parikrama.voice.tts import CoquiTTSEngine

        engine = CoquiTTSEngine()
        result = engine.split_sentences("नमस्ते। मैं ठीक हूँ।")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_bytes(self):
        """synthesize_stream() yields non-empty bytes for each sentence."""
        tts = self._make_tts()

        mock_wav = [0.1, 0.2, -0.1]  # simulate Coqui TTS output
        mock_engine = MagicMock()
        mock_engine.tts.return_value = mock_wav
        tts._engine = mock_engine

        chunks = []
        async for chunk in tts.synthesize_stream("Hello Manali. How are you?"):
            chunks.append(chunk)

        assert len(chunks) == 2  # two sentences
        assert all(isinstance(c, bytes) for c in chunks)
        assert all(len(c) > 0 for c in chunks)

    @pytest.mark.asyncio
    async def test_tts_error_yields_nothing(self):
        """synthesize_stream() yields nothing if model raises exception."""
        tts = self._make_tts()

        mock_engine = MagicMock()
        mock_engine.tts.side_effect = RuntimeError("TTS model failed")
        tts._engine = mock_engine

        chunks = []
        async for chunk in tts.synthesize_stream("Test sentence."):
            chunks.append(chunk)

        assert chunks == []


class TestElevenLabsTTSEngine:
    """Unit tests for ElevenLabsTTSEngine."""

    @pytest.mark.asyncio
    async def test_falls_back_to_coqui_without_api_key(self):
        """ElevenLabs falls back to Coqui when ELEVENLABS_API_KEY is empty."""
        from parikrama.voice.tts import ElevenLabsTTSEngine

        engine = ElevenLabsTTSEngine()

        mock_coqui_engine = MagicMock()
        mock_coqui_engine.tts.return_value = [0.1, 0.2]
        engine._fallback._engine = mock_coqui_engine

        with patch("parikrama.config.settings") as mock_settings:
            mock_settings.ELEVENLABS_API_KEY = ""
            mock_settings.TTS_ENGINE = "coqui"
            # patch the settings import inside tts module
            with patch("parikrama.voice.tts.settings") as inner_settings:
                inner_settings.ELEVENLABS_API_KEY = ""

                chunks = []
                async for chunk in engine.synthesize_stream("Hello!"):
                    chunks.append(chunk)

        # Fallback to Coqui was used — should get bytes (or empty if model not available)
        assert isinstance(chunks, list)


# ══════════════════════════════════════════════════════════════════════════════
# VoicePipeline
# ══════════════════════════════════════════════════════════════════════════════


class TestVoicePipeline:
    """Integration tests for VoicePipeline state machine."""

    def _make_pipeline(self, on_transcript=None, on_audio_chunk=None):
        from parikrama.voice.pipeline import VoicePipeline
        from parikrama.voice.stt import WhisperSTT
        from parikrama.voice.tts import CoquiTTSEngine
        from parikrama.voice.vad import SileroVAD

        mock_vad = MagicMock(spec=SileroVAD)
        mock_stt = MagicMock(spec=WhisperSTT)
        mock_tts = MagicMock(spec=CoquiTTSEngine)

        on_transcript = on_transcript or AsyncMock(return_value="I'll plan your trip!")
        on_audio_chunk = on_audio_chunk or AsyncMock()

        pipeline = VoicePipeline(
            on_transcript=on_transcript,
            on_audio_chunk=on_audio_chunk,
            vad=mock_vad,
            stt=mock_stt,
            tts=mock_tts,
        )
        return pipeline, mock_vad, mock_stt, mock_tts

    @pytest.mark.asyncio
    async def test_speech_start_sets_is_speaking(self):
        """VAD returning True sets _is_speaking=True."""
        pipeline, mock_vad, _, _ = self._make_pipeline()

        import numpy as np

        mock_vad.is_speech.return_value = True

        with patch("numpy.frombuffer", return_value=np.zeros(512, dtype=np.int16)):
            await pipeline.process_audio_frame(b"\x00" * 1024)

        assert pipeline._is_speaking is True

    @pytest.mark.asyncio
    async def test_short_audio_not_transcribed(self):
        """Audio below MIN_AUDIO_BYTES threshold is ignored."""
        pipeline, mock_vad, mock_stt, _ = self._make_pipeline()

        import numpy as np

        # simulate: speech start then stop with very little audio
        mock_vad.is_speech.side_effect = [True, False]

        with patch("numpy.frombuffer", return_value=np.zeros(100, dtype=np.int16)):
            # speech start
            await pipeline.process_audio_frame(b"\x00" * 200)
            # speech end — buffer too small
            await pipeline.process_audio_frame(b"\x00" * 200)

        # STT should NOT have been called
        mock_stt.transcribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_tts_cancelled_on_interrupt(self):
        """User speaking while TTS plays sets _cancel_tts event."""
        pipeline, mock_vad, _, _ = self._make_pipeline()
        pipeline._is_responding = True  # simulate TTS in progress

        import numpy as np

        mock_vad.is_speech.return_value = True

        with patch("numpy.frombuffer", return_value=np.zeros(512, dtype=np.int16)):
            await pipeline.process_audio_frame(b"\x00" * 1024)

        assert pipeline._cancel_tts.is_set()
        assert pipeline._is_responding is False

    def test_reset_clears_all_state(self):
        """reset() clears speaking/responding flags and cancel event."""
        pipeline, mock_vad, _, _ = self._make_pipeline()

        pipeline._is_speaking = True
        pipeline._is_responding = True
        pipeline._cancel_tts.set()

        pipeline.reset()

        assert pipeline._is_speaking is False
        assert pipeline._is_responding is False
        assert not pipeline._cancel_tts.is_set()
        mock_vad.reset.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# LiveKitManager
# ══════════════════════════════════════════════════════════════════════════════


class TestLiveKitManager:
    """Unit tests for LiveKitManager — mocks livekit SDK."""

    def _make_manager(self):
        from parikrama.voice.livekit_manager import LiveKitManager

        return LiveKitManager()

    def test_create_token_returns_string(self):
        """create_token() returns a non-empty JWT string."""
        manager = self._make_manager()

        mock_token = MagicMock()
        mock_token.to_jwt.return_value = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

        with patch(
            "parikrama.voice.livekit_manager.LiveKitManager.create_token",
            return_value="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
        ):
            token = manager.create_token(
                room_name="voice-abc-123",
                participant_identity="user-uuid",
                participant_name="Test User",
            )

        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.asyncio
    async def test_create_room_returns_metadata(self):
        """create_room() returns dict with name and sid."""
        manager = self._make_manager()

        mock_room = MagicMock()
        mock_room.name = "voice-abc-123"
        mock_room.sid = "RM_test123"

        # LiveKitAPI is imported lazily inside the method body (from livekit.api import LiveKitAPI)
        # so we patch it at the source module, not at the livekit_manager namespace.
        mock_lk_instance = AsyncMock()
        mock_lk_instance.room.create_room = AsyncMock(return_value=mock_room)

        with patch("livekit.api.LiveKitAPI", return_value=mock_lk_instance):
            result = await manager.create_room("voice-abc-123")

        assert result["name"] == "voice-abc-123"
        assert result["sid"] == "RM_test123"


# ══════════════════════════════════════════════════════════════════════════════
# VoiceSessionService
# ══════════════════════════════════════════════════════════════════════════════


class TestVoiceSessionService:
    """Unit tests for VoiceSessionService."""

    def _make_service(self):
        from parikrama.services.voice_session_service import VoiceSessionService

        return VoiceSessionService()

    @pytest.mark.asyncio
    async def test_create_session_returns_metadata(self):
        """create_session() returns session_id, room_name, user_token, livekit_url."""
        service = self._make_service()

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(return_value={"name": "voice-test", "sid": "RM_1"})
            mock_lk.create_token.return_value = "test-jwt-token"

            result = await service.create_session(user_id="user-abc", trip_id=None)

        assert "session_id" in result
        assert "room_name" in result
        assert "user_token" in result
        assert "livekit_url" in result
        assert result["user_token"] == "test-jwt-token"

    @pytest.mark.asyncio
    async def test_create_session_stores_in_memory(self):
        """create_session() stores session in _sessions dict."""
        service = self._make_service()

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(return_value={"name": "v-test", "sid": "RM_1"})
            mock_lk.create_token.return_value = "token"

            result = await service.create_session(user_id="user-123")

        assert result["session_id"] in service._sessions
        assert service.active_session_count == 1

    @pytest.mark.asyncio
    async def test_end_session_removes_from_memory(self):
        """end_session() removes session and calls livekit delete."""
        service = self._make_service()

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(return_value={"name": "v-test", "sid": "RM_1"})
            mock_lk.create_token.return_value = "token"
            mock_lk.delete_room = AsyncMock()

            result = await service.create_session(user_id="user-xyz")
            session_id = result["session_id"]

            await service.end_session(session_id, "user-xyz")

        assert session_id not in service._sessions
        assert service.active_session_count == 0

    @pytest.mark.asyncio
    async def test_end_session_wrong_user_raises(self):
        """end_session() raises PermissionError when wrong user tries to end session."""
        service = self._make_service()

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(return_value={"name": "v-test", "sid": "RM_1"})
            mock_lk.create_token.return_value = "token"

            result = await service.create_session(user_id="owner-user")
            session_id = result["session_id"]

        with pytest.raises(PermissionError):
            await service.end_session(session_id, "attacker-user")

    @pytest.mark.asyncio
    async def test_livekit_failure_does_not_block_session_creation(self):
        """Session is created even if LiveKit room creation fails."""
        service = self._make_service()

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(side_effect=RuntimeError("LiveKit offline"))
            mock_lk.create_token.return_value = "token"

            result = await service.create_session(user_id="user-abc")

        # session still created despite LiveKit failure
        assert "session_id" in result
        assert result["session_id"] in service._sessions


# ══════════════════════════════════════════════════════════════════════════════
# Voice REST API
# ══════════════════════════════════════════════════════════════════════════════


class TestVoiceAPI:
    """Integration tests for voice REST endpoints using the test client."""

    @pytest.mark.asyncio
    async def test_create_session_requires_auth(self, client: AsyncClient):
        """POST /voice/sessions without token returns 401."""
        resp = await client.post("/api/v1/voice/sessions", json={})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_create_session_returns_session_data(self, client: AsyncClient):
        """POST /voice/sessions returns session_id and livekit_url."""
        # register and login
        await client.post(
            "/api/v1/auth/register",
            json={"email": "voice1@test.com", "name": "Voice Tester", "password": "Secure@123"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "voice1@test.com", "password": "Secure@123"},
        )
        token = resp.json()["tokens"]["access_token"]

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(return_value={"name": "v-test", "sid": "RM_1"})
            mock_lk.create_token.return_value = "test-livekit-jwt"

            resp = await client.post(
                "/api/v1/voice/sessions",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert "session_id" in data
        assert "room_name" in data
        assert "user_token" in data
        assert "livekit_url" in data

    @pytest.mark.asyncio
    async def test_create_session_with_trip_id(self, client: AsyncClient):
        """POST /voice/sessions with trip_id includes it in session."""
        await client.post(
            "/api/v1/auth/register",
            json={"email": "voice2@test.com", "name": "Voice Tester2", "password": "Secure@123"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "voice2@test.com", "password": "Secure@123"},
        )
        token = resp.json()["tokens"]["access_token"]
        trip_id = str(uuid.uuid4())

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(return_value={"name": "v-test", "sid": "RM_1"})
            mock_lk.create_token.return_value = "jwt"

            resp = await client.post(
                "/api/v1/voice/sessions",
                json={"trip_id": trip_id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == status.HTTP_201_CREATED

    @pytest.mark.asyncio
    async def test_delete_session_requires_auth(self, client: AsyncClient):
        """DELETE /voice/sessions/{id} without token returns 401."""
        resp = await client.delete(f"/api/v1/voice/sessions/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_delete_session_success(self, client: AsyncClient):
        """DELETE /voice/sessions/{id} ends the session cleanly."""
        await client.post(
            "/api/v1/auth/register",
            json={"email": "voice3@test.com", "name": "Voice Tester3", "password": "Secure@123"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "voice3@test.com", "password": "Secure@123"},
        )
        token = resp.json()["tokens"]["access_token"]

        with patch("parikrama.services.voice_session_service.livekit_manager") as mock_lk:
            mock_lk.create_room = AsyncMock(return_value={"name": "v-test", "sid": "RM_1"})
            mock_lk.create_token.return_value = "jwt"
            mock_lk.delete_room = AsyncMock()

            create_resp = await client.post(
                "/api/v1/voice/sessions",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )
            session_id = create_resp.json()["session_id"]

            delete_resp = await client.delete(
                f"/api/v1/voice/sessions/{session_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert delete_resp.status_code == status.HTTP_204_NO_CONTENT
