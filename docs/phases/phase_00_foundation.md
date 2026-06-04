# Phase 0: Foundation & Project Setup

## Overview

Phase 0 establishes the bedrock infrastructure for PariKrama. **Nothing else works until this is rock-solid.** The goal is simple but non-negotiable: any developer clones the repo, runs `docker compose up`, and has a fully functional development environment within 5 minutes — PostgreSQL with pgvector, Redis, MinIO, LiveKit, Prometheus, Grafana, the FastAPI backend, Celery workers, and the Next.js frontend, all wired together.

We use **uv** as the Python package manager (not pip, not poetry) because it's 10-100x faster, has built-in lockfile support, and handles virtual environments seamlessly. The monorepo uses a workspace layout so backend, worker, and MCP server share dependencies without conflicts.

### Why This Phase Matters
- **Eliminates "works on my machine" syndrome** — Docker standardizes everything
- **Enforces code quality from day zero** — pre-commit hooks catch issues before CI
- **CI/CD skeleton means every PR is validated** — no broken code reaches main
- **Proper secret management prevents security incidents** — `.env` patterns established early

---

## Architecture Decisions

### Decision 1: Monorepo vs Polyrepo
| Approach | Pros | Cons |
|----------|------|------|
| **Monorepo (chosen)** | Shared types, atomic changes, single CI | Larger repo size |
| Polyrepo | Independent deployment | Version sync nightmare, contract drift |

**Why Monorepo:** A solo developer or small team benefits enormously from atomic cross-cutting changes. When you update an API contract in the backend, you update the frontend types in the same commit. No version drift.

### Decision 2: uv vs Poetry vs pip-tools
| Tool | Speed | Lockfile | Workspaces | Maturity |
|------|-------|----------|------------|----------|
| **uv (chosen)** | ⚡ 10-100x faster | ✅ Native | ✅ Native | Production-ready |
| Poetry | Slow | ✅ | ❌ Hacky | Mature |
| pip-tools | Medium | ✅ | ❌ | Mature |

**Why uv:** Speed matters when you have CI running on every PR. uv resolves and installs in seconds where poetry takes minutes. Native workspace support means `apps/backend` and `apps/worker` share a single lockfile.

### Decision 3: Docker Compose vs Kubernetes (for dev/staging)
**Why Docker Compose:** K8s is overkill for development and early production. Docker Compose gives us service orchestration, networking, and volume management with a single YAML file. When we outgrow it, we migrate to K8s — the Dockerfiles remain the same.

### Decision 4: Apps Layout
```
apps/backend   → FastAPI main server (API + WebSocket)
apps/frontend  → Next.js 14 application
apps/worker    → Celery workers (async tasks: document processing, notifications)
apps/mcp       → FastMCP server (Phase 8)
```
**Why separate `worker` from `backend`:** Celery workers run long tasks (PDF processing, embedding generation, email sending). Keeping them separate means:
- Workers can scale independently (spin up more worker containers under load)
- A worker crash doesn't take down the API server
- Resource limits are isolated (workers are memory-hungry due to ML models)

---

## Complete Monorepo Folder Structure

