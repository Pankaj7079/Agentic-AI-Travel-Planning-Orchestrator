# PariKrama — Claude Context File

> **Agentic AI Travel Planning Orchestrator**
> User says "Delhi to Manali, 5 days, ₹15,000" → system spawns AI agents that research,
> plan, and deliver a complete itinerary with RAG-grounded context.

---

## 🧠 Engineering Mindset (Read Before Every Task)

You are a **Senior AI/ML Engineer, System Architect, and Backend Developer** working on a
production-grade agentic AI system. This is NOT a toy project — every decision matters.

### Before Writing Code — Always Think First

```
1. UNDERSTAND → Read the existing code, the phase doc, the failing test
2. DESIGN     → Plan the architecture, data contracts, failure modes
3. VALIDATE   → Check: Is this consistent with existing patterns? Will it break CI?
4. BUILD      → Write production-quality, typed, tested, documented code
5. VERIFY     → Run linter, run tests, confirm CI passes
```

> ⚠️ **Never code in the wrong direction.** If requirements are unclear, STOP and ask.
> A wrong implementation wastes more time than clarifying upfront.

### Quality Standards for This Project

| Standard | Requirement |
|----------|------------|
| **Type safety** | Full type annotations + Pydantic everywhere |
| **Async** | All I/O must be `async/await` — no blocking calls |
| **Testing** | Every new feature gets at least one test |
| **Lint** | Ruff `0 errors` before every single commit |
| **Logging** | structlog for all important events (never bare `print`) |
| **Error handling** | Every LLM call, DB op, and external API must have try/except + fallback |
| **Docs** | Every class, function, and module has a clear docstring |

### Agentic System Principles (Critical for This Project)

- **LangGraph StateGraph:** State MUST be `TypedDict` — not Pydantic, not dataclass
- **Circuit breaker:** Every LLM provider must have error threshold + recovery probe
- **RAG-grounded:** Agents must retrieve context BEFORE calling the LLM — never hallucinate
- **Observability:** Log agent name, query, RAG chunks used, provider, model, latency on every run
- **Graceful degradation:** If Gemini fails → fallback to Groq. If RAG fails → continue without context.
- **Idempotent:** Agent runs with the same input should produce consistent (not identical) outputs
- **Human-in-the-loop:** High-stakes decisions (booking, payment) need user confirmation (Phase 5)

---

## 🏗️ Monorepo Structure

```
PariKrama_Agentic-AI-Travel-Planning-Orchestrator/
├── apps/
│   ├── backend/          ← FastAPI backend (PRIMARY — most active)
│   │   └── src/parikrama/
│   │       ├── agents/   ← LangGraph agents
│   │       ├── api/v1/   ← REST endpoints
│   │       ├── core/     ← security, middleware, exceptions, logging
│   │       ├── db/       ← SQLAlchemy session
│   │       ├── llm/      ← LLM router + providers
│   │       ├── models/   ← SQLAlchemy ORM models
│   │       ├── rag/      ← chunker, embeddings, retriever, reranker
│   │       ├── repositories/ ← DB query layer (empty stub, direct service access used)
│   │       ├── schemas/  ← Pydantic schemas
│   │       ├── services/ ← Business logic layer
│   │       └── voice/    ← LiveKit voice stub (Phase 6, not yet implemented)
│   ├── worker/           ← Celery worker (document processing tasks)
│   │   └── src/parikrama_worker/
│   │       ├── celery_app.py
│   │       └── tasks/document_tasks.py
│   └── mcp/              ← MCP server stub (Phase 8, skeleton only)
│       └── src/parikrama_mcp/
├── packages/common/      ← Shared types (uv workspace package)
├── docs/phases/          ← Full phase design docs (IMPORTANT, read before starting a phase)
├── infra/
│   ├── docker/           ← docker-compose for local services
│   └── scripts/
├── tests/
│   ├── conftest.py       ← Shared fixtures: DB, client, session rollback
│   └── backend/          ← All backend tests
│       ├── test_auth.py
│       ├── test_health.py
│       ├── test_trips.py
│       ├── test_users.py
│       ├── test_rag.py
│       ├── test_llm_router.py
│       └── test_agents.py
├── Makefile              ← Dev commands (make backend, make test, etc.)
├── pyproject.toml        ← Root: uv workspace + ruff + pytest config
└── .github/workflows/ci.yml ← CI: Lint then Test (GitHub Actions)
```

---

