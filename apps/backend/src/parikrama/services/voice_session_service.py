"""
VoiceSessionService — manages the lifecycle of a voice planning session.

A voice session:
1. Creates a LiveKit room for audio transport
2. Returns a JWT token for the browser to join the room
3. Maintains an active VoicePipeline per session
4. Routes transcribed speech through the existing TripPlanningService
5. Streams TTS audio back via WebSocket or LiveKit room

Sessions are ephemeral — no DB persistence in Phase 6.
Future phases may persist transcripts and session metadata.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog

from parikrama.config import settings
from parikrama.voice.audio_utils import webm_to_pcm
from parikrama.voice.livekit_manager import livekit_manager
from parikrama.voice.pipeline import VoicePipeline

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

logger = structlog.get_logger(__name__)


class VoiceSession:
    """
    Represents an active voice session for a single user.

    Owns the VoicePipeline and holds references to the LiveKit room name
    and any active WebSocket audio bridges.
    """

    def __init__(
        self,
        session_id: str,
        room_name: str,
        user_id: str,
        trip_id: str | None,
    ) -> None:
        self.session_id = session_id
        self.room_name = room_name
        self.user_id = user_id
        self.trip_id = trip_id

        # pipeline is set up by VoiceSessionService after creation
        self.pipeline: VoicePipeline | None = None
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)

    async def enqueue_audio_chunk(self, chunk: bytes) -> None:
        """Called by TTS engine — puts audio chunk into output queue."""
        try:
            self._audio_queue.put_nowait(chunk)
        except asyncio.QueueFull:
            logger.warning("voice_audio_queue_full", session_id=self.session_id)

    async def audio_chunks(self) -> AsyncGenerator[bytes, None]:
        """Async generator — yields TTS audio chunks as they arrive."""
        while True:
            try:
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=30.0)
                yield chunk
            except TimeoutError:
                break  # session ended or no activity for 30s


class VoiceSessionService:
    """
    Manages all active voice sessions.

    Responsibilities:
      - Create / teardown voice sessions
      - Route audio frames through VoicePipeline
      - Provide access to TTS audio output stream
    """

    def __init__(self) -> None:
        # session_id → VoiceSession
        self._sessions: dict[str, VoiceSession] = {}

    async def create_session(
        self,
        user_id: str,
        trip_id: str | None = None,
    ) -> dict:
        """
        Create a new voice session.

        1. Creates a LiveKit room
        2. Generates user JWT token
        3. Returns session metadata for the client

        Args:
            user_id: The authenticated user's ID.
            trip_id: Optional trip to associate with this voice session.

        Returns:
            Dict with session_id, room_name, user_token, livekit_url.
        """
        session_id = str(uuid.uuid4())
        room_name = f"voice-{user_id[:8]}-{session_id[:8]}"

        # create LiveKit room (best-effort, non-fatal if LiveKit is offline)
        try:
            await livekit_manager.create_room(room_name)
        except Exception as exc:
            logger.warning(
                "livekit_room_creation_failed_continuing",
                room=room_name,
                error=str(exc),
            )

        # generate user access token
        user_token = livekit_manager.create_token(
            room_name=room_name,
            participant_identity=user_id,
            participant_name=f"user-{user_id[:8]}",
        )

        session = VoiceSession(
            session_id=session_id,
            room_name=room_name,
            user_id=user_id,
            trip_id=trip_id,
        )
        self._sessions[session_id] = session

        logger.info(
            "voice_session_created",
            session_id=session_id,
            room_name=room_name,
            user_id=user_id,
            trip_id=trip_id,
        )

        return {
            "session_id": session_id,
            "room_name": room_name,
            "user_token": user_token,
            "livekit_url": settings.LIVEKIT_URL,
        }

    def build_pipeline(
        self,
        session_id: str,
        on_transcript: Callable,
    ) -> VoicePipeline:
        """
        Attach a VoicePipeline to an existing session.

        The on_transcript callback is provided by the WebSocket endpoint;
        it calls the agent and returns the response text.

        Args:
            session_id: The voice session ID.
            on_transcript: async (text: str) -> str — agent handler.

        Returns:
            Configured VoicePipeline.
        """
        session = self._get_session(session_id)

        async def _on_audio_chunk(chunk: bytes) -> None:
            await session.enqueue_audio_chunk(chunk)

        pipeline = VoicePipeline(
            on_transcript=on_transcript,
            on_audio_chunk=_on_audio_chunk,
        )
        session.pipeline = pipeline
        return pipeline

    async def process_audio_bytes(
        self,
        session_id: str,
        audio_bytes: bytes,
        is_webm: bool = True,
        sample_rate: int = 16000,
    ) -> None:
        """
        Process a chunk of audio from the WebSocket stream.

        Decodes WebM/Opus if needed, then feeds frames to the VoicePipeline.

        Args:
            session_id: The voice session ID.
            audio_bytes: Raw audio bytes (WebM or PCM).
            is_webm: True if input is WebM/Opus (from browser MediaRecorder).
            sample_rate: Target sample rate for PCM (default 16kHz).
        """
        session = self._get_session(session_id)
        if session.pipeline is None:
            raise ValueError(
                f"Voice session {session_id} has no pipeline; call build_pipeline() first"
            )

        # decode WebM → raw PCM if needed
        if is_webm:
            try:
                pcm_bytes = webm_to_pcm(audio_bytes, target_sample_rate=sample_rate)
            except ValueError as exc:
                logger.warning("webm_decode_skipped", session_id=session_id, error=str(exc))
                return
        else:
            pcm_bytes = audio_bytes

        # feed in 20ms frames (640 bytes at 16kHz 16-bit mono)
        frame_size = int(sample_rate * 0.02 * 2)  # 20ms * sample_rate * 2 bytes
        offset = 0
        while offset + frame_size <= len(pcm_bytes):
            frame = pcm_bytes[offset : offset + frame_size]
            await session.pipeline.process_audio_frame(frame, sample_rate)
            offset += frame_size

    def get_audio_stream(self, session_id: str) -> AsyncGenerator[bytes, None]:
        """Return the TTS audio output async generator for this session."""
        session = self._get_session(session_id)
        return session.audio_chunks()

    async def end_session(self, session_id: str, user_id: str) -> None:
        """
        End a voice session and clean up resources.

        Deletes the LiveKit room and removes the session from memory.
        """
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        if session.user_id != user_id:
            # restore and reject
            self._sessions[session_id] = session
            raise PermissionError(f"User {user_id} does not own session {session_id}")

        if session.pipeline:
            session.pipeline.reset()

        try:
            await livekit_manager.delete_room(session.room_name)
        except Exception as exc:
            logger.warning("livekit_room_delete_failed_on_end", error=str(exc))

        logger.info("voice_session_ended", session_id=session_id)

    def _get_session(self, session_id: str) -> VoiceSession:
        """Retrieve session or raise ValueError."""
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Voice session not found: {session_id}")
        return session

    @property
    def active_session_count(self) -> int:
        """Number of currently active voice sessions (for monitoring)."""
        return len(self._sessions)


# module-level singleton — shared across all WebSocket connections
voice_session_service = VoiceSessionService()