```
PariKrama_Agentic-AI-Travel-Planning-Orchestrator/
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                    # Lint + test on every PR
│   │   ├── deploy-staging.yml        # Deploy on merge to main
│   │   └── deploy-production.yml     # Deploy on version tag
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
│
├── apps/
│   ├── backend/                      # FastAPI application
│   │   ├── pyproject.toml            # Backend-specific deps
│   │   ├── Dockerfile
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/            # Migration files
│   │   │       └── .gitkeep
│   │   └── src/
│   │       └── parikrama/
│   │           ├── __init__.py
│   │           ├── main.py           # FastAPI app factory
│   │           ├── config.py         # Pydantic settings
│   │           ├── dependencies.py   # FastAPI dependency injection
│   │           │
│   │           ├── api/              # Route handlers
│   │           │   ├── __init__.py
│   │           │   ├── router.py     # Main router aggregator
│   │           │   ├── v1/
│   │           │   │   ├── __init__.py
│   │           │   │   ├── auth.py
│   │           │   │   ├── users.py
│   │           │   │   ├── trips.py
│   │           │   │   ├── documents.py
│   │           │   │   ├── agents.py
│   │           │   │   ├── voice.py
│   │           │   │   ├── notifications.py
│   │           │   │   ├── admin.py
│   │           │   │   └── health.py
│   │           │   └── websocket/
│   │           │       ├── __init__.py
│   │           │       └── manager.py
│   │           │
│   │           ├── core/             # Business logic
│   │           │   ├── __init__.py
│   │           │   ├── security.py   # JWT, hashing, encryption
│   │           │   ├── rate_limit.py # Rate limiting with slowapi
│   │           │   ├── middleware.py  # CORS, logging, correlation IDs
│   │           │   └── exceptions.py # Custom exception classes
│   │           │
│   │           ├── services/         # Business logic layer
│   │           │   ├── __init__.py
│   │           │   ├── auth_service.py
│   │           │   ├── user_service.py
│   │           │   ├── trip_service.py
│   │           │   ├── document_service.py
│   │           │   ├── notification_service.py
│   │           │   ├── rag_service.py
│   │           │   ├── voice_service.py
│   │           │   └── export_service.py
│   │           │
│   │           ├── agents/           # LangGraph agents
│   │           │   ├── __init__.py
│   │           │   ├── base.py       # Base agent class
│   │           │   ├── orchestrator.py
│   │           │   ├── research.py
│   │           │   ├── booking.py
│   │           │   ├── budget.py
│   │           │   ├── itinerary.py
│   │           │   ├── graph.py      # LangGraph definition
│   │           │   ├── state.py      # Agent state TypedDict
│   │           │   ├── tools/        # Agent tools
│   │           │   │   ├── __init__.py
│   │           │   │   ├── weather.py
│   │           │   │   ├── maps.py
│   │           │   │   ├── hotels.py
│   │           │   │   ├── transport.py
│   │           │   │   └── places.py
│   │           │   └── prompts/      # System prompts
│   │           │       ├── orchestrator.md
│   │           │       ├── research.md
│   │           │       ├── booking.md
│   │           │       ├── budget.md
│   │           │       └── itinerary.md
│   │           │
│   │           ├── llm/              # LLM router + providers
│   │           │   ├── __init__.py
│   │           │   ├── router.py     # LLMRouter with fallback
│   │           │   ├── providers/
│   │           │   │   ├── __init__.py
│   │           │   │   ├── gemini.py
│   │           │   │   └── groq.py
│   │           │   ├── cache.py      # LLM response caching
│   │           │   └── cost_tracker.py
│   │           │
│   │           ├── rag/              # RAG pipeline
│   │           │   ├── __init__.py
│   │           │   ├── embeddings.py # Embedding model wrapper
│   │           │   ├── chunker.py    # Document chunking
│   │           │   ├── retriever.py  # Hybrid search
│   │           │   ├── reranker.py   # Cross-encoder
│   │           │   └── ingestion.py  # Document processing
│   │           │
│   │           ├── voice/            # Voice pipeline
│   │           │   ├── __init__.py
│   │           │   ├── stt.py        # Whisper STT
│   │           │   ├── tts.py        # TTS engine
│   │           │   ├── vad.py        # Voice activity detection
│   │           │   └── pipeline.py   # Orchestration
│   │           │
│   │           ├── models/           # SQLAlchemy models
│   │           │   ├── __init__.py
│   │           │   ├── base.py       # Declarative base + mixins
│   │           │   ├── user.py
│   │           │   ├── trip.py
│   │           │   ├── agent.py
│   │           │   ├── document.py
│   │           │   ├── notification.py
│   │           │   ├── approval.py
│   │           │   └── cost.py
│   │           │
│   │           ├── repositories/     # Data access layer
│   │           │   ├── __init__.py
│   │           │   ├── base.py       # Generic CRUD
│   │           │   ├── user_repo.py
│   │           │   ├── trip_repo.py
│   │           │   ├── document_repo.py
│   │           │   └── notification_repo.py
│   │           │
│   │           ├── schemas/          # Pydantic schemas
│   │           │   ├── __init__.py
│   │           │   ├── auth.py
│   │           │   ├── user.py
│   │           │   ├── trip.py
│   │           │   ├── document.py
│   │           │   ├── notification.py
│   │           │   ├── agent.py
│   │           │   └── common.py     # Pagination, error responses
│   │           │
│   │           └── db/               # Database setup
│   │               ├── __init__.py
│   │               ├── session.py    # Async session factory
│   │               └── init_db.py    # Initial data seeding
│   │
│   ├── frontend/                     # Next.js 14
│   │   ├── package.json
│   │   ├── next.config.js
│   │   ├── tsconfig.json
│   │   ├── tailwind.config.ts
│   │   ├── Dockerfile
│   │   ├── .env.example
│   │   ├── public/
│   │   │   ├── favicon.ico
│   │   │   └── images/
│   │   └── src/
│   │       ├── app/                  # App Router pages
│   │       │   ├── layout.tsx
│   │       │   ├── page.tsx
│   │       │   ├── (auth)/
│   │       │   │   ├── login/page.tsx
│   │       │   │   └── register/page.tsx
│   │       │   ├── (dashboard)/
│   │       │   │   ├── layout.tsx
│   │       │   │   ├── page.tsx
│   │       │   │   ├── trips/
│   │       │   │   │   ├── page.tsx
│   │       │   │   │   ├── [id]/page.tsx
│   │       │   │   │   └── new/page.tsx
│   │       │   │   ├── documents/page.tsx
│   │       │   │   ├── notifications/page.tsx
│   │       │   │   └── settings/page.tsx
│   │       │   └── admin/
│   │       │       ├── layout.tsx
│   │       │       ├── page.tsx
│   │       │       ├── users/page.tsx
│   │       │       └── analytics/page.tsx
│   │       │
│   │       ├── components/
│   │       │   ├── ui/               # Shadcn components
│   │       │   ├── chat/
│   │       │   │   ├── ChatInterface.tsx
│   │       │   │   ├── MessageBubble.tsx
│   │       │   │   ├── VoiceButton.tsx
│   │       │   │   └── ApprovalCard.tsx
│   │       │   ├── trip/
│   │       │   │   ├── ItineraryView.tsx
│   │       │   │   ├── DayCard.tsx
│   │       │   │   └── BudgetBreakdown.tsx
│   │       │   ├── layout/
│   │       │   │   ├── Sidebar.tsx
│   │       │   │   ├── Header.tsx
│   │       │   │   └── NotificationBell.tsx
│   │       │   └── shared/
│   │       │       ├── LoadingSpinner.tsx
│   │       │       └── ErrorBoundary.tsx
│   │       │
│   │       ├── hooks/
│   │       │   ├── useWebSocket.ts
│   │       │   ├── useVoice.ts
│   │       │   ├── useAuth.ts
│   │       │   └── useNotifications.ts
│   │       │
│   │       ├── stores/               # Zustand stores
│   │       │   ├── authStore.ts
│   │       │   ├── tripStore.ts
│   │       │   └── notificationStore.ts
│   │       │
│   │       ├── lib/
│   │       │   ├── api.ts            # Axios/fetch wrapper
│   │       │   ├── socket.ts         # Socket.io client
│   │       │   └── utils.ts
│   │       │
│   │       └── types/
│   │           ├── trip.ts
│   │           ├── user.ts
│   │           └── api.ts
│   │
│   ├── worker/                       # Celery workers
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/
│   │       └── parikrama_worker/
│   │           ├── __init__.py
│   │           ├── celery_app.py     # Celery configuration
│   │           ├── tasks/
│   │           │   ├── __init__.py
│   │           │   ├── document_tasks.py   # PDF processing
│   │           │   ├── embedding_tasks.py  # Embedding generation
│   │           │   ├── email_tasks.py      # Email sending
│   │           │   ├── push_tasks.py       # FCM notifications
│   │           │   └── cleanup_tasks.py    # Scheduled cleanups
│   │           └── config.py
│   │
│   └── mcp/                          # FastMCP server (Phase 8)
│       ├── pyproject.toml
│       ├── Dockerfile
│       └── src/
│           └── parikrama_mcp/
│               ├── __init__.py
│               ├── server.py
│               └── tools/
│                   ├── __init__.py
│                   ├── search.py
│                   ├── trips.py
│                   └── weather.py
│
├── packages/                         # Shared code
│   └── common/
│       ├── pyproject.toml
│       └── src/
│           └── parikrama_common/
│               ├── __init__.py
│               ├── constants.py      # Shared constants
│               ├── enums.py          # Status enums
│               └── utils.py          # Shared utilities
│
├── infra/                            # Infrastructure configs
│   ├── docker/
│   │   ├── docker-compose.yml        # Dev environment
│   │   ├── docker-compose.prod.yml   # Production overrides
│   │   ├── postgres/
│   │   │   └── init.sql              # DB init + pgvector
│   │   ├── prometheus/
│   │   │   └── prometheus.yml
│   │   ├── grafana/
│   │   │   ├── provisioning/
│   │   │   │   ├── dashboards/
│   │   │   │   │   └── parikrama.json
│   │   │   │   └── datasources/
│   │   │   │       └── prometheus.yml
│   │   │   └── dashboards/
│   │   │       └── parikrama-overview.json
│   │   ├── redis/
│   │   │   └── redis.conf
│   │   ├── minio/
│   │   │   └── .gitkeep
│   │   ├── livekit/
│   │   │   └── livekit.yaml
│   │   └── nginx/
│   │       └── nginx.conf            # Reverse proxy (prod)
│   │
│   └── scripts/
│       ├── setup-dev.sh              # Dev environment bootstrap
│       ├── setup-dev.ps1             # Windows PowerShell version
│       ├── seed-db.py                # Database seed data
│       └── generate-keys.py          # Generate API/JWT keys
│
├── docs/                             # Project documentation
│   ├── architecture.md
│   ├── api-reference.md
│   ├── deployment.md
│   ├── development.md
│   └── images/
│       └── architecture-diagram.png
│
├── tests/                            # Test suites
│   ├── conftest.py                   # Shared fixtures
│   ├── backend/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_trips.py
│   │   ├── test_agents.py
│   │   ├── test_rag.py
│   │   └── test_llm_router.py
│   ├── worker/
│   │   ├── conftest.py
│   │   └── test_tasks.py
│   └── e2e/
│       └── test_trip_flow.py
│
├── data/                             # Local data (gitignored)
│   ├── knowledge_base/              # Travel docs for RAG
│   │   └── .gitkeep
│   └── models/                       # Local ML models
│       └── .gitkeep
│
├── .env.example                      # Template for all env vars
├── .pre-commit-config.yaml
├── pyproject.toml                    # Root workspace config (uv)
├── uv.lock                           # Locked dependencies
├── .python-version                   # Python version (3.12)
├── .gitignore
├── LICENSE
├── Makefile                          # Developer commands
└── README.md
```

