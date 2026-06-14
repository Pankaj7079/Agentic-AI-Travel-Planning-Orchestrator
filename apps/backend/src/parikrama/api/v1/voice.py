"""
Voice Pipeline API — REST endpoints + WebSocket audio bridge.

REST endpoints:
  POST   /v1/voice/sessions           — create voice session + LiveKit token
  DELETE /v1/voice/sessions/{id}      — end session, clean up LiveKit room
  GET    /v1/voice/sessions/{id}/token — refresh token (e.g., after expiry)

WebSocket endpoint:
  WS /v1/voice/sessions/{session_id}/stream

  The WebSocket bridge allows browsers to stream audio without native WebRTC:
    Client → server: { type: "audio", data: "<base64 webm>", format: "webm" }
    Server → client: { type: "transcript", text: "..." }
    Server → client: { type: "audio_response", data: "<base64 pcm>", sequence: N }
    Server → client: { type: "response_end" }
    Server → client: { type: "error", code: "...", message: "..." }

  This is also used for testing the full pipeline without a real LiveKit room.
"""

from __future__ import annotations

import asyncio
import base64
import json

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from parikrama.core.security import get_current_user_id
from parikrama.schemas.voice import (
    VoiceSessionCreateRequest,
    VoiceSessionResponse,
    WSEndMessage,
    WSErrorMessage,
    WSTranscriptMessage,
)
from parikrama.services.voice_session_service import voice_session_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/voice", tags=["Voice"])


# ── REST: Session management ──────────────────────────────────────────────────


@router.post("/sessions", response_model=VoiceSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_session(
    body: VoiceSessionCreateRequest,
    user_id: str = Depends(get_current_user_id),
) -> VoiceSessionResponse:
    """
    Create a new voice session.

    Returns a LiveKit room name and JWT token the browser uses to join via WebRTC.
    Also supports the WebSocket fallback (see /sessions/{id}/stream).
    """
    result = await voice_session_service.create_session(
        user_id=user_id,
        trip_id=body.trip_id,
    )
    logger.info("voice_session_created_api", user_id=user_id, session_id=result["session_id"])
    return VoiceSessionResponse(**result)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def end_voice_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    """
    End a voice session and release LiveKit resources.

    Only the session owner can end a session.
    """
    try:
        await voice_session_service.end_session(session_id, user_id)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Session not found"}
        )
    except PermissionError:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Not your session"}
        )


@router.get("/sessions/{session_id}/token")
async def refresh_voice_token(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """
    Refresh the LiveKit token for an active session.

    Returns a new JWT token valid for 6 more hours.
    """
    from parikrama.voice.livekit_manager import livekit_manager

    # token refresh: we need the room name from the session
    # sessions are in-memory on the singleton service
    session = voice_session_service._sessions.get(session_id)
    if session is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Session not found"}
        )
    if session.user_id != user_id:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Not your session"}
        )

    new_token = livekit_manager.create_token(
        room_name=session.room_name,
        participant_identity=user_id,
        participant_name=f"user-{user_id[:8]}",
    )
    return {"user_token": new_token, "session_id": session_id}


# ── WebSocket: Audio streaming bridge ────────────────────────────────────────


@router.websocket("/sessions/{session_id}/stream")
async def voice_stream(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    WebSocket audio bridge — full-duplex voice interaction without native WebRTC.

    Authentication: pass JWT token as query param ?token=<access_token>
    Protocol (JSON):
      Client → Server:  { "type": "audio", "data": "<base64>", "format": "webm" }
      Server → Client:  { "type": "transcript", "text": "...", "session_id": "..." }
      Server → Client:  { "type": "audio_response", "data": "<base64>", "sequence": N }
      Server → Client:  { "type": "response_end", "session_id": "..." }
      Server → Client:  { "type": "error", "code": "...", "message": "..." }
    """
    from parikrama.core.security import decode_token

    # ── Authenticate via query param token ────────────────────────────────────
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise ValueError("No user ID in token")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    logger.info("voice_ws_connected", session_id=session_id, user_id=user_id)

    # ── Validate session ownership ────────────────────────────────────────────
    session = voice_session_service._sessions.get(session_id)
    if session is None:
        await websocket.send_text(
            WSErrorMessage(code="SESSION_NOT_FOUND", message="Session not found").model_dump_json()
        )
        await websocket.close(code=4004)
        return

    if session.user_id != user_id:
        await websocket.send_text(
            WSErrorMessage(code="FORBIDDEN", message="Not your session").model_dump_json()
        )
        await websocket.close(code=4003)
        return

    # ── Build voice pipeline ──────────────────────────────────────────────────
    audio_chunk_seq = 0

    async def handle_transcript(text: str) -> str:
        """Called by VoicePipeline when Whisper finishes transcribing."""
        # send transcript event to client
        await websocket.send_text(
            WSTranscriptMessage(
                text=text,
                session_id=session_id,
            ).model_dump_json()
        )

        # run through agent pipeline — for now, simple echo back
        # Phase 7 will wire this to TripPlanningService
        try:
            from parikrama.services.voice_agent_handler import handle_voice_query

            response = await handle_voice_query(text, session.trip_id, user_id)
        except ImportError:
            # stub response until voice agent handler is wired
            response = (
                f"I heard you say: {text}. "
                "I'm your PariKrama travel assistant. "
                "Tell me where you'd like to go and I'll plan your trip!"
            )
        return response

    pipeline = voice_session_service.build_pipeline(session_id, handle_transcript)

    # ── Task: forward TTS audio chunks to client ──────────────────────────────
    async def forward_audio_chunks() -> None:
        nonlocal audio_chunk_seq
        audio_gen = voice_session_service.get_audio_stream(session_id)
        async for chunk in audio_gen:
            audio_chunk_seq += 1
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "audio_response",
                        "data": base64.b64encode(chunk).decode(),
                        "sequence": audio_chunk_seq,
                    }
                )
            )
        # signal end of response
        await websocket.send_text(WSEndMessage(session_id=session_id).model_dump_json())

    forwarding_task = asyncio.create_task(forward_audio_chunks(), name="forward_audio")

    # ── Main receive loop ─────────────────────────────────────────────────────
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except TimeoutError:
                # send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    WSErrorMessage(
                        code="INVALID_JSON", message="Message must be valid JSON"
                    ).model_dump_json()
                )
                continue

            msg_type = msg.get("type")

            if msg_type == "audio":
                # decode base64 audio and feed into pipeline
                try:
                    audio_bytes = base64.b64decode(msg.get("data", ""))
                    audio_format = msg.get("format", "webm")
                    sample_rate = int(msg.get("sample_rate", 16000))
                    is_webm = audio_format == "webm"
                    await voice_session_service.process_audio_bytes(
                        session_id=session_id,
                        audio_bytes=audio_bytes,
                        is_webm=is_webm,
                        sample_rate=sample_rate,
                    )
                except Exception as exc:
                    logger.warning("audio_frame_processing_error", error=str(exc))
                    await websocket.send_text(
                        WSErrorMessage(code="AUDIO_ERROR", message=str(exc)).model_dump_json()
                    )

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "end":
                logger.info("voice_ws_client_ended", session_id=session_id)
                break

    except WebSocketDisconnect:
        logger.info("voice_ws_disconnected", session_id=session_id)
    except Exception as exc:
        logger.error("voice_ws_error", session_id=session_id, error=str(exc))
    finally:
        forwarding_task.cancel()
        pipeline.reset()
        logger.info("voice_ws_cleanup_done", session_id=session_id)
