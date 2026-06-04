"""Central router that collects all versioned API routes."""

from fastapi import APIRouter

from parikrama.api.v1 import health

api_router = APIRouter()

# v1 routes
api_router.include_router(health.router, prefix="/v1")

# future phase routes will be added here:
# api_router.include_router(auth.router, prefix="/v1")
# api_router.include_router(users.router, prefix="/v1")
# api_router.include_router(trips.router, prefix="/v1")
# api_router.include_router(documents.router, prefix="/v1")
