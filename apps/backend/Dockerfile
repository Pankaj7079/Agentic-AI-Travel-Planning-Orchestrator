FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml

RUN uv sync --frozen --no-dev --package parikrama-backend

COPY packages/common/src packages/common/src
COPY apps/backend/src apps/backend/src
COPY apps/backend/alembic.ini apps/backend/alembic.ini
COPY apps/backend/alembic apps/backend/alembic

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "parikrama.main:app", "--host", "0.0.0.0", "--port", "8000"]
