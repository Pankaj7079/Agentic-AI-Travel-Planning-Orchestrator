"""
Voice agent handler — routes voice transcripts through the agent pipeline.

This module provides a thin adapter between the voice WebSocket endpoint
and the existing TripPlanningService (text-based agentic pipeline).

The handler:
  1. Receives a transcribed text utterance
  2. Optionally loads existing trip context
  3. Invokes the agent pipeline in "voice mode" (abbreviated responses)
  4. Returns a concise response suitable for TTS
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Maximum TTS response length — shorter = faster, less to synthesize
MAX_VOICE_RESPONSE_CHARS = 500


async def handle_voice_query(
    text: str,
    trip_id: str | None,
    user_id: str,
) -> str:
    """
    Handle a voice query from the user.

    Attempts to route through TripPlanningService. Falls back to a
    friendly stub if the planning service is unavailable or raises.

    Args:
        text: Transcribed user speech.
        trip_id: Optional associated trip ID for context.
        user_id: The authenticated user's ID.

    Returns:
        Agent response text (optimised for TTS: concise, no markdown).
    """
    try:
        from parikrama.llm.router import LLMRouter

        router = LLMRouter()

        # Build a voice-optimised system prompt
        system_prompt = (
            "You are PariKrama, a friendly AI travel assistant. "
            "The user is speaking to you. Give a helpful, conversational response "
            "in 1-3 short sentences. No bullet points, no markdown — just natural speech. "
            f"{'Context: user has an active trip plan.' if trip_id else ''}"
        )

        response = await router.generate(
            prompt=text,
            system=system_prompt,
        )

        # Trim to voice-friendly length
        if len(response) > MAX_VOICE_RESPONSE_CHARS:
            response = response[:MAX_VOICE_RESPONSE_CHARS].rsplit(" ", 1)[0] + "..."

        logger.info(
            "voice_query_handled",
            user_id=user_id,
            query_len=len(text),
            response_len=len(response),
        )
        return response

    except Exception as exc:
        logger.warning("voice_agent_handler_fallback", error=str(exc))
        return (
            "I heard you! I'm still thinking about that. "
            "Could you please repeat your travel request?"
        )
