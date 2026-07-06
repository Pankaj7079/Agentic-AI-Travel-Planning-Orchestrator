"""
PariKrama — FastAPI application factory.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from parikrama.api.router import api_router
from parikrama.config import settings
from parikrama.core.exceptions import register_exception_handlers
from parikrama.core.logger import setup_logging
from parikrama.core.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from parikrama.db.session import engine

logger = structlog.get_logger()

ALEMBIC_DIR = Path(__file__).resolve().parent.parent.parent


async def _check_and_recover_db() -> None:
    """Check if core tables exist; if not, auto-run alembic migration."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'users'")
            )
            if result.scalar():
                return
    except Exception:
        return

    logger.warning("database_tables_missing", msg="Auto-recovering database tables...")

    def _run_alembic():
        import alembic.command
        import alembic.config

        cfg = alembic.config.Config(str(ALEMBIC_DIR / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        alembic.command.stamp(cfg, "base")
        alembic.command.upgrade(cfg, "head")

    try:
        await asyncio.to_thread(_run_alembic)
        logger.info("database_tables_recovered", msg="All tables recreated successfully")
    except Exception as e:
        logger.error("database_recovery_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup and shutdown lifecycle hooks."""
    setup_logging()
    logger.info("starting_parikrama", env=settings.APP_ENV, version="0.1.0")

    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            environment=settings.APP_ENV,
        )

    await _check_and_recover_db()

    yield

    await engine.dispose()
    logger.info("parikrama_shutdown_complete")


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title="PariKrama API",
        description="Agentic AI Travel Planning Orchestrator",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    @app.get("/health")
    def health_check():
        """Simple health check endpoint."""
        return {"status": "ok", "version": "0.1.0", "service": "parikrama"}

    @app.get("/metrics")
    def metrics():
        """Prometheus metrics endpoint."""
        if PROMETHEUS_AVAILABLE:
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        return Response(content="# prometheus_client not available\n", media_type="text/plain")

    # Phase 5 — WebSocket for real-time agent updates
    from parikrama.api.websocket.routes import router as ws_router

    app.include_router(ws_router)

    return app


app = create_app()
