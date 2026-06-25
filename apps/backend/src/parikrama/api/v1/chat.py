"""
Chat Assistant API — powers the floating Krama AI chatbot.

Krama is a knowledgeable, friendly Indian travel companion AI.
She gives warm, personalized, contextually rich travel advice —
not robotic bullet points. Think of her as a well-travelled
friend who happens to know everything about India.

Features:
  - Web search integration (Tavily/DuckDuckGo) for real-time info
  - Expanded Indian travel knowledge base
  - Smart search detection (knows when to search vs. answer from knowledge)
  - Chat history support for contextual conversations
  - Offline KB fallback when LLM is unavailable
"""

from __future__ import annotations

import re

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
- Creates complete day-by-day itineraries in 60-90 seconds using multi-agent AI
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
4. AI agents will run (takes 30-90 seconds): Research → Hotels/Transport → Budget → Itinerary
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

## Detailed Destination Knowledge

### Hill Stations
- **Manali**: April-June for snow, Oct-Nov for clear views. Delhi→Manali Volvo ₹1,200-1,800. Budget stay ₹500-1,000/night. Must-visit: Solang Valley, Rohtang Pass (permit needed), Old Manali cafes, Hadimba Temple.
- **Shimla**: Year-round (snow in Dec-Feb). Kalka-Shimla toy train is iconic. ₹800-1,500/night budget. Mall Road, Ridge, Kufri, Chail nearby.
- **Darjeeling**: Oct-Dec or Mar-May. toy train UNESCO site. ₹1,000-2,000/night. Tiger Hill sunrise, Batasia Loop, tea gardens.
- **Mussoorie**: Apr-Jun, Sep-Nov. Delhi→Mussoorie 6hrs. ₹800-1,500/night. Kempty Falls, Gun Hill, Camel's Back Road.
- **Coorg (Kodagu)**: Oct-Mar. Bangalore→Coorg 5hrs. ₹1,000-2,500/night. Abbey Falls, Dubare elephant camp, coffee plantations.
- **Ooty/Kodaikanal**: Oct-Mar. Chennai→Ooty train scenic. ₹800-2,000/night. Nilgiri toy train, botanical gardens, lake boating.

### Beaches
- **Goa**: Oct-Mar. North Goa (Anjuna, Vagator) for nightlife, South Goa (Palolem, Agonda) for peace. Scooter ₹300-500/day. Budget ₹1,500-3,000/day.
- **Kerala beaches**: Kovalam, Varkala (Oct-Mar). Peaceful, less crowded than Goa.
- **Gokarna**: Oct-Mar. Budget alternative to Goa. ₹500-1,000/day. Om Beach, Half Moon Beach.
- **Andaman**: Oct-May. Port Blair→Havelock ferry ₹500-1,800. Scuba ₹3,500-6,000. Budget ₹3,000-5,000/day.

### Heritage & Culture
- **Rajasthan**: Oct-Mar. Golden Triangle (Delhi-Agra-Jaipur) for first-timers. Udaipur lakes, Jaisalmer desert, Jodhpur blue city. ₹1,500-5,000/day.
- **Varanasi**: Oct-Mar. Evening Ganga Aarti is unmissable. ₹800-2,000/day. Sarnath nearby.
- **Khajuraho**: Oct-Mar. Famous temple sculptures. ₹500-1,500/day.
- **Hampi**: Oct-Feb. UNESCO ruins. ₹500-1,200/day. Bicycle exploration is best.

### Wildlife & Nature
- **Jim Corbett**: Nov-Jun. Safari ₹3,500-5,000/jeep. Stay ₹1,000-3,000/night.
- **Kaziranga**: Nov-Apr. One-horned rhino. Elephant safari ₹500, Jeep ₹3,000-4,000.
- **Ranthambore**: Oct-Apr. Tiger spotting. ₹100-1,500 entry + safari costs.
- **Spiti Valley**: Jun-Sep. Remote Himalayan. Manali→Spiti 2 days. ₹2,000-4,000/day.

### Offbeat Gems
- **Meghalaya**: Nov-Mar. Living root bridges, Dawki crystal river, Mawlynnong cleanest village.
- **Ziro Valley**: Sep-Oct. Arunachal. Peaceful, rice paddies, Apatani culture.
- **Hampi**: Oct-Feb. Ancient ruins, bouldering, sunset at Matanga Hill.
- **Tirthan Valley**: Mar-Jun, Sep-Nov. Great Himalayan NP, trout fishing, village homestays.