## 📦 Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Package Manager** | `uv` | ALWAYS use `uv run` — never pip directly |
| **Backend** | FastAPI + Python 3.12 | Async-first, pydantic-settings config |
| **Agents** | LangGraph | StateGraph with TypedDict AgentState |
| **Primary LLM** | Gemini 2.5 Flash Lite | via `google-generativeai` |
| **Fallback LLM** | Groq / Llama-3.1-70B | Circuit breaker auto-fallback |
| **Embeddings** | sentence-transformers/all-MiniLM-L6-v2 | 384-dim, local |
| **Database** | PostgreSQL 16 + pgvector + pg_trgm | Vector + trigram search |
| **Cache/Queue** | Redis 7 | Celery broker + cache |
| **Object Storage** | MinIO | S3-compatible, self-hosted |
| **Auth** | Custom JWT | HS256, access + refresh tokens |
| **CI/CD** | GitHub Actions | `.github/workflows/ci.yml` |
| **Linter** | Ruff | Replaces black + isort + flake8 |
| **Voice** | LiveKit + Whisper + Coqui | Phase 6 — not yet built |
| **Frontend** | Next.js 14 + TypeScript | Phase 7 — not yet built |
| **MCP Server** | FastMCP | Phase 8 — skeleton only |
| **Monitoring** | LangSmith + Sentry + Prometheus | Phase 9 — not yet built |

---

## ✅ Implementation Status

### Phase 0 — Foundation ✅ COMPLETE
- uv monorepo workspace
- Docker Compose for PostgreSQL (pgvector), Redis, MinIO
- Makefile with `make dev`, `make test`, `make lint`, `make migrate`
- Ruff config (line-length=100, py312)
- GitHub Actions CI (lint → test with PostgreSQL + Redis services)
- Pre-commit hooks

### Phase 1 — Backend Core + Auth ✅ COMPLETE
**Models:** `User`, `Trip`, `UserCost` (SQLAlchemy async ORM)
**Auth:** JWT access + refresh tokens, bcrypt password hashing, Google OAuth stub
**API Endpoints:**
- `POST /api/v1/auth/register` — register user
- `POST /api/v1/auth/login` — login, returns access + refresh tokens
- `POST /api/v1/auth/refresh` — refresh access token
- `GET  /api/v1/auth/me` — get current user
- `GET  /api/v1/users/profile` — profile
- `PUT  /api/v1/users/profile` — update name/prefs
- `POST /api/v1/users/change-password`
- `GET  /api/v1/users/stats`
- `POST /api/v1/trips/` — create trip
- `GET  /api/v1/trips/` — list trips (filter by status)
- `GET  /api/v1/trips/{id}` — get trip detail
- `GET  /api/v1/trips/{id}/status` — status polling
- `POST /api/v1/trips/{id}/cancel`
- `GET  /api/v1/health` — health check
**Tests:** test_auth.py, test_trips.py, test_users.py, test_health.py (all passing ✅)

### Phase 2 — RAG Pipeline ✅ COMPLETE
**RAG Components:**
- `rag/chunker.py` — token-aware text splitter (RecursiveCharacterTextSplitter-style)
- `rag/embeddings.py` — SentenceTransformer (all-MiniLM-L6-v2, 384-dim) with LRU cache
- `rag/retriever.py` — hybrid search: pgvector cosine + pg_trgm BM25-like, RRF fusion
- `rag/reranker.py` — cross-encoder reranking (local)
**Models:** `Document`, `DocumentChunk` (with pgvector column)
**Services:** `DocumentService`, `RAGService`, `StorageService` (MinIO)
**Workers:** `document_tasks.py` — Celery: extract → chunk → embed → store in pgvector
**API Endpoints:**
- `POST /api/v1/documents/upload` — upload PDF/TXT to MinIO + trigger Celery task
- `GET  /api/v1/documents/` — list docs (paginated, filter by status/destination)
- `GET  /api/v1/documents/{id}` — get doc + processing status
- `DELETE /api/v1/documents/{id}` — delete doc + chunks
- `POST /api/v1/rag/query` — RAG hybrid search
- `GET  /api/v1/rag/stats` — KB statistics
**Tests:** test_rag.py (all passing ✅)

### Phase 3 — LLM Router + Agent Foundation ✅ COMPLETE
**LLM Layer:**
- `llm/schemas.py` — `LLMResponse`, `LLMProvider` (enum), `ProviderHealth`, `CircuitState`
- `llm/providers/gemini.py` — Gemini 2.5 Flash Lite provider
- `llm/providers/groq.py` — Groq/Llama-3.1-70B provider
- `llm/router.py` — `LLMRouter` with circuit breaker (sliding-window, error threshold,
  recovery probe), latency tracking, `from_settings()` factory
