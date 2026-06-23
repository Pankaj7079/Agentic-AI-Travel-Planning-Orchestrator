"""
Chat Assistant API — powers the floating Krama AI chatbot.

Krama is a knowledgeable, friendly Indian travel companion AI.
She gives warm, personalized, contextually rich travel advice —
not robotic bullet points. Think of her as a well-travelled
friend who happens to know everything about India.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger("parikrama.api.v1.chat")
router = APIRouter(prefix="/chat", tags=["chat"])

# ── Master system prompt ───────────────────────────────────────────────────────

KRAMA_SYSTEM_PROMPT = """You are Krama — a warm, knowledgeable, and genuinely helpful AI travel companion for PariKrama, India's smartest travel planning platform.

## Your Personality
You are like a well-travelled Indian friend who gives real, honest advice. You:
- Sound human, warm, and conversational — never robotic or corporate
- Use natural language including mild Hinglish ("Bhai, Manali mein...") when the user writes in Hindi/Hinglish
- Share specific, concrete recommendations — not generic filler
- Are honest when you don't know something exact
- Use one or two relevant emojis per message (not every sentence)
- Sometimes share a fun travel fact or insider tip

## What You Know About PariKrama
PariKrama is an AI-powered Indian travel planning platform that:
- Creates complete day-by-day itineraries in 60–90 seconds using multi-agent AI
- Covers all major Indian destinations: hill stations, beaches, heritage cities, forests
- Plans within any budget (budget ₹5,000 to luxury ₹5,00,000+)
- Understands English, Hindi, and Hinglish naturally
- Provides hotel options, transport choices (bus/train/flight), budget breakdowns
- Has a Human-in-the-Loop (HITL) system for your approval on major decisions
- Exports trip plans as PDF for offline use

## How to Use PariKrama (guide users accurately)
1. **Login/Register** at the top right
2. Go to **Dashboard → New Trip** (or click the ✈️ button)
3. Just type your trip request naturally — "5 din Manali trip, Delhi se, ₹15,000 mein"
4. AI agents will run (takes 30–90 seconds): Research → Hotels/Transport → Budget → Itinerary
5. Review and approve the plan
6. Download as PDF or share the link

## Indian Travel Expertise You Can Share
- Best times to visit different destinations (weather, crowds, festivals)
- Budget travel hacks (Tatkal vs Advance booking, shared cabs, dhabas vs restaurants)
- Train/bus/flight comparisons for common routes
- Hidden gems and offbeat destinations near popular ones
- Visa/permit requirements for restricted areas (Ladakh, Northeast India, Andaman)
- Cultural tips (dress codes, local customs, tipping norms)
- Food recommendations (local specialties by region)

## Response Guidelines
- Keep responses CONVERSATIONAL and to-the-point (80–200 words usually)
- Give SPECIFIC answers — "Manali to Kasol is ₹200–400 by shared cab" not "transport costs vary"
- If asked about trip planning → guide them to use PariKrama properly
- If asked general travel questions → give genuine helpful advice like a knowledgeable friend
- For budget estimates → give rough real ranges in INR
- Never make up flight/hotel prices as exact facts — say "around" or "roughly"
- Always respond in the SAME LANGUAGE as the user (English, Hindi, or Hinglish)
- Never start with "Sure!" or "Certainly!" — jump straight to the helpful content

## Example Responses
User: "Manali trip 5 days, ₹15,000 mein possible hai?"
Krama: "Haan bilkul possible hai! 🏔️ ₹15,000 mein Manali ka solid trip hota hai. Delhi se Volvo bus ₹1,200–1,500 return, budget guesthouses ₹500–800/night. Khane mein ₹200–300/day comfortable rehta hai. Rohtang Pass, Solang Valley, Old Manali ghoom sakte ho aaram se. PariKrama mein trip plan karo — sab automatically calculate ho jaayega!"

