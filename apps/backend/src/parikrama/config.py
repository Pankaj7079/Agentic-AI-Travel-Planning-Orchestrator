"""
Centralized configuration loaded from environment variables.

Uses pydantic-settings for validation — if a required var is missing,
the app fails fast at startup instead of crashing randomly later.
"""

import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
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
    DATABASE_URL: str = "postgresql+asyncpg://parikrama:parikrama_dev_2024@localhost:5432/parikrama"
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

    # -- OAuth Google --
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # -- LLM: Gemini (primary) --
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_TIMEOUT_SECONDS: int = 30

    # -- LLM: Groq (fallback) --
    GROQ_API_KEY: str = ""
    GROQ_PRIMARY_MODEL: str = "llama-3.1-70b-versatile"
    GROQ_SECONDARY_MODEL: str = "mixtral-8x7b-32768"
    GROQ_TIMEOUT_SECONDS: int = 15

    # -- LLM Router thresholds --
    LLM_FALLBACK_LATENCY_THRESHOLD_MS: int = 10000
    LLM_FALLBACK_ERROR_THRESHOLD: int = 3
    LLM_FALLBACK_ERROR_WINDOW_SECONDS: int = 60
    LLM_HEALTH_CHECK_INTERVAL_SECONDS: int = 30

    # -- Embeddings --
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # -- LiveKit --
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "secret"

    # -- Notifications --
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@parikrama.dev"
    FCM_CREDENTIALS_PATH: str = ""

    # -- Monitoring --
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "parikrama-dev"
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        """Accept comma-separated string or JSON list."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v


# singleton imported everywhere
settings = Settings()  # type: ignore[call-arg]
