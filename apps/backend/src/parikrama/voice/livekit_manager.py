"""
LiveKit room and token management.

Creates LiveKit rooms for voice sessions and generates JWT access tokens
for both users (participants) and the agent (server-side observer).

Each voice session gets its own LiveKit room:
    room_name = "voice-{user_id}-{short_uuid}"

Token scopes:
  - User token: can_publish=True, can_subscribe=True
  - Agent token: can_publish=True, can_subscribe=True, room_record=True

LiveKit server URL is configured via LIVEKIT_URL env var.
In development, run: docker run -p 7880:7880 livekit/livekit-server --dev
"""

from __future__ import annotations

import structlog

from parikrama.config import settings

logger = structlog.get_logger(__name__)


class LiveKitManager:
    """
    Manage LiveKit rooms and participant tokens.

    Token generation uses the LiveKit JWT SDK (livekit package).
    Room management uses the LiveKit Server API (livekit-api package).
    """

    def create_token(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: str,
        *,
        can_publish: bool = True,
        can_subscribe: bool = True,
        room_record: bool = False,
    ) -> str:
        """
        Generate a LiveKit JWT access token for a participant.

        Args:
            room_name: The LiveKit room name to grant access to.
            participant_identity: Unique identifier (e.g. user UUID).
            participant_name: Display name shown in the room.
            can_publish: Whether the participant can publish tracks.
            can_subscribe: Whether the participant can subscribe to tracks.
            room_record: Extra permission for server-side recording.

        Returns:
            Signed JWT token string (valid 6 hours).
        """
        from livekit.api import AccessToken, VideoGrants  # type: ignore[import]

        token = AccessToken(
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )
        token.with_identity(participant_identity)
        token.with_name(participant_name)
        token.with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=can_publish,
                can_subscribe=can_subscribe,
                room_record=room_record,
            )
        )

        jwt = token.to_jwt()
        logger.debug(
            "livekit_token_created",
            room=room_name,
            identity=participant_identity,
        )
        return jwt

    async def create_room(self, room_name: str) -> dict:
        """
        Create a LiveKit room via the Server API.

        Args:
            room_name: Unique room name.

        Returns:
            Dict with 'name' and 'sid' of the created room.
        """
        from livekit.api import CreateRoomRequest, LiveKitAPI  # type: ignore[import]

        lk_api = LiveKitAPI(
            url=settings.LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://"),
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )

        try:
            room = await lk_api.room.create_room(
                CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,  # auto-close after 5min of inactivity
                    max_participants=3,  # user + server agent + observer
                )
            )
            logger.info("livekit_room_created", room=room_name, sid=room.sid)
            return {"name": room.name, "sid": room.sid}
        except Exception as exc:
            logger.error("livekit_room_create_failed", room=room_name, error=str(exc))
            raise

    async def delete_room(self, room_name: str) -> None:
        """
        Delete a LiveKit room and disconnect all participants.

        Called when a voice session ends (user hangs up or session times out).
        """
        from livekit.api import DeleteRoomRequest, LiveKitAPI  # type: ignore[import]

        lk_api = LiveKitAPI(
            url=settings.LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://"),
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )

        try:
            await lk_api.room.delete_room(DeleteRoomRequest(room=room_name))
            logger.info("livekit_room_deleted", room=room_name)
        except Exception as exc:
            # non-fatal — room may already be gone
            logger.warning("livekit_room_delete_failed", room=room_name, error=str(exc))


# module-level singleton
livekit_manager = LiveKitManager()
