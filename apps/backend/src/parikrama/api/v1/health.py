"""
Health check endpoints for load balancers and monitoring.
"""

import redis.asyncio as redis_client
import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import ORJSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.config import settings
from parikrama.db.session import get_db

logger = structlog.get_logger()
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Liveness probe."""
    return {"status": "healthy", "service": "parikrama-backend", "version": "0.1.0"}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe — checks DB and Redis."""
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "connected"
    except Exception as e:
        logger.error("postgres_health_failed", error=str(e))
        checks["postgres"] = "disconnected"

    try:
        r = redis_client.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "connected"
    except Exception as e:
        logger.error("redis_health_failed", error=str(e))
        checks["redis"] = "disconnected"

    all_healthy = all(v == "connected" for v in checks.values())
    return ORJSONResponse(
        status_code=200 if all_healthy else 503,
        content={"status": "ready" if all_healthy else "degraded", "checks": checks},
    )