---

## Docker Compose — All Services

```yaml
# infra/docker/docker-compose.yml
# PariKrama Development Environment
# Usage: docker compose -f infra/docker/docker-compose.yml up -d

name: parikrama

services:
  # ── PostgreSQL 16 with pgvector ──────────────────────────────────────
  postgres:
    image: pgvector/pgvector:pg16
    container_name: parikrama-postgres
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-parikrama}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-parikrama_dev_2024}
      POSTGRES_DB: ${POSTGRES_DB:-parikrama}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U parikrama"]
      interval: 5s
      timeout: 5s
      retries: 5

  # ── Redis 7 (cache + Celery broker) ─────────────────────────────────
  redis:
    image: redis:7-alpine
    container_name: parikrama-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: redis-server /usr/local/etc/redis/redis.conf
    volumes:
      - redis_data:/data
      - ./redis/redis.conf:/usr/local/etc/redis/redis.conf
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  # ── MinIO (S3-compatible object storage) ────────────────────────────
  minio:
    image: minio/minio:latest
    container_name: parikrama-minio
    restart: unless-stopped
    ports:
      - "9000:9000"   # API
      - "9001:9001"   # Console
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin123}
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── MinIO bucket initializer (one-shot) ──────────────────────────────
  minio-init:
    image: minio/mc:latest
    container_name: parikrama-minio-init
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set parikrama http://minio:9000 minioadmin minioadmin123;
      mc mb --ignore-existing parikrama/documents;
      mc mb --ignore-existing parikrama/exports;
      mc mb --ignore-existing parikrama/voice-recordings;
      mc mb --ignore-existing parikrama/backups;
      echo 'Buckets created successfully';
      exit 0;
      "

  # ── LiveKit Server (WebRTC for voice) ───────────────────────────────
  livekit:
    image: livekit/livekit-server:latest
    container_name: parikrama-livekit
    restart: unless-stopped
    ports:
      - "7880:7880"   # HTTP
      - "7881:7881"   # WebSocket
      - "7882:7882/udp"  # WebRTC UDP
    volumes:
      - ./livekit/livekit.yaml:/etc/livekit.yaml
    command: --config /etc/livekit.yaml --dev

  # ── Prometheus (metrics collection) ─────────────────────────────────
  prometheus:
    image: prom/prometheus:latest
    container_name: parikrama-prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'

  # ── Grafana (metrics visualization) ─────────────────────────────────
  grafana:
    image: grafana/grafana:latest
    container_name: parikrama-grafana
    restart: unless-stopped
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_USER:-admin}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
    depends_on:
      - prometheus

  # ── FastAPI Backend ─────────────────────────────────────────────────
  backend:
    build:
      context: ../../
      dockerfile: apps/backend/Dockerfile
    container_name: parikrama-backend
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - ../../.env
    environment:
      - DATABASE_URL=postgresql+asyncpg://parikrama:parikrama_dev_2024@postgres:5432/parikrama
      - REDIS_URL=redis://redis:6379/0
      - MINIO_ENDPOINT=minio:9000
    volumes:
      - ../../apps/backend/src:/app/src   # Hot reload in dev
      - ../../data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_healthy
    command: >
      uv run uvicorn parikrama.main:app
      --host 0.0.0.0 --port 8000 --reload
      --log-level info

  # ── Celery Worker ───────────────────────────────────────────────────
  worker:
    build:
      context: ../../
      dockerfile: apps/worker/Dockerfile
    container_name: parikrama-worker
    restart: unless-stopped
    env_file:
      - ../../.env
    environment:
      - DATABASE_URL=postgresql+asyncpg://parikrama:parikrama_dev_2024@postgres:5432/parikrama
      - REDIS_URL=redis://redis:6379/0
      - MINIO_ENDPOINT=minio:9000
    volumes:
      - ../../apps/worker/src:/app/src
      - ../../data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      uv run celery -A parikrama_worker.celery_app worker
      --loglevel=info --concurrency=2

  # ── Celery Beat (scheduled tasks) ───────────────────────────────────
  celery-beat:
    build:
      context: ../../
      dockerfile: apps/worker/Dockerfile
    container_name: parikrama-celery-beat
    restart: unless-stopped
    env_file:
      - ../../.env
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    command: >
      uv run celery -A parikrama_worker.celery_app beat
      --loglevel=info

  # ── Next.js Frontend ───────────────────────────────────────────────
  frontend:
    build:
      context: ../../apps/frontend
      dockerfile: Dockerfile
      target: development
    container_name: parikrama-frontend
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
      - NEXT_PUBLIC_WS_URL=ws://localhost:8000
      - NEXT_PUBLIC_LIVEKIT_URL=ws://localhost:7880
    volumes:
      - ../../apps/frontend/src:/app/src  # Hot reload in dev
    depends_on:
      - backend

volumes:
  postgres_data:
  redis_data:
  minio_data:
  prometheus_data:
  grafana_data:
```

