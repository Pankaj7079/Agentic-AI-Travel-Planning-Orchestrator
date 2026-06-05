"""Central router that collects all versioned API routes."""

from fastapi import APIRouter

from parikrama.api.v1 import auth, documents, health, rag, trips, users

api_router = APIRouter()

# v1 routes
api_router.include_router(health.router, prefix="/v1")
api_router.include_router(auth.router, prefix="/v1")
api_router.include_router(trips.router, prefix="/v1")
api_router.include_router(users.router, prefix="/v1")

# Phase 2 — RAG pipeline
api_router.include_router(documents.router, prefix="/v1")
api_router.include_router(rag.router, prefix="/v1")

# Phase 3+ routes added here:
# api_router.include_router(approvals.router, prefix="/v1")
