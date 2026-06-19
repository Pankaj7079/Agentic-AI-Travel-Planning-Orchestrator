"""Central router that collects all versioned API routes."""

from fastapi import APIRouter

from parikrama.api.v1 import (
    agents,
    approvals,
    auth,
    chat,
    documents,
    health,
    notifications,
    rag,
    trip_planning,
    trips,
    users,
    voice,
)

api_router = APIRouter()

# v1 routes
api_router.include_router(health.router, prefix="/v1")
api_router.include_router(auth.router, prefix="/v1")
api_router.include_router(trips.router, prefix="/v1")
api_router.include_router(users.router, prefix="/v1")

# Phase 2 — RAG pipeline
api_router.include_router(documents.router, prefix="/v1")
api_router.include_router(rag.router, prefix="/v1")

# Phase 3 — LLM Agents
api_router.include_router(agents.router, prefix="/v1")

# Phase 4 — Multi-agent trip planning pipeline
api_router.include_router(trip_planning.router, prefix="/v1")

# Phase 5 — HITL + Notifications
api_router.include_router(approvals.router, prefix="/v1")
api_router.include_router(notifications.router, prefix="/v1")

# Phase 6 — Voice Pipeline
api_router.include_router(voice.router, prefix="/v1")

# Phase 7 — Krama AI Chatbot Assistant
api_router.include_router(chat.router, prefix="/v1")