---

## Database Initialization Script

```sql
-- infra/docker/postgres/init.sql
-- Initialize PariKrama database with required extensions

-- pgvector for embedding storage (RAG)
CREATE EXTENSION IF NOT EXISTS vector;

-- pg_trgm for fuzzy text search (BM25-like)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- uuid-ossp for generating UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify extensions loaded correctly
DO $$
BEGIN
  RAISE NOTICE 'pgvector version: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
  RAISE NOTICE 'All extensions loaded for PariKrama';
END $$;
```

---

## Root pyproject.toml (uv Workspace)

```toml
# pyproject.toml (root) — uv workspace configuration
[project]
name = "parikrama"
version = "0.1.0"
description = "Agentic AI Travel Planning Orchestrator"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "MIT"}
authors = [
    {name = "Pankaj", email = "pankaj@parikrama.dev"},
]

# root has no direct deps — each app manages its own
dependencies = []

[tool.uv]
# define the workspace members
managed = true

[tool.uv.workspace]
members = [
    "apps/backend",
    "apps/worker",
    "apps/mcp",
    "packages/common",
]

[tool.uv.sources]
# local packages resolve from workspace
parikrama-common = { workspace = true }

# ── Shared dev tools ──────────────────────────────────────────────────
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "httpx>=0.27",          # async test client for FastAPI
    "factory-boy>=3.3",     # test fixtures
    "mypy>=1.10",
    "ruff>=0.5",            # linter + formatter (replaces black + isort)
    "pre-commit>=3.7",
]

# ── Ruff config (replaces black, isort, flake8) ─────────────────────
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["apps/*/src", "packages/*/src"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
    "SIM", # flake8-simplify
    "TCH", # type-checking imports
    "RUF", # ruff-specific rules
]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.lint.isort]
known-first-party = ["parikrama", "parikrama_worker", "parikrama_mcp", "parikrama_common"]

# ── Mypy config ──────────────────────────────────────────────────────
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
plugins = ["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

# ── Pytest config ────────────────────────────────────────────────────
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short --cov=apps --cov-report=term-missing"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests requiring external services",
]
```

---

## Backend pyproject.toml

```toml
# apps/backend/pyproject.toml
[project]
name = "parikrama-backend"
version = "0.1.0"
description = "PariKrama FastAPI backend"
requires-python = ">=3.12"

dependencies = [
    # -- Web Framework --
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "python-multipart>=0.0.9",     # file uploads

    # -- Database --
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",               # async postgres driver
    "alembic>=1.13",
    "pgvector>=0.3",               # vector extension support

    # -- Validation & Config --
    "pydantic>=2.7",
    "pydantic-settings>=2.3",

    # -- Auth & Security --
    "python-jose[cryptography]>=3.3",  # JWT
    "passlib[bcrypt]>=1.7",            # password hashing
    "slowapi>=0.1.9",                  # rate limiting

    # -- LLM & Agents --
    "langchain>=0.2",
    "langchain-google-genai>=1.0",     # Gemini provider
    "langchain-groq>=0.1",            # Groq provider
    "langgraph>=0.1",
    "langsmith>=0.1",                  # tracing

    # -- RAG --
    "sentence-transformers>=3.0",      # local embeddings
    "rank-bm25>=0.2",                  # BM25 keyword search

    # -- Voice --
    "openai-whisper>=20231117",        # STT
    "livekit>=0.11",                   # WebRTC
    "silero-vad>=5.0",                 # Voice activity detection

    # -- Storage & Cache --
    "redis>=5.0",
    "minio>=7.2",

    # -- Notifications --
    "resend>=2.0",                     # email
    "firebase-admin>=6.5",            # FCM push
    "python-socketio>=5.11",          # WebSocket

    # -- Document Processing --
    "pymupdf>=1.24",                  # PDF extraction
    "reportlab>=4.2",                 # PDF generation

    # -- Monitoring --
    "prometheus-client>=0.20",
    "sentry-sdk[fastapi]>=2.5",
    "structlog>=24.1",

    # -- Shared --
    "parikrama-common",

    # -- Utilities --
    "httpx>=0.27",                    # async HTTP client
    "tenacity>=8.3",                  # retry logic
    "orjson>=3.10",                   # fast JSON
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parikrama"]
```

