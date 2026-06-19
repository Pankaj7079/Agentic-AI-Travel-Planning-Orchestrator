"""
Chat Assistant API — powers the floating Krama AI chatbot.

Simple, lightweight endpoint that uses the LLM router to answer
general questions about PariKrama and travel planning.
Authentication is optional — works for both logged-in and public users.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

KRAMA_SYSTEM_PROMPT = """You are Krama, the friendly AI assistant for PariKrama — an intelligent agentic AI travel planning platform built for Indian travelers.

PariKrama features:
- Multi-agent LangGraph pipeline: Orchestrator → Research + Booking (parallel) → Budget Optimizer → Itinerary Finalizer
- Human-in-the-loop approvals for key decisions
- Support for English, Hindi, and Hinglish
- Detailed day-by-day itineraries with activities, meals, tips
- Budget breakdowns in INR
- Hotel options, transport options
- PDF export and sharing
- Real-time agent progress via WebSocket

Your role:
- Answer questions about PariKrama features, how to use the platform, travel tips
- Be friendly, helpful, and concise
- Use emojis naturally to make responses engaging
- Keep answers under 150 words unless the question demands detail
- Guide users to the right feature (Dashboard → New Trip, etc.)
- Don't make up prices or real hotel/flight bookings — you only plan, not book

Always respond in the same language as the user (English, Hindi, or Hinglish).
"""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    context: str = Field(default="parikrama_assistant", max_length=100)


class ChatResponse(BaseModel):
    response: str
    provider: str


@router.post("/assistant", response_model=ChatResponse)
async def chat_with_krama(body: ChatRequest, request: Request) -> ChatResponse:
    """
    Chat with Krama AI — the PariKrama floating assistant.

    Authentication is optional. Works for both public visitors and
    logged-in users. Uses the shared LLM router with Gemini as primary
    and Groq as fallback.
    """
    try:
        from parikrama.config import settings
        from parikrama.llm.router import LLMRouter

        llm = LLMRouter.from_settings(settings)
        response = await llm.generate(
            prompt=body.message,
            system=KRAMA_SYSTEM_PROMPT,
            temperature=0.65,
        )

        logger.info(
            "krama_chat_response",
            provider=response.provider,
            latency_ms=response.latency_ms,
            msg_len=len(body.message),
        )

        return ChatResponse(
            response=response.content,
            provider=response.provider,
        )

    except Exception as exc:
        logger.warning("krama_chat_fallback", error=str(exc)[:100])
        # Graceful fallback — never let the chatbot crash
        return ChatResponse(
            response=(
                "I'm having a quick hiccup! 🤔 Here's what I know:\n\n"
                "• **Plan a trip** → Dashboard → New Trip → describe your vacation\n"
                "• **See itinerary** → Dashboard → My Trips → click any trip\n"
                "• **Approvals** → agents pause for your OK on big decisions\n\n"
                "Try refreshing or asking again in a moment!"
            ),
            provider="fallback",
        )
