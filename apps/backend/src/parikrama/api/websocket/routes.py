"""
WebSocket endpoint — real-time agent progress and approval notifications.

Authentication: JWT token passed as a query parameter `?token=<access_token>`
since WebSocket browsers cannot send custom headers.

Heartbeat: The server sends a ping frame every 30 seconds to prevent
proxy/load-balancer timeouts. Client should respond with pong.

Message types received from server:
    agent_update       — progress event from a running agent node
    approval_request   — HITL gate: user needs to approve/reject
    trip_completed     — itinerary is ready
    notification       — generic notification (email, push equivalent)
    pong               — heartbeat response

Message types accepted from client:
    ping               — heartbeat keepalive (server replies pong)
"""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from parikrama.api.websocket.manager import ws_manager
from parikrama.core.security import decode_token

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])

HEARTBEAT_INTERVAL = 30  # seconds


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(..., description="JWT access token for authentication"),
) -> None:
    """
    WebSocket connection endpoint for real-time updates.

    Connect with: ws://localhost:8000/ws/<user_id>?token=<access_token>

    The server validates the JWT and ensures the token's user_id matches
    the URL parameter to prevent subscribing to another user's events.
    """
    # ── Authenticate ──────────────────────────────────────────────────────
    try:
        payload = decode_token(token)
        token_user_id = payload.get("sub", "")
        if token_user_id != user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(
                "ws_auth_mismatch",
                token_user_id=token_user_id,
                url_user_id=user_id,
            )
            return
    except Exception as exc:
        logger.warning("ws_auth_failed", error=str(exc)[:100])
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # ── Connect ───────────────────────────────────────────────────────────
    await ws_manager.connect(user_id, websocket)

    # welcome message
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "user_id": user_id,
                    "message": "PariKrama live updates active",
                }
            )
        )
    except Exception:
        await ws_manager.disconnect(user_id, websocket)
        return

    # ── Message loop with heartbeat ───────────────────────────────────────
    try:
        while True:
            # Wait for client message with timeout for heartbeat
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=HEARTBEAT_INTERVAL)
                data = json.loads(raw)

                if data.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

            except TimeoutError:
                # Send ping to keep connection alive through proxies
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break  # connection is dead

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected", user_id=user_id)
    except Exception as exc:
        logger.error("ws_error", user_id=user_id, error=str(exc)[:100])
    finally:
        await ws_manager.disconnect(user_id, websocket)