## Transport Knowledge
- **Trains**: Book on IRCTC 120 days in advance. Tatkal opens 1 day before (10am AC, 11am non-AC). Rajdhani/Shatabdi for premium, Sleeper for budget.
- **Buses**: State transport (RSRTC, HRTC, KSRTC) are cheapest. Private Volvos for comfort. RedBus/AbhiBus for booking.
- **Flights**: IndiGo/SpiceJet for budget. Book 3-4 weeks early. ₹3,000-8,000 domestic one-way.
- **Cabs**: Ola/Uber in cities. Shared cabs for hill stations (much cheaper). Self-drive available in major cities.

## Budget Ranges (per person per day)
- Backpacker: ₹800-1,500 (hostels, local food, public transport)
- Budget: ₹1,500-3,000 (guesthouses, restaurants, shared transport)
- Mid-range: ₹3,000-6,000 (3-star hotels, AC travel, guided tours)
- Premium: ₹6,000-15,000 (4-star hotels, flights, private cabs)
- Luxury: ₹15,000+ (5-star, business class, private experiences)

## Response Guidelines
- Keep responses CONVERSATIONAL and to-the-point (80-200 words usually)
- Give SPECIFIC answers — "Manali to Kasol is ₹200-400 by shared cab" not "transport costs vary"
- If asked about trip planning → guide them to use PariKrama properly
- If asked general travel questions → give genuine helpful advice like a knowledgeable friend
- For budget estimates → give rough real ranges in INR
- Never make up flight/hotel prices as exact facts — say "around" or "roughly"
- Always respond in the SAME LANGUAGE as the user (English, Hindi, or Hinglish)
- Never start with "Sure!" or "Certainly!" — jump straight to the helpful content
- When web search results are provided, use them to give CURRENT, accurate information
- Always mention that PariKrama can create a full plan for any trip discussed

## Example Responses
User: "Manali trip 5 days, ₹15,000 mein possible hai?"
Krama: "Haan bilkul possible hai! 🏔️ ₹15,000 mein Manali ka solid trip hota hai. Delhi se Volvo bus ₹1,200-1,500 return, budget guesthouses ₹500-800/night. Khane mein ₹200-300/day comfortable rehta hai. Rohtang Pass, Solang Valley, Old Manali ghoom sakte ho aaram se. PariKrama mein trip plan karo — sab automatically calculate ho jaayega!"

