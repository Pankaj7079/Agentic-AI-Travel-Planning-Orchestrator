"""
Health check endpoints for load balancers and monitoring.

/health  -> basic liveness (is the process running?)
/ready   -> readiness (can we serve traffic? DB + Redis connected?)
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
    """Liveness probe — returns 200 if the server is running."""
    return {"status": "healthy", "service": "parikrama-backend", "version": "0.1.0"}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe — verifies database and Redis connectivity."""
    checks: dict[str, str] = {}

    # postgres check
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "connected"
    except Exception as e:
        logger.error("postgres_health_failed", error=str(e))
        checks["postgres"] = "disconnected"

    # redis check
    try:
        r = redis_client.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "connected"
    except Exception as e:
        logger.error("redis_health_failed", error=str(e))
        checks["redis"] = "disconnected"

    all_healthy = all(v == "connected" for v in checks.values())
    status_code = 200 if all_healthy else 503

    return ORJSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_healthy else "degraded",
            "checks": checks,
        },
    )
