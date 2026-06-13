"""
WebSocket connection manager for real-time agent updates.

Manages per-user WebSocket connections — supports multiple tabs/devices.
Broadcasts: agent progress, approval requests, trip status changes.

Key design:
- One global singleton (ws_manager) shared across the FastAPI process.
- Async lock prevents race conditions when multiple connections close at once.
- Dead connections detected on send and pruned automatically.
- 30-second heartbeat pings prevent proxy timeouts (handled in the route).
"""

import asyncio
import json

import structlog
from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """Manage active WebSocket connections per user."""

    def __init__(self) -> None:
        # user_id → set of active WebSocket connections (multi-tab support)
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection for a user."""
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
        logger.info(
            "ws_connected",
            user_id=user_id,
            total_connections=len(self._connections.get(user_id, set())),
        )

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
        logger.info("ws_disconnected", user_id=user_id)

    async def send_to_user(self, user_id: str, message: dict) -> int:
        """
        Send a message to all connections for a user.

        Returns number of successfully delivered messages.
        Dead connections are detected here and pruned.
        """
        connections = self._connections.get(user_id, set()).copy()
        if not connections:
            return 0

        sent = 0
        failed: list[WebSocket] = []
        payload = json.dumps(message, default=str)

        for ws in connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(payload)
                    sent += 1
                else:
                    failed.append(ws)
            except Exception as exc:
                logger.debug("ws_send_failed", error=str(exc)[:80])
                failed.append(ws)

        # prune dead connections
        if failed:
            async with self._lock:
                for ws in failed:
                    self._connections.get(user_id, set()).discard(ws)
                if user_id in self._connections and not self._connections[user_id]:
                    del self._connections[user_id]

        return sent

    async def broadcast_agent_update(
        self,
        user_id: str,
        trip_id: str,
        agent: str,
        status: str,
        message: str,
    ) -> None:
        """Broadcast an agent progress update to the user."""
        await self.send_to_user(
            user_id,
            {
                "type": "agent_update",
                "trip_id": trip_id,
                "agent": agent,
                "status": status,
                "message": message,
            },
        )

    async def broadcast_approval_request(
        self,
        user_id: str,
        approval_id: str,
        title: str,
        description: str,
        payload: dict,
    ) -> None:
        """Send an approval request card to the user."""
        await self.send_to_user(
            user_id,
            {
                "type": "approval_request",
                "approval_id": approval_id,
                "title": title,
                "description": description,
                "payload": payload,
            },
        )

    async def broadcast_trip_completed(self, user_id: str, trip_id: str) -> None:
        """Notify user that trip planning is done."""
        await self.send_to_user(
            user_id,
            {"type": "trip_completed", "trip_id": trip_id},
        )

    @property
    def active_connections(self) -> int:
        """Total active connections across all users."""
        return sum(len(conns) for conns in self._connections.values())

    @property
    def connected_users(self) -> int:
        """Number of distinct users with at least one open connection."""
        return len(self._connections)


# ── Singleton ─────────────────────────────────────────────────────────────────
# One instance per process — FastAPI shares this across all requests.
ws_manager = ConnectionManager()