---

## Worker pyproject.toml

```toml
# apps/worker/pyproject.toml
[project]
name = "parikrama-worker"
version = "0.1.0"
description = "PariKrama Celery workers"
requires-python = ">=3.12"

dependencies = [
    "celery[redis]>=5.4",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "pgvector>=0.3",
    "sentence-transformers>=3.0",
    "pymupdf>=1.24",
    "reportlab>=4.2",
    "resend>=2.0",
    "firebase-admin>=6.5",
    "minio>=7.2",
    "redis>=5.0",
    "structlog>=24.1",
    "pydantic-settings>=2.3",
    "parikrama-common",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parikrama_worker"]
```

---

## Common Package pyproject.toml

```toml
# packages/common/pyproject.toml
[project]
name = "parikrama-common"
version = "0.1.0"
description = "Shared constants, enums, and utilities"
requires-python = ">=3.12"

dependencies = [
    "pydantic>=2.7",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parikrama_common"]
```

---

## Environment Variables (.env.example)

```bash
# ══════════════════════════════════════════════════════════════════════
# PariKrama Environment Configuration
# Copy this file to .env and fill in actual values
# NEVER commit .env to git
# ══════════════════════════════════════════════════════════════════════

# ── Application ──────────────────────────────────────────────────────
APP_NAME=PariKrama
APP_ENV=development          # development | staging | production
DEBUG=true
LOG_LEVEL=DEBUG              # DEBUG | INFO | WARNING | ERROR
SECRET_KEY=change-this-to-a-random-64-char-string-in-production
CORS_ORIGINS=["http://localhost:3000"]

# ── Database (PostgreSQL + pgvector) ─────────────────────────────────
POSTGRES_USER=parikrama
POSTGRES_PASSWORD=parikrama_dev_2024
POSTGRES_DB=parikrama
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://parikrama:parikrama_dev_2024@localhost:5432/parikrama

# ── Redis ────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_TTL=3600         # default cache TTL in seconds

# ── MinIO (S3-compatible storage) ────────────────────────────────────
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_SECURE=false           # true in production with TLS
MINIO_BUCKET_DOCUMENTS=documents
MINIO_BUCKET_EXPORTS=exports
MINIO_BUCKET_VOICE=voice-recordings

# ── LLM — Primary (Gemini 2.5 Flash Lite) ───────────────────────────
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_MAX_RETRIES=3
GEMINI_TIMEOUT_SECONDS=30

# ── LLM — Fallback (Groq) ───────────────────────────────────────────
GROQ_API_KEY=your-groq-api-key-here
GROQ_PRIMARY_MODEL=llama-3.1-70b-versatile
GROQ_SECONDARY_MODEL=mixtral-8x7b-32768
GROQ_TIMEOUT_SECONDS=15

# ── LLM Router Config ───────────────────────────────────────────────
LLM_FALLBACK_LATENCY_THRESHOLD_MS=10000    # switch to Groq if > 10s
LLM_FALLBACK_ERROR_THRESHOLD=3             # switch after 3 errors
LLM_FALLBACK_ERROR_WINDOW_SECONDS=60       # within 60s window
LLM_HEALTH_CHECK_INTERVAL_SECONDS=30       # check primary health

# ── Embeddings ───────────────────────────────────────────────────────
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
EMBEDDING_BATCH_SIZE=32

# ── Authentication ───────────────────────────────────────────────────
JWT_SECRET_KEY=change-this-jwt-secret-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ── OAuth (Google) ───────────────────────────────────────────────────
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# ── LiveKit (Voice/WebRTC) ───────────────────────────────────────────
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# ── Notifications — Email (Resend) ──────────────────────────────────
RESEND_API_KEY=your-resend-api-key-here
RESEND_FROM_EMAIL=noreply@parikrama.dev

# ── Notifications — Push (Firebase Cloud Messaging) ─────────────────
FCM_CREDENTIALS_PATH=./firebase-credentials.json

# ── Monitoring — LangSmith ──────────────────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-langsmith-api-key
LANGCHAIN_PROJECT=parikrama-dev

# ── Monitoring — Sentry ─────────────────────────────────────────────
SENTRY_DSN=your-sentry-dsn-here
SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% of transactions in prod
SENTRY_ENVIRONMENT=development

# ── Monitoring — Prometheus ──────────────────────────────────────────
PROMETHEUS_METRICS_PORT=8001

# ── External APIs ───────────────────────────────────────────────────
OPENWEATHERMAP_API_KEY=your-openweathermap-key
GOOGLE_MAPS_API_KEY=your-google-maps-key
GOOGLE_PLACES_API_KEY=your-google-places-key

# ── Grafana ──────────────────────────────────────────────────────────
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin
```

---

## Infrastructure Configuration Files

### Redis Configuration

```conf
# infra/docker/redis/redis.conf
# PariKrama Redis configuration

# persistence - RDB snapshots
save 900 1
save 300 10
save 60 10000

# memory management
maxmemory 256mb
maxmemory-policy allkeys-lru

# logging
loglevel notice

# security - bind to all interfaces in Docker (network isolation via compose)
bind 0.0.0.0
protected-mode no
```

### LiveKit Configuration

```yaml
# infra/docker/livekit/livekit.yaml
# PariKrama LiveKit development config

port: 7880
rtc:
  port_range_start: 50000
  port_range_end: 60000
  use_external_ip: false
  tcp_port: 7881
  udp_port: 7882

keys:
  devkey: secret

logging:
  level: info

room:
  empty_timeout: 300     # 5 min auto-close empty rooms
  max_participants: 10
```

### Prometheus Configuration

```yaml
# infra/docker/prometheus/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'parikrama-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

### Grafana Datasource Provisioning

```yaml
# infra/docker/grafana/provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

---

## Backend Dockerfile

