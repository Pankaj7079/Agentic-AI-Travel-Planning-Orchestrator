# PariKrama

**Agentic AI Travel Planning Orchestrator**

> User says "Delhi to Manali, 5 days, ₹15,000" → system spawns AI agents that research,
> plan, and deliver a complete itinerary with RAG-grounded context.

[![CI](https://github.com/Pankaj7079/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/Pankaj7079/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![Ruff](https://img.shields.io/badge/ruff-0-errors-brightgreen)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-156%20passing-brightgreen)](https://github.com/Pankaj7079/PariKrama_Agentic-AI-Travel-Planning-Orchestrator)

---

## Features

- **Multi-Agent Pipeline** — LangGraph-orchestrated agents: Orchestrator, Research, Booking, Budget Optimizer, Itinerary Finalizer
- **RAG-Grounded Planning** — Hybrid search (pgvector cosine + pg_trgm BM25) with cross-encoder reranking
- **Dual LLM Support** — Gemini 2.5 Flash Lite (primary) with Groq/Llama-3.1-70B circuit-breaker fallback
- **Human-in-the-Loop** — Approval gates for expensive hotel/transport decisions via WebSocket
- **Real-time Progress** — WebSocket + polling for live agent status updates
- **Voice Pipeline** — LiveKit + Whisper STT + Coqui TTS (Phase 6)
- **JWT Auth** — Access + refresh tokens, bcrypt hashing, Google OAuth stub
- **Document Processing** — PDF/TXT upload → chunk → embed → pgvector via Celery workers

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client (Next.js)                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │ REST + WebSocket
┌──────────────────────────────▼──────────────────────────────────┐
│                     FastAPI Backend                              │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │  Auth    │  │  Trips   │  │  RAG     │  │  Approvals/    │  │
│  │  API     │  │  API     │  │  API     │  │  Notifications │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬────────┘  │
│       │              │             │                 │           │
│  ┌────▼──────────────▼─────────────▼─────────────────▼────────┐ │
│  │                    Service Layer                            │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │                                      │
│  ┌────────────────────────▼───────────────────────────────────┐ │
│  │              LangGraph Trip Planning Pipeline               │ │
│  │                                                             │ │
│  │  orchestrator → [research ‖ booking] → budget → itinerary   │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼───────┐    ┌────────▼────────┐    ┌────────▼────────┐
│  PostgreSQL   │    │     Redis       │    │     MinIO       │
│  + pgvector   │    │  (Celery broker)│    │  (S3 storage)   │
└───────────────┘    └─────────────────┘    └─────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Package Manager** | `uv` |
| **Backend** | FastAPI + Python 3.12 (async-first) |
| **Agents** | LangGraph (StateGraph + TypedDict) |
| **Primary LLM** | Gemini 2.5 Flash Lite |
| **Fallback LLM** | Groq / Llama-3.1-70B |
| **Embeddings** | sentence-transformers/all-MiniLM-L6-v2 (384-dim, local) |
| **Database** | PostgreSQL 16 + pgvector + pg_trgm |
| **Cache/Queue** | Redis 7 |
| **Object Storage** | MinIO (S3-compatible) |
| **Auth** | Custom JWT (HS256, access + refresh) |
| **Linter** | Ruff |
| **CI/CD** | GitHub Actions |

---

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker & Docker Compose
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/Pankaj7079/PariKrama_Agentic-AI-Travel-Planning-Orchestrator.git
cd PariKrama_Agentic-AI-Travel-Planning-Orchestrator

# Install all dependencies
uv sync --all-packages --group dev
```

### Environment Setup

Create a `.env` file in `apps/backend/`:

```env
# LLM API Keys (at least one required)
GEMINI_API_KEY=your-gemini-key
GROQ_API_KEY=your-groq-key

# Database
DATABASE_URL=postgresql+asyncpg://parikrama:parikrama_dev_2024@localhost:5432/parikrama

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
JWT_SECRET_KEY=your-random-secret
SECRET_KEY=your-random-secret
```

### Start Services

```bash
# Start PostgreSQL, Redis, MinIO
make services
# OR
docker compose -f infra/docker/docker-compose.yml up -d

# Run database migrations
cd apps/backend && uv run alembic upgrade head

# Start the backend
make backend
# OR
cd apps/backend && uv run uvicorn parikrama.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery worker (optional, for document processing)
make worker
```

The API is now available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/register` | Register new user |
| `POST` | `/api/v1/auth/login` | Login (returns access + refresh tokens) |
| `POST` | `/api/v1/auth/refresh` | Refresh access token |
| `GET` | `/api/v1/auth/me` | Get current user |

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/users/me` | Get full profile |
| `PATCH` | `/api/v1/users/me` | Update name, notification prefs |
| `POST` | `/api/v1/users/me/change-password` | Change password |
| `GET` | `/api/v1/users/me/stats` | Trip and cost statistics |

### Trips

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/trips` | Create a new trip |
| `GET` | `/api/v1/trips` | List trips (filter by status) |
| `GET` | `/api/v1/trips/{id}` | Get trip details |
| `GET` | `/api/v1/trips/{id}/status` | Poll planning status |
| `POST` | `/api/v1/trips/{id}/plan` | Trigger multi-agent pipeline |
| `POST` | `/api/v1/trips/{id}/cancel` | Cancel trip |
| `GET` | `/api/v1/trips/{id}/agents` | Agent run history |
| `GET` | `/api/v1/trips/{id}/export/pdf` | Export itinerary as HTML |
| `POST` | `/api/v1/trips/{id}/share` | Create shareable link |

### Approvals (HITL)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/approvals` | List pending approvals |
| `POST` | `/api/v1/approvals/{id}/approve` | Approve and resume pipeline |
| `POST` | `/api/v1/approvals/{id}/reject` | Reject and cancel trip |

### RAG & Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/documents/upload` | Upload document (PDF/TXT) |
| `GET` | `/api/v1/documents` | List documents |
| `DELETE` | `/api/v1/documents/{id}` | Delete document + chunks |
| `POST` | `/api/v1/rag/search` | RAG hybrid search |
| `GET` | `/api/v1/rag/stats` | Knowledge base statistics |

### Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/notifications` | List notifications |
| `GET` | `/api/v1/notifications/unread-count` | Unread count |
| `POST` | `/api/v1/notifications/{id}/read` | Mark as read |
| `POST` | `/api/v1/notifications/read-all` | Mark all as read |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/agents/health` | LLM router status |
| `GET` | `/metrics` | Prometheus metrics |

---

## Project Structure

```
PariKrama_Agentic-AI-Travel-Planning-Orchestrator/
├── apps/
│   ├── backend/               # FastAPI backend
│   │   └── src/parikrama/
│   │       ├── agents/        # LangGraph agents
│   │       │   ├── trip_graph.py        # Main planning pipeline
│   │       │   ├── trip_state.py        # Shared TypedDict state
│   │       │   ├── orchestrator.py      # Request parser
│   │       │   ├── research_agent.py    # Weather, places, RAG
│   │       │   ├── booking_agent.py     # Hotels, transport
│   │       │   ├── budget_optimizer.py  # Cost breakdown
│   │       │   └── final_itinerary_agent.py  # Day-by-day plan
│   │       ├── api/v1/        # REST endpoints
│   │       ├── core/          # Security, middleware, logging
│   │       ├── db/            # SQLAlchemy async session
│   │       ├── llm/           # LLM router + providers
│   │       ├── models/        # SQLAlchemy ORM models
│   │       ├── rag/           # Chunker, embeddings, retriever
│   │       ├── schemas/       # Pydantic request/response
│   │       └── services/      # Business logic
│   ├── worker/                # Celery document processor
│   └── mcp/                   # MCP server (skeleton)
├── tests/                     # Integration tests (156 tests)
├── docs/phases/               # Phase design documents
├── infra/docker/              # Docker Compose config
├── Makefile                   # Dev commands
└── pyproject.toml             # uv workspace + ruff + pytest
```

---

## Development

### Available Commands

```bash
# Install dependencies
uv sync --all-packages --group dev

# Start infrastructure
make services

# Start backend (with auto-reload)
make backend

# Run all tests
uv run pytest tests/ -v --tb=short

# Lint (always before committing)
uv run ruff check .
uv run ruff format .

# Database migrations
cd apps/backend && uv run alembic upgrade head
```

### Commit Convention

```
type(scope): short description

feat(agents): add parallel research execution
fix(auth): resolve token refresh race condition
docs(readme): update API endpoints
test(trips): add create trip validation tests
```

---

## Testing

Tests are integration tests using real PostgreSQL with pgvector. The test database is created and torn down per test session.

```bash
# Run all tests
uv run pytest tests/ -v --tb=short

# Run specific test file
uv run pytest tests/backend/test_trips.py -v

# Run with coverage
uv run pytest tests/ --cov=parikrama --cov-report=term-missing
```

**Test Coverage:**
- `test_auth.py` — Registration, login, token refresh, profile
- `test_trips.py` — Trip CRUD, status polling, cancellation
- `test_users.py` — Profile, password change, stats
- `test_agents.py` — ItineraryAgent, BudgetAgent, API auth
- `test_rag.py` — Chunker, embeddings, RRF fusion, document API
- `test_llm_router.py` — Routing, circuit breaker, fallback
- `test_trip_planning.py` — Full pipeline: orchestrator, research, booking, budget, graph routing
- `test_hitl.py` — Approvals, notifications, WebSocket manager
- `test_voice.py` — VAD, STT, TTS, LiveKit, voice sessions

---

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Foundation (uv, Docker, CI) | Complete |
| 1 | Backend Core + Auth | Complete |
| 2 | RAG Pipeline | Complete |
| 3 | LLM Router + Agent Foundation | Complete |
| 4 | Multi-Agent Pipeline | Complete |
| 5 | Human-in-the-Loop + Notifications | Complete |
| 6 | Voice Pipeline (LiveKit + Whisper + Coqui) | Planned |
| 7 | Frontend (Next.js 14 + TypeScript) | Planned |
| 8 | MCP Server (Claude Desktop) | Planned |
| 9 | Monitoring (LangSmith + Sentry + Prometheus) | Planned |
| 10 | Production Deployment | Planned |

---

## License

This project is licensed under the MIT License.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit changes (`git commit -m 'feat(scope): add amazing feature'`)
4. Push to branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

**Before submitting:** Ensure `uv run ruff check .` passes with 0 errors and all tests pass.
