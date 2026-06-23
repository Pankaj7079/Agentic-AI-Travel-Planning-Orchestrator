"""
Custom middleware for request tracing and structured logging.

Every HTTP request gets:
  - A unique correlation_id (X-Correlation-ID header)
  - A structured log line with layer="API", method, path, status, duration_ms
  - Error body captured for 4xx/5xx in the errors.log
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("parikrama.core.middleware")


# Paths to skip logging (health/metrics spam)
_SILENT_PATHS = {"/api/v1/health", "/health", "/metrics", "/favicon.ico"}


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inject a correlation ID into every request for tracing across log files."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4())[:8])
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            layer="API",
        )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log every request with method, path, status, duration.

    - Normal requests → INFO level in api_requests.log
    - 4xx client errors → WARNING
    - 5xx server errors → ERROR (also lands in errors.log for fast triage)
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _SILENT_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        status = response.status_code
        log_ctx = dict(
            layer="API",
            method=request.method,
            path=request.url.path,
            status=status,
            duration_ms=duration_ms,
            client=request.client.host if request.client else "unknown",
        )

        if status >= 500:
            logger.error("http_request", **log_ctx,
                         hint="Check errors.log for full traceback")
        elif status >= 400:
            logger.warning("http_request", **log_ctx)
        elif request.method != "OPTIONS":
            # Skip OPTIONS preflight noise from structured logs
            logger.info("http_request", **log_ctx)

        return response