**Agent Foundation:**
- `agents/schemas.py` — `AgentInput`, `AgentOutput`, `AgentState` (TypedDict for LangGraph)
- `agents/base.py` — `BaseAgent` ABC: `build_graph()`, `retrieve_context()`, `_node_call_llm()`
- `agents/itinerary_agent.py` — `ItineraryAgent` (3-node graph: retrieve → call_llm → format)
- `agents/budget_agent.py` — `BudgetAgent` (3-node graph: extract_budget → retrieve → call_llm)
- `agents/prompts/itinerary.py` — system prompt for itinerary
- `agents/prompts/budget.py` — system prompt for budget
**API Endpoints:**
- `POST /api/v1/agents/itinerary` — run ItineraryAgent
- `POST /api/v1/agents/budget` — run BudgetAgent
- `GET  /api/v1/agents/health` — LLM router circuit breaker status
**CRITICAL BUG FIX:** `AsyncSession` must be imported at runtime (not under TYPE_CHECKING)
  in `agents.py` — FastAPI needs it to resolve `Annotated[AsyncSession, Depends(get_db)]`.
  Use `# noqa: TC002` comment to suppress ruff warning.
**Tests:** test_llm_router.py (11 tests), test_agents.py (18 tests) — all passing ✅

---

## 🔲 Upcoming Phases

| Phase | Name | Status |
|-------|------|--------|
| **4** | Multi-Agent System: OrchestratorAgent, HotelAgent, TransportAgent, ResearchAgent | 🔲 NEXT |
| **5** | Human-in-the-Loop + Email Notifications (Resend) | 🔲 |
| **6** | Voice Pipeline (LiveKit + Whisper + Coqui TTS) | 🔲 |
| **7** | Frontend (Next.js 14 + TypeScript + React) | 🔲 |
| **8** | MCP Server (Claude Desktop integration) | 🔲 skeleton exists |
| **9** | Monitoring (LangSmith + Sentry + Prometheus + Grafana) | 🔲 |
| **10** | Production Deployment (Docker + Railway) | 🔲 |

> **Phase design docs:** `docs/phases/phase_XX_name.md` — read BEFORE starting any phase!

---

## ⚙️ Key Dev Commands

```powershell
# Install everything
uv sync --all-packages --group dev

# Start infrastructure (PostgreSQL, Redis, MinIO)
make services
# OR
docker compose -f infra/docker/docker-compose.yml up -d

# Start backend
make backend
# OR: cd apps/backend && uv run uvicorn parikrama.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
uv run pytest tests/ -v --tb=short

# Lint + format (ALWAYS before committing)
uv run ruff check .
uv run ruff format .

# Database migrations
cd apps/backend && uv run alembic upgrade head

# Start Celery worker
make worker
```

---

## 🔑 Critical Conventions (MUST FOLLOW)

1. **Package manager:** ALWAYS `uv run <cmd>` — never `pip install`, never `python` directly
2. **Async everywhere:** All DB operations use `AsyncSession`, all endpoints are `async def`
3. **Lint before commit:** `uv run ruff check . && uv run ruff format --check .` must pass
4. **AsyncSession in FastAPI deps:** Import at runtime (not TYPE_CHECKING) for FastAPI DI
   → use `# noqa: TC002` to silence ruff's TC002 rule
5. **TypedDict for LangGraph:** `AgentState` must be a proper TypedDict (not dataclass/Pydantic)
6. **Tests are integration:** `conftest.py` uses real PostgreSQL with pgvector — tests require
   the DB service running (or CI provides it)
7. **Shell is PowerShell (Windows dev):** No `grep`, `cat`, `sed` — use PowerShell equivalents
   or Python. BUT CI runs on Ubuntu — use cross-platform commands in workflows.
8. **Ruff rules:** line-length=100, TC002 (type-checking imports) is enforced — use noqa sparingly
9. **Commits:** Always `git add -A && git commit -m "type(scope): message" && git push`
10. **No scratch files in git:** Delete temp files before committing

---

## 🐛 Known Issues / Gotchas

- **TC002 + FastAPI:** Any `Annotated[SomeType, Depends(...)]` where `SomeType` is a
  third-party class MUST be imported at runtime. Put `# noqa: TC002` on that import.
- **AgentState:** LangGraph requires a TypedDict — Pydantic BaseModel WILL NOT work
  as StateGraph state schema (causes Pyright type errors but still works at runtime).
- **PostgreSQL tests:** `conftest.py` creates `vector` and `pg_trgm` extensions.
  CI provides PostgreSQL via GitHub Actions services. Local dev needs Docker.
- **MinIO:** Not used in tests (mocked). Needed for real document uploads.
- **Celery worker:** Not tested in unit tests — document processing is Celery async.

---

## 📁 Config / Env Vars (from `apps/backend/src/parikrama/config.py`)

Key variables to set in `.env`:
```
GEMINI_API_KEY=<your-key>     # Primary LLM
GROQ_API_KEY=<your-key>       # Fallback LLM (at least one required for agents)
DATABASE_URL=postgresql+asyncpg://parikrama:parikrama_dev_2024@localhost:5432/parikrama
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=<random-secret>
SECRET_KEY=<random-secret>
```

---

## 🔗 GitHub Repo

`https://github.com/Pankaj7079/PariKrama_Agentic-AI-Travel-Planning-Orchestrator`
Branch: `main` — CI runs on every push