```dockerfile
# apps/backend/Dockerfile
FROM python:3.12-slim AS base

# prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# install system deps needed by some Python packages (psycopg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# copy workspace config first (cache deps layer)
COPY pyproject.toml uv.lock ./
COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml

# install deps (cached unless pyproject.toml or lockfile changes)
RUN uv sync --frozen --no-dev --package parikrama-backend

# copy source code
COPY packages/common/src packages/common/src
COPY apps/backend/src apps/backend/src
COPY apps/backend/alembic.ini apps/backend/alembic.ini
COPY apps/backend/alembic apps/backend/alembic

EXPOSE 8000

# default command — overridden in docker-compose for dev
CMD ["uv", "run", "uvicorn", "parikrama.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Worker Dockerfile

```dockerfile
# apps/worker/Dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN uv sync --frozen --no-dev --package parikrama-worker

COPY packages/common/src packages/common/src
COPY apps/worker/src apps/worker/src

CMD ["uv", "run", "celery", "-A", "parikrama_worker.celery_app", "worker", "--loglevel=info"]
```

## Frontend Dockerfile

```dockerfile
# apps/frontend/Dockerfile

# ── Development stage ────────────────────────────────────────────────
FROM node:20-alpine AS development
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ── Production build ────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# ── Production runtime ──────────────────────────────────────────────
FROM node:20-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

---

## Pre-commit Configuration

```yaml
# .pre-commit-config.yaml
repos:
  # ── Ruff (replaces black + isort + flake8) ─────────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff          # linter
        args: [--fix]
      - id: ruff-format   # formatter

  # ── MyPy (type checking) ──────────────────────────────────────────
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic
          - sqlalchemy[mypy]
        args: [--ignore-missing-imports]

  # ── General file hygiene ──────────────────────────────────────────
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: check-merge-conflict
      - id: detect-private-key       # prevent secret leaks

  # ── Frontend linting ──────────────────────────────────────────────
  - repo: local
    hooks:
      - id: eslint
        name: eslint
        entry: bash -c 'cd apps/frontend && npx eslint --fix'
        language: system
        files: '^apps/frontend/.*\.(ts|tsx)$'
        pass_filenames: false
```

---

## GitHub Actions CI/CD

### CI Pipeline (runs on every PR)

```yaml
# .github/workflows/ci.yml
name: CI Pipeline

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # ── Python Backend Checks ──────────────────────────────────────────
  backend-lint:
    name: Backend Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --frozen --all-packages

      - name: Ruff lint
        run: uv run ruff check .

      - name: Ruff format check
        run: uv run ruff format --check .

      - name: MyPy type check
        run: uv run mypy apps/backend/src apps/worker/src packages/common/src
        continue-on-error: true  # strict mypy can be noisy early on

  backend-test:
    name: Backend Tests
    runs-on: ubuntu-latest
    needs: backend-lint
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --frozen --all-packages --group dev

      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0
          APP_ENV: testing
          SECRET_KEY: test-secret-key-not-for-production
          JWT_SECRET_KEY: test-jwt-secret-key
        run: uv run pytest tests/ -x --cov --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
        continue-on-error: true

  # ── Frontend Checks ────────────────────────────────────────────────
  frontend-lint:
    name: Frontend Lint & Type Check
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/frontend
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
          cache-dependency-path: apps/frontend/package-lock.json

      - name: Install deps
        run: npm ci

      - name: ESLint
        run: npm run lint

      - name: TypeScript check
        run: npx tsc --noEmit

  frontend-build:
    name: Frontend Build
    runs-on: ubuntu-latest
    needs: frontend-lint
    defaults:
      run:
        working-directory: apps/frontend
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
          cache-dependency-path: apps/frontend/package-lock.json

      - name: Install deps
        run: npm ci

      - name: Build
        run: npm run build

  # ── Docker Build Validation ────────────────────────────────────────
  docker-build:
    name: Docker Build Check
    runs-on: ubuntu-latest
    needs: [backend-test, frontend-build]
    steps:
      - uses: actions/checkout@v4

      - name: Build backend image
        run: docker build -f apps/backend/Dockerfile -t parikrama-backend:test .

      - name: Build worker image
        run: docker build -f apps/worker/Dockerfile -t parikrama-worker:test .
```

### Staging Deployment

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy to Staging

on:
  push:
    branches: [main]

jobs:
  deploy:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Railway
        # Railway CLI or API-based deployment
        run: echo "Railway deployment configured in Phase 10"
        # Placeholder — full implementation in Phase 10
```

### Production Deployment

```yaml
# .github/workflows/deploy-production.yml
name: Deploy to Production

on:
  push:
    tags:
      - 'v*'

