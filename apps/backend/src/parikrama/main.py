"""
PariKrama — FastAPI application factory.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from parikrama.api.router import api_router
from parikrama.config import settings
from parikrama.core.exceptions import register_exception_handlers
from parikrama.core.logger import setup_logging
from parikrama.core.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from parikrama.db.session import engine

logger = structlog.get_logger()


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
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    # Phase 5 — WebSocket for real-time agent updates
    from parikrama.api.websocket.routes import router as ws_router

    app.include_router(ws_router)

    return app


app = create_app()
