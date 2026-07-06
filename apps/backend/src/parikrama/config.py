"""
Centralized configuration loaded from environment variables.

Uses pydantic-settings for validation — if a required var is missing,
the app fails fast at startup instead of crashing randomly later.
"""

import json
from pathlib import Path


def _find_env_file() -> list[str]:
    """Search for .env in all parent directories up to the filesystem root."""
    candidates = []
    # Walk up from this file's location to find all .env files
    current = Path(__file__).resolve().parent
    while True:
        env_path = current / ".env"
        if env_path.exists():
            candidates.append(str(env_path))
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent
    # Also check cwd as a final fallback
    cwd_env = Path(".env").resolve()
    if cwd_env.exists() and str(cwd_env) not in candidates:
        candidates.append(str(cwd_env))
    # Return in order: closest .env first (most specific wins in pydantic-settings)
    return candidates or [".env"]


from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # -- App --
    APP_NAME: str = "PariKrama"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    SECRET_KEY: str = "change-this-in-production"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # -- Database --
    DATABASE_URL: str = "postgresql+asyncpg://parikrama:parikrama_dev_2024@127.0.0.1:5432/parikrama"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # -- Redis --
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600

    # -- MinIO --
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_SECURE: bool = False

    # -- Auth --
    JWT_SECRET_KEY: str = "change-this-jwt-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -- Google OAuth --
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # -- LLM --
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_SECONDS: int = 60
    GROQ_API_KEY: str = ""
    GROQ_PRIMARY_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_SECONDARY_MODEL: str = "llama3-8b-8192"
    GROQ_TIMEOUT_SECONDS: int = 30
    LLM_FALLBACK_LATENCY_THRESHOLD_MS: int = 45000
    LLM_FALLBACK_ERROR_THRESHOLD: int = 3
    LLM_FALLBACK_ERROR_WINDOW_SECONDS: int = 60
    LLM_HEALTH_CHECK_INTERVAL_SECONDS: int = 30

    # -- Web Search --
    TAVILY_API_KEY: str = ""

    # -- Embeddings --
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # -- LiveKit --
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "secret"

    # -- Voice Pipeline (Phase 6) --
    WHISPER_MODEL_SIZE: str = "base"  # tiny | base | small | medium
    TTS_ENGINE: str = "coqui"  # coqui | elevenlabs
    ELEVENLABS_API_KEY: str = ""  # optional — premium TTS
    ELEVENLABS_VOICE_ID: str = "Rachel"  # ElevenLabs voice selection
    VAD_THRESHOLD: float = 0.5  # speech detection sensitivity (0-1)

    # -- Phase 4: Agent Tools --
    OPENWEATHERMAP_API_KEY: str = ""  # Free tier: 1,000 calls/day
    GOOGLE_PLACES_API_KEY: str = ""  # Optional: enhances place search

    # -- Notifications --
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@parikrama.dev"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM_EMAIL: str = "noreply@parikrama.dev"

    # -- Monitoring --
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "parikrama-dev"
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v


settings = Settings()  # type: ignore[call-arg]

# Log loaded LLM config at startup for debugging.
# Use structlog (not stdlib logging) so keyword args work correctly.
import structlog

_startup_log = structlog.get_logger("parikrama.config")
_startup_log.info(
    "llm_config_loaded",
    latency_threshold_ms=settings.LLM_FALLBACK_LATENCY_THRESHOLD_MS,
    error_threshold=settings.LLM_FALLBACK_ERROR_THRESHOLD,
    gemini_model=settings.GEMINI_MODEL,
)