User: "Best time to visit Kerala?"
Krama: "Kerala is gorgeous year-round, but the sweet spot is October to March 🌴 — post-monsoon greens, cool backwaters, no heavy rains. December-January is peak season (crowded + expensive). If you want quieter beaches and lower prices, September-October is magical after the rains. Avoid June-August unless you specifically want to experience the monsoon — it's beautiful but travel gets challenging."
"""


# ── Schemas ────────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: str = Field(default="parikrama_assistant", max_length=100)
    history: list[dict] | None = Field(default=None, max_length=10)


class ChatResponse(BaseModel):
    response: str
    provider: str
    searched_web: bool = False


# ── Web search detection ──────────────────────────────────────────────────────

# Patterns that indicate the user wants real-time / current information
_SEARCH_TRIGGERS = [
    r"\b(weather|temperature|forecast|mausam)\b",
    r"\b(current|latest|recent|today|tonight|tomorrow|this week|this month)\b",
    r"\b(price|cost|fare|ticket|rate|charges|kitne|mein)\b.*\b(hotel|flight|bus|train|cab|room)\b",
    r"\b(hotel|flight|bus|train|cab|room)\b.*\b(price|cost|fare|ticket|rate|charges|kitne|mein)\b",
    r"\b(events?|festival|concert|mela|fair)\b.*\b(now|today|this|upcoming)\b",
    r"\b(open|closed|timing|hours|schedule|timetable)\b",
    r"\b(road condition|traffic|highway|route)\b",
    r"\b(booking|available|vacancy|seat)\b",
]

_DESTINATION_PATTERNS = [
    r"(?:in|to|at|for|of|near)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    r"(?:trip|travel|visit|go to|tour)\s+(?:to\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
]


def _needs_web_search(message: str) -> bool:
    """Detect if the message likely needs real-time web information."""
    msg_lower = message.lower()
    return any(re.search(p, msg_lower) for p in _SEARCH_TRIGGERS)


def _extract_destination(message: str) -> str:
    """Try to extract a destination name from the message."""
    for pattern in _DESTINATION_PATTERNS:
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
    return ""


# ── Smart offline knowledge base ──────────────────────────────────────────────


def _smart_offline_response(message: str) -> str:
    """Give a contextually relevant offline response when LLM is unavailable."""
    msg = message.lower()

    if any(w in msg for w in ["manali", "shimla", "kullu", "spiti", "lahaul"]):
        return (
            "Himachal Pradesh is stunning! 🏔️ Best visited April-June (snow melts, roads open) "
            "or September-October (post-monsoon clarity). Delhi to Manali is about 14-16 hours by Volvo bus (₹1,200-1,800). "
            "Budget travelers do well at ₹1,500-2,500/day including stay and food.\n\n"
            "To get a detailed plan → use **PariKrama**: go to Dashboard → New Trip and describe your trip. "
            "Our AI will plan everything in under 90 seconds!"
        )
    elif any(w in msg for w in ["goa", "beach", "sea", "ocean"]):
        return (
            "Goa is perfect October-March 🌊 — sunny, sea's calm, nightlife buzzing. "
            "North Goa (Anjuna, Vagator) is livelier; South Goa (Palolem, Agonda) is peaceful. "
            "Mumbai to Goa: overnight train (Mandovi Express) is the classic way — ₹400-1,200 depending on class. "
            "Budget: ₹2,000-3,500/day covers stay + food + scooter rental.\n\n"
            "Let PariKrama plan your Goa trip → Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["kerala", "munnar", "allepey", "backwater", "cochin", "kochi"]):
        return (
            "Kerala — God's Own Country! 🌴 Best Oct-March. "
            "Must-dos: Munnar tea gardens, Alleppey houseboat (₹3,000-8,000/night), Kovalam beach. "
            "Trains from major cities are the most comfortable option. "
            "Budget: ₹2,500-4,000/day for a good mid-range experience.\n\n"
            "Try PariKrama for a full Kerala itinerary → Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["rajasthan", "jaipur", "udaipur", "jodhpur", "jaisalmer"]):
        return (
            "Rajasthan is magical October-March! 🏯 "
            "The golden triangle (Jaipur-Agra-Delhi) is iconic for first-timers. "
            "Udaipur is the most romantic city in India, hands down. "
            "Jaisalmer desert camps are unforgettable — budget ₹2,000-5,000/night. "
            "Trains between Rajasthan cities are reliable and scenic.\n\n"
            "Plan your Rajasthan royal tour → PariKrama Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["ladakh", "leh", "pangong", "nubra"]):
        return (
            "Ladakh is a dream destination! ❄️ Only accessible June-September (roads open). "
            "Inner Line Permit (ILP) needed for Pangong, Nubra, Tso Moriri — ₹400-600, get online. "
            "Acclimatize for 2-3 days in Leh before high-altitude treks. "
            "Budget: ₹4,000-7,000/day (permits, stays, local transport). "
            "Fly Delhi→Leh (₹4,000-8,000) or drive Manali-Leh highway (2 days, epic experience).\n\n"
            "Plan your Ladakh adventure → PariKrama Dashboard → New Trip!"
        )
    elif any(w in msg for w in ["meghalaya", "shillong", "dawki", "cherrapunji"]):
        return (
            "Meghalaya is India's hidden gem! 🌿 Best Nov-March (dry season). "
            "Living root bridges at Cherrapunji are UNESCO-worthy. Dawki river is crystal clear. "
            "Shillong is the 'Scotland of India' — cafes, music, cool weather. "
            "Budget: ₹1,500-3,000/day. Fly to Guwahati, then 10hrs by road or 3hrs flight to Shillong."
        )
    elif any(
        w in msg for w in ["plan", "trip", "parikrama", "how", "kaise", "karna", "start", "help"]
    ):
        return (
            "Here's how to use PariKrama to plan your trip in 3 steps 🗺️\n\n"
            "1. **Login** (top right) → **Dashboard** → **New Trip**\n"
            '2. Just describe your trip naturally: *"5 days Manali from Delhi, ₹15,000, 2 people"*\n'
            "3. Our AI agents will research destinations, find hotels & transport, optimize budget, "
            "and create a day-by-day itinerary — all in 60-90 seconds!\n\n"
            "You can then review, approve, and download your plan as PDF. "
            "No need to fill long forms — just talk to the planner!"
        )
    elif any(
        w in msg
        for w in ["budget", "cost", "price", "kitna", "cheap", "affordable", "₹", "rs", "rupee"]
    ):
        return (
            "Budget planning really depends on destination and style 💰 Rough India travel ranges:\n\n"
            "• **Ultra Budget** (hostels + local food): ₹800-1,500/day\n"
            "• **Mid-range** (decent hotels + restaurants): ₹2,500-5,000/day\n"
            "• **Comfortable** (3-star hotels + AC travel): ₹5,000-10,000/day\n"
            "• **Premium** (5-star + flights): ₹15,000+/day\n\n"
            "PariKrama will calculate the exact budget breakdown for your specific trip. "
            "Go to Dashboard → New Trip and mention your budget — it'll optimize everything for you!"
        )
    elif any(w in msg for w in ["food", "khana", "eat", "restaurant", "dhaba", "cuisine"]):
        return (
            "Indian food varies wildly by region — here's a quick guide 🍛\n\n"
            "• **North India**: Paratha, chole bhature, butter chicken, dal makhani\n"
            "• **Rajasthan**: Dal baati churma, laal maas, kachori\n"
            "• **South India**: Dosa, idli sambar, appam, fish curry\n"
            "• **Goa**: Vindaloo, xacuti, prawn balchao, bebinca\n"
            "• **Kerala**: Appam + stew, malabar biryani, fish moilee\n"
            "• **Bengal**: Rasgulla, mishti doi, kathi rolls\n\n"
            "Pro tip: Dhabas (roadside eateries) serve the most authentic food at half the restaurant price!"
        )
    elif any(w in msg for w in ["weather", "mausam", "rain", "snow", "temperature"]):
        return (
            "Indian weather varies a lot by season and region 🌤️\n\n"
            "• **Oct-Mar**: Best for most of India (cool, dry)\n"
            "• **Apr-Jun**: Hill stations are pleasant, plains are scorching\n"
            "• **Jul-Sep**: Monsoon — Kerala & Meghalaya are beautiful, but travel is tricky\n\n"
            "Check the specific destination's weather before you go. "
            "PariKrama's Research Agent fetches real-time weather for your trip!"
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
    as primary and Groq as fallback. Integrates web search for real-time
    information (weather, prices, events). Falls back to smart offline KB
    if no LLM provider is configured.
    """
    searched_web = False

    try:
        from parikrama.config import settings
        from parikrama.llm.router import LLMRouter

        llm = LLMRouter.from_settings(settings)

        # ── Step 1: Detect if web search is needed ────────────────────
        web_context = ""
        if _needs_web_search(body.message):
            destination = _extract_destination(body.message)
            if destination:
                try:
                    from parikrama.agents.tools.web_search import search_web

                    web_context = await search_web(destination, max_results=5)
                    if web_context:
                        searched_web = True
                        logger.info(
                            "krama_web_search_used",
                            layer="CHATBOT",
                            destination=destination,
                            context_len=len(web_context),
                        )
                except Exception as exc:
                    logger.warning(
                        "krama_web_search_failed",
                        layer="CHATBOT",
                        error=str(exc)[:100],
                    )

        # ── Step 2: Build prompt with history + web context ───────────
        prompt_parts = []

        if web_context:
            prompt_parts.append(
                f"[Live web search results for {destination or 'this topic'}]:\n"
                f"{web_context[:2000]}\n\n"
                f"Use this information to give current, accurate advice. "
                f"Cite specific details from the search when relevant."
            )

        if body.history:
            history_text = "\n".join(
                f"{'User' if h.get('role') == 'user' else 'Krama'}: {h.get('content', '')}"
                for h in body.history[-6:]
            )
            prompt_parts.append(f"Recent conversation:\n{history_text}")

        prompt_parts.append(f"User: {body.message}")
        prompt = "\n\n".join(prompt_parts)

        # ── Step 3: Call LLM ─────────────────────────────────────────
        response = await llm.generate(
            prompt=prompt,
            system=KRAMA_SYSTEM_PROMPT,
            temperature=0.72,
        )

        logger.info(
            "krama_chat_response",
            layer="CHATBOT",
            provider=response.provider,
            latency_ms=response.latency_ms,
            msg_len=len(body.message),
            searched_web=searched_web,
        )

        return ChatResponse(
            response=response.content,
            provider=response.provider,
            searched_web=searched_web,
        )

    except Exception as exc:
        err_str = str(exc)
        logger.warning(
            "krama_chat_fallback",
            layer="CHATBOT",
            error=err_str[:200],
            hint="LLM provider not available — using offline KB response",
        )
        return ChatResponse(
            response=_smart_offline_response(body.message),
            provider="offline_kb",
            searched_web=False,
        )
