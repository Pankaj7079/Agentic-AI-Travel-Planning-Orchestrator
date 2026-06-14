"""
Pydantic schemas for the Voice Pipeline API (Phase 6).

Request/response models for:
  - Creating a voice session
  - WebSocket audio frame messages
  - Session status and cleanup
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceSessionCreateRequest(BaseModel):
    """Request body for POST /v1/voice/sessions."""

    trip_id: str | None = Field(
        default=None,
        description="Optional trip ID to associate with this voice session. "
        "If provided, the agent uses this trip's context for planning.",
    )


class VoiceSessionResponse(BaseModel):
    """Response from POST /v1/voice/sessions."""

    session_id: str = Field(description="Unique voice session identifier.")
    room_name: str = Field(description="LiveKit room name for WebRTC connection.")
    user_token: str = Field(description="JWT token to join the LiveKit room.")
    livekit_url: str = Field(description="LiveKit server WebSocket URL.")


class VoiceSessionStatusResponse(BaseModel):
    """Response from GET /v1/voice/sessions/{session_id}/status."""

    session_id: str
    room_name: str
    active: bool


# ── WebSocket message schemas ──────────────────────────────────────────────────


class WSAudioMessage(BaseModel):
    """
    WebSocket message from client → server (audio frame).

    Clients send base64-encoded audio chunks as JSON messages:
      { "type": "audio", "data": "<base64>", "format": "webm", "sample_rate": 16000 }
    """

    type: str = Field(default="audio")
    data: str = Field(description="Base64-encoded audio bytes.")
    format: str = Field(
        default="webm",
        description="Audio format: 'webm' (browser MediaRecorder) or 'pcm' (raw 16-bit).",
    )
    sample_rate: int = Field(
        default=16000,
        description="Sample rate in Hz (must match server VAD expectations).",
    )


class WSTranscriptMessage(BaseModel):
    """
    WebSocket message from server → client (transcript event).

    Sent when Whisper finishes transcribing an utterance.
    """

    type: str = "transcript"
    text: str
    language: str = "en"
    session_id: str


class WSAudioResponseMessage(BaseModel):
    """
    WebSocket message from server → client (TTS audio chunk).

    Server sends base64-encoded audio chunks as the TTS streams.
    """

    type: str = "audio_response"
    data: str = Field(description="Base64-encoded PCM audio bytes.")
    sequence: int = Field(description="Chunk sequence number for ordering.")


class WSErrorMessage(BaseModel):
    """WebSocket error event from server → client."""

    type: str = "error"
    code: str
    message: str


class WSEndMessage(BaseModel):
    """WebSocket event signalling the end of a TTS response."""

    type: str = "response_end"
    session_id: str
