"""
Custom exception hierarchy for clean error handling.
"""

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse


class PariKramaError(Exception):
    """Base exception for all application errors."""

    status_code: int = 500
    detail: str = "An unexpected error occurred"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class NotFoundError(PariKramaError):
    status_code = 404
    detail = "Resource not found"


class ConflictError(PariKramaError):
    status_code = 409
    detail = "Resource already exists"


class AuthenticationError(PariKramaError):
    status_code = 401
    detail = "Authentication failed"


class ForbiddenError(PariKramaError):
    status_code = 403
    detail = "Insufficient permissions"


class ValidationError(PariKramaError):
    status_code = 422
    detail = "Validation error"


class RateLimitError(PariKramaError):
    status_code = 429
    detail = "Rate limit exceeded"


class LLMError(PariKramaError):
    status_code = 502
    detail = "LLM service unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI app."""

    @app.exception_handler(PariKramaError)
    async def handle_parikrama_error(request: Request, exc: PariKramaError):
        return ORJSONResponse(
            status_code=exc.status_code,
            content={
                "error": type(exc).__name__,
                "detail": exc.detail,
                "path": str(request.url.path),
            },
        )