jobs:
  deploy:
    name: Deploy to Production
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Verify tag format
        run: |
          if [[ ! "${{ github.ref_name }}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "Invalid tag format. Use semantic versioning: v1.0.0"
            exit 1
          fi

      - name: Deploy to Production
        run: echo "Production deployment configured in Phase 10"
```

---

## Key Implementation Files

### FastAPI Application Factory

```python
# apps/backend/src/parikrama/main.py
"""
PariKrama — FastAPI application factory.

Single entry point that wires up all middleware, routes, and lifecycle events.
Uses factory pattern so tests can create isolated app instances.
"""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from parikrama.config import settings
from parikrama.api.router import api_router
from parikrama.core.middleware import (
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
)
from parikrama.db.session import engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup and shutdown lifecycle hooks."""
    # startup
    logger.info("starting_parikrama", env=settings.APP_ENV)

    # initialize Sentry if DSN is configured
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            environment=settings.APP_ENV,
        )

    yield

    # shutdown — dispose DB connections gracefully
    await engine.dispose()
    logger.info("parikrama_shutdown_complete")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="PariKrama API",
        description="Agentic AI Travel Planning Orchestrator",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # -- CORS --
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Custom Middleware (order matters: outermost first) --
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # -- Routes --
    app.include_router(api_router, prefix="/api")

    return app


# uvicorn uses this directly
app = create_app()
```

### Pydantic Settings

```python
# apps/backend/src/parikrama/config.py
"""
Centralized configuration loaded from environment variables.

Uses pydantic-settings for validation — if a required var is missing,
the app fails fast at startup instead of crashing randomly later.
"""
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
    SECRET_KEY: str
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # -- Database --
    DATABASE_URL: str
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

    # -- LLM: Gemini (primary) --
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_TIMEOUT_SECONDS: int = 30

    # -- LLM: Groq (fallback) --
    GROQ_API_KEY: str = ""
    GROQ_PRIMARY_MODEL: str = "llama-3.1-70b-versatile"
    GROQ_SECONDARY_MODEL: str = "mixtral-8x7b-32768"

    # -- LLM Router --
    LLM_FALLBACK_LATENCY_THRESHOLD_MS: int = 10000
    LLM_FALLBACK_ERROR_THRESHOLD: int = 3
    LLM_FALLBACK_ERROR_WINDOW_SECONDS: int = 60
    LLM_HEALTH_CHECK_INTERVAL_SECONDS: int = 30

    # -- Embeddings --
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # -- Auth --
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -- OAuth Google --
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

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
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v


# singleton — imported everywhere
settings = Settings()  # type: ignore[call-arg]
```

### Correlation ID Middleware

```python
# apps/backend/src/parikrama/core/middleware.py
"""
Custom middleware stack for request tracing and logging.

CorrelationIdMiddleware assigns a unique ID to every request so we can
trace it through backend -> worker -> LLM calls in logs.
"""
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inject a correlation ID into every request for distributed tracing."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # use client-provided ID or generate one
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

        # bind to structlog context so every log in this request has it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        # pass through the request chain
        response = await call_next(request)

        # echo it back so frontend can log it too
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
```

### Shared Constants & Enums

```python
# packages/common/src/parikrama_common/enums.py
"""
Shared enums used across backend, worker, and MCP server.

Single source of truth — if you add a status, add it here.
"""
from enum import StrEnum


class TripStatus(StrEnum):
    """Trip lifecycle states."""
    PENDING = "pending"
    PLANNING = "planning"            # agents are working
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AgentName(StrEnum):
    """Agent identifiers in the orchestration graph."""
    ORCHESTRATOR = "orchestrator"
    RESEARCH = "research"
    BOOKING = "booking"
    BUDGET = "budget"
    ITINERARY = "itinerary"


class AgentRunStatus(StrEnum):
    """Status of individual agent executions."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"      # human-in-the-loop pause


class DocumentStatus(StrEnum):
    """Document processing pipeline states."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    CHUNKED = "chunked"
    EMBEDDED = "embedded"
    FAILED = "failed"


class NotificationType(StrEnum):
    """Notification categories for filtering and routing."""
    TRIP_UPDATE = "trip_update"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_RESULT = "approval_result"
    SYSTEM = "system"
    DOCUMENT_READY = "document_ready"


class ApprovalStatus(StrEnum):
    """Approval request states."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class LLMProvider(StrEnum):
    """LLM provider identifiers for routing and cost tracking."""
    GEMINI = "gemini"
    GROQ_LLAMA = "groq_llama"
    GROQ_MIXTRAL = "groq_mixtral"
```

### Makefile (Developer Commands)

```makefile
# Makefile — Developer convenience commands
# Usage: make <command>

.PHONY: help dev down logs test lint format migrate seed clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker Commands ──────────────────────────────────────────────────
dev: ## Start all services in development mode
	docker compose -f infra/docker/docker-compose.yml up -d --build

down: ## Stop all services
	docker compose -f infra/docker/docker-compose.yml down

logs: ## Tail logs from all services
	docker compose -f infra/docker/docker-compose.yml logs -f

logs-backend: ## Tail backend logs only
	docker compose -f infra/docker/docker-compose.yml logs -f backend

# ── Python Commands ──────────────────────────────────────────────────
install: ## Install all dependencies with uv
	uv sync --all-packages --group dev

test: ## Run all tests
	uv run pytest tests/ -x -v

test-cov: ## Run tests with coverage report
	uv run pytest tests/ --cov --cov-report=html
	@echo "Open htmlcov/index.html to view coverage"

lint: ## Run linter
	uv run ruff check .

format: ## Format all Python code
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run mypy type checker
	uv run mypy apps/backend/src apps/worker/src packages/common/src

# ── Database Commands ────────────────────────────────────────────────
migrate: ## Run database migrations
	cd apps/backend && uv run alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new MSG="add users table")
	cd apps/backend && uv run alembic revision --autogenerate -m "$(MSG)"

seed: ## Seed database with sample data
	uv run python infra/scripts/seed-db.py

# ── Cleanup ──────────────────────────────────────────────────────────
clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml
```

---

## Alembic Configuration

```ini
# apps/backend/alembic.ini
[alembic]
script_location = alembic
prepend_sys_path = src
sqlalchemy.url = driver://user:pass@localhost/dbname
# actual URL is set in alembic/env.py from settings
```

```python
# apps/backend/alembic/env.py
"""Alembic migration environment wired to our async engine."""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from parikrama.config import settings
from parikrama.models.base import Base

# import all models so Alembic sees them for autogenerate
from parikrama.models import user, trip, agent, document, notification, approval, cost  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without connecting to the database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations with an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## Setup Scripts

### Windows PowerShell Setup

```powershell
# infra/scripts/setup-dev.ps1
# PariKrama development environment bootstrap (Windows)
# Usage: .\infra\scripts\setup-dev.ps1

Write-Host "🚀 Setting up PariKrama development environment..." -ForegroundColor Cyan

# check prerequisites
$required = @("docker", "uv", "node")
foreach ($cmd in $required) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "❌ '$cmd' is not installed. Please install it first." -ForegroundColor Red
        exit 1
    }
}

# copy .env if it doesn't exist
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "📝 Created .env from .env.example — edit it with your API keys" -ForegroundColor Yellow
}

# install Python dependencies
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Cyan
uv sync --all-packages --group dev

# install pre-commit hooks
Write-Host "🪝 Installing pre-commit hooks..." -ForegroundColor Cyan
uv run pre-commit install

# install frontend dependencies
Write-Host "📦 Installing frontend dependencies..." -ForegroundColor Cyan
Push-Location apps/frontend
npm ci
Pop-Location

# start Docker services
Write-Host "🐳 Starting Docker services..." -ForegroundColor Cyan
docker compose -f infra/docker/docker-compose.yml up -d postgres redis minio

# wait for postgres
Write-Host "⏳ Waiting for PostgreSQL..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

# run migrations
Write-Host "🗄️  Running database migrations..." -ForegroundColor Cyan
Push-Location apps/backend
uv run alembic upgrade head
Pop-Location

Write-Host ""
Write-Host "✅ Setup complete! Run 'make dev' to start all services." -ForegroundColor Green
Write-Host ""
Write-Host "Available services:" -ForegroundColor Cyan
Write-Host "  Backend API:    http://localhost:8000/docs"
Write-Host "  Frontend:       http://localhost:3000"
Write-Host "  MinIO Console:  http://localhost:9001"
Write-Host "  Grafana:        http://localhost:3001"
Write-Host "  Prometheus:     http://localhost:9090"
```

---

## .gitignore Additions

```gitignore
# ── PariKrama-specific ────────────────────────────────────────────────
.env
.env.local
.env.production

# uv
.venv/
uv.lock  # keep this committed for reproducibility — remove this line

# data directories
data/knowledge_base/*
data/models/*
!data/knowledge_base/.gitkeep
!data/models/.gitkeep

# local ML models
*.pt
*.bin
*.onnx

# MinIO data
infra/docker/minio/data/

# Firebase credentials
firebase-credentials.json

# coverage
htmlcov/
coverage.xml
.coverage

# IDE
.idea/
.vscode/
*.swp
```

---

## Testing Strategy

### Phase 0 Tests
| Test | Type | What It Validates |
|------|------|-------------------|
| Docker compose health | Integration | All services start and pass health checks |
| App imports | Unit | `from parikrama.main import app` doesn't crash |
| Settings validation | Unit | Missing required env vars raise clear errors |
| Config parsing | Unit | CORS origins parse from string and list |

```python
# tests/backend/test_config.py
"""Tests for configuration loading and validation."""
import os
import pytest
from unittest.mock import patch


def test_settings_loads_from_env():
    """Settings should load all required values from environment."""
    from parikrama.config import Settings

    with patch.dict(os.environ, {
        "SECRET_KEY": "test-secret",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
        "JWT_SECRET_KEY": "jwt-test",
    }):
        s = Settings()
        assert s.APP_NAME == "PariKrama"
        assert s.DEBUG is True


def test_settings_fails_without_required_vars():
    """App should fail fast if SECRET_KEY is missing."""
    from pydantic import ValidationError
    from parikrama.config import Settings

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError):
            Settings()


def test_cors_origins_parses_json_string():
    """CORS_ORIGINS should accept JSON array string from env."""
    from parikrama.config import Settings

    with patch.dict(os.environ, {
        "SECRET_KEY": "test",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "CORS_ORIGINS": '["http://localhost:3000","http://example.com"]',
    }):
        s = Settings()
        assert len(s.CORS_ORIGINS) == 2
        assert "http://localhost:3000" in s.CORS_ORIGINS
```

---

## Definition of Done — Phase 0

- [ ] Monorepo structure created with all directories
- [ ] `pyproject.toml` (root) configured with uv workspace members
- [ ] `apps/backend/pyproject.toml` with all dependencies listed
- [ ] `apps/worker/pyproject.toml` with Celery dependencies
- [ ] `packages/common` shared package with enums and constants
- [ ] `.env.example` contains ALL environment variables with descriptions
- [ ] `docker-compose.yml` starts: PostgreSQL+pgvector, Redis, MinIO, LiveKit, Prometheus, Grafana
- [ ] PostgreSQL `init.sql` enables pgvector, pg_trgm, uuid-ossp extensions
- [ ] Dockerfiles for backend, worker, and frontend are buildable
- [ ] `make dev` starts the full development environment
- [ ] `make test` runs the test suite
- [ ] Pre-commit hooks configured (ruff, mypy, eslint, secret detection)
- [ ] GitHub Actions CI runs on every PR (lint, test, Docker build)
- [ ] FastAPI app factory with lifespan hooks starts without errors
- [ ] Pydantic Settings loads and validates all environment variables
- [ ] CorrelationId middleware injects trace IDs into every request
- [ ] Alembic configured for async migrations
- [ ] Windows setup script (`setup-dev.ps1`) bootstraps the environment
- [ ] `.gitignore` covers all generated files, secrets, and data dirs
- [ ] Shared enums defined in `parikrama_common` package

## Common Pitfalls

| Pitfall | How to Avoid |
|---------|-------------|
| **pgvector image not found** | Use `pgvector/pgvector:pg16` not `postgres:16` with manual extension |
| **uv lockfile conflicts** | Always run `uv lock` after changing any `pyproject.toml` |
| **Docker volume permissions** | Use named volumes, not bind mounts for database data |
| **CORS issues in dev** | Set `CORS_ORIGINS=["http://localhost:3000"]` explicitly |
| **Alembic can't find models** | Import all model modules in `alembic/env.py` |
| **MinIO buckets not created** | The `minio-init` service handles this — ensure it depends on minio health |
| **Windows path issues** | Use forward slashes in Python paths, Dockerfiles handle Linux paths |

## Scale-Up Path

| Component | Current | When to Scale | Scale-To |
|-----------|---------|---------------|----------|
| PostgreSQL | Single instance | > 10K concurrent users | Read replicas + PgBouncer |
| Redis | Single instance | > 50K ops/sec | Redis Cluster (6 nodes) |
| Celery Workers | 2 concurrent | Task queue > 100 pending | Kubernetes HPA, 4-8 workers |
| MinIO | Single node | > 1TB storage | Distributed mode (4+ nodes) |
| Backend | Single instance | > 500 req/sec | Kubernetes with 3-5 replicas behind ingress |

---

*Phase 0 provides the complete foundation. Every subsequent phase builds on this structure without modifying the core infrastructure setup.*