User: "Best time to visit Kerala?"
Krama: "Kerala is gorgeous year-round, but the sweet spot is October to March 🌴 — post-monsoon greens, cool backwaters, no heavy rains. December–January is peak season (crowded + expensive). If you want quieter beaches and lower prices, September–October is magical after the rains. Avoid June–August unless you specifically want to experience the monsoon — it's beautiful but travel gets challenging."
"""


# ── Schemas ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: str = Field(default="parikrama_assistant", max_length=100)
    # Optional: pass recent chat history for context
    history: list[dict] | None = Field(default=None, max_length=10)


class ChatResponse(BaseModel):
    response: str
    provider: str


# ── Smart offline knowledge base ──────────────────────────────────────────────

def _smart_offline_response(message: str) -> str:
    """
    Give a contextually relevant offline response when LLM is unavailable.
    Much better than a generic error message.
    """
    msg = message.lower()

    if any(w in msg for w in ["manali", "shimla", "kullu", "spiti", "lahaul"]):
        return (
            "Himachal Pradesh is stunning! 🏔️ Best visited April–June (snow melts, roads open) "
            "or September–October (post-monsoon clarity). Delhi to Manali is about 14–16 hours by Volvo bus (₹1,200–1,800). "
            "Budget travelers do well at ₹1,500–2,500/day including stay and food.\n\n"
            "To get a detailed plan → use **PariKrama**: go to Dashboard → New Trip and describe your trip. "
            "Our AI will plan everything in under 90 seconds!"
        )
    elif any(w in msg for w in ["goa", "beach", "sea", "ocean"]):
        return (
            "Goa is perfect October–March 🌊 — sunny, sea's calm, nightlife buzzing. "
            "North Goa (Anjuna, Vagator) is livelier; South Goa (Palolem, Agonda) is peaceful. "
            "Mumbai to Goa: overnight train (Mandovi Express) is the classic way — ₹400–1,200 depending on class. "
            "Budget: ₹2,000–3,500/day covers stay + food + scooter rental.\n\n"
            "Let PariKrama plan your Goa trip → Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["kerala", "munnar", "allepey", "backwater", "cochin", "kochi"]):
        return (
            "Kerala — God's Own Country! 🌴 Best Oct–March. "
            "Must-dos: Munnar tea gardens, Alleppey houseboat (₹3,000–8,000/night), Kovalam beach. "
            "Trains from major cities are the most comfortable option. "
            "Budget: ₹2,500–4,000/day for a good mid-range experience.\n\n"
            "Try PariKrama for a full Kerala itinerary → Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["rajasthan", "jaipur", "udaipur", "jodhpur", "jaisalmer"]):
        return (
            "Rajasthan is magical October–March! 🏯 "
            "The golden triangle (Jaipur–Agra–Delhi) is iconic for first-timers. "
            "Udaipur is the most romantic city in India, hands down. "
            "Jaisalmer desert camps are unforgettable — budget ₹2,000–5,000/night. "
            "Trains between Rajasthan cities are reliable and scenic.\n\n"
            "Plan your Rajasthan royal tour → PariKrama Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["ladakh", "leh", "pangong", "nubra"]):
        return (
            "Ladakh is a dream destination! ❄️ Only accessible June–September (roads open). "
            "Inner Line Permit (ILP) needed for Pangong, Nubra, Tso Moriri — ₹400–600, get online. "
            "Acclimatize for 2–3 days in Leh before high-altitude treks. "
            "Budget: ₹4,000–7,000/day (permits, stays, local transport). "
            "Fly Delhi→Leh (₹4,000–8,000) or drive Manali–Leh highway (2 days, epic experience).\n\n"
            "Plan your Ladakh adventure → PariKrama Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["plan", "trip", "parikrama", "how", "kaise", "karna", "start", "help"]):
        return (
            "Here's how to use PariKrama to plan your trip in 3 steps 🗺️\n\n"
            "1. **Login** (top right) → **Dashboard** → **New Trip**\n"
            "2. Just describe your trip naturally: *\"5 days Manali from Delhi, ₹15,000, 2 people\"*\n"
            "3. Our AI agents will research destinations, find hotels & transport, optimize budget, "
            "and create a day-by-day itinerary — all in 60–90 seconds!\n\n"
            "You can then review, approve, and download your plan as PDF. "
            "No need to fill long forms — just talk to the planner!"
        )
    elif any(w in msg for w in ["budget", "cost", "price", "kitna", "cheap", "affordable", "₹", "rs", "rupee"]):
        return (
            "Budget planning really depends on destination and style 💰 Rough India travel ranges:\n\n"
            "• **Ultra Budget** (hostels + local food): ₹800–1,500/day\n"
            "• **Mid-range** (decent hotels + restaurants): ₹2,500–5,000/day\n"
            "• **Comfortable** (3-star hotels + AC travel): ₹5,000–10,000/day\n"
            "• **Premium** (5-star + flights): ₹15,000+/day\n\n"
            "PariKrama will calculate the exact budget breakdown for your specific trip. "
            "Go to Dashboard → New Trip and mention your budget — it'll optimize everything for you!"
        )
    else:
        return (
            "I'm Krama, your PariKrama travel companion! 🌏 "
            "I can help you:\n\n"
            "• **Plan a trip** → describe where you want to go and I'll guide you\n"
            "• **Travel tips** → best time to visit, what to pack, local food recommendations\n"
            "• **Budget advice** → rough costs for Indian destinations\n"
            "• **Use PariKrama** → Dashboard → New Trip → describe your trip naturally\n\n"
            "What would you like to explore? Ask me anything about your upcoming trip! ✈️"
        )


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/assistant", response_model=ChatResponse)
async def chat_with_krama(body: ChatRequest, request: Request) -> ChatResponse:
    """
    Chat with Krama AI — the PariKrama floating assistant.

    Authentication is optional. Uses the shared LLM router with Gemini
    as primary and Groq as fallback. Falls back to smart offline KB
    if no LLM provider is configured.
    """
    try:
        from parikrama.config import settings
        from parikrama.llm.router import LLMRouter

        llm = LLMRouter.from_settings(settings)

        # Build prompt — include recent chat history if provided
        prompt = body.message
        if body.history:
            history_text = "\n".join(
                f"{'User' if h.get('role') == 'user' else 'Krama'}: {h.get('content', '')}"
                for h in body.history[-6:]  # last 3 exchanges
            )
            prompt = f"Recent conversation:\n{history_text}\n\nUser: {body.message}"

        response = await llm.generate(
            prompt=prompt,
            system=KRAMA_SYSTEM_PROMPT,
            temperature=0.72,  # slightly creative but grounded
        )

        logger.info(
            "krama_chat_response",
            layer="CHATBOT",
            provider=response.provider,
            latency_ms=response.latency_ms,
            msg_len=len(body.message),
            context=body.context,
        )

        return ChatResponse(
            response=response.content,
            provider=response.provider,
        )

    except Exception as exc:
        err_str = str(exc)
        logger.warning(
            "krama_chat_fallback",
            layer="CHATBOT",
            error=err_str[:200],
            hint="LLM provider not available — using offline KB response",
        )
        # Smart contextual fallback — not a generic error message
        return ChatResponse(
            response=_smart_offline_response(body.message),
            provider="offline_kb",
        )
