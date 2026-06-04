# ══════════════════════════════════════════════════════════════════════
# PariKrama Makefile — developer commands
# Usage: make <target>
# ══════════════════════════════════════════════════════════════════════

.DEFAULT_GOAL := help
.PHONY: help dev backend worker services stop clean test lint format migrate

# ── Help ─────────────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ──────────────────────────────────────────────────────
services: ## Start infrastructure services (DB, Redis, MinIO, etc.)
	docker compose -f infra/docker/docker-compose.yml up -d

stop: ## Stop all infrastructure services
	docker compose -f infra/docker/docker-compose.yml down

backend: ## Start FastAPI dev server with hot reload
	cd apps/backend && uv run uvicorn parikrama.main:app --host 0.0.0.0 --port 8000 --reload

worker: ## Start Celery worker
	cd apps/worker && uv run celery -A parikrama_worker.celery_app worker --loglevel=info

beat: ## Start Celery Beat scheduler
	cd apps/worker && uv run celery -A parikrama_worker.celery_app beat --loglevel=info

frontend: ## Start Next.js dev server
	cd apps/frontend && npm run dev

dev: services ## Start everything (services + backend)
	@echo "Services started. Run 'make backend' in another terminal."

# ── Database ─────────────────────────────────────────────────────────
migrate: ## Run database migrations
	cd apps/backend && uv run alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new MSG="add users table")
	cd apps/backend && uv run alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback one migration
	cd apps/backend && uv run alembic downgrade -1

# ── Code Quality ─────────────────────────────────────────────────────
test: ## Run test suite
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage
	uv run pytest tests/ -v --cov=apps --cov-report=term-missing

lint: ## Run linter
	uv run ruff check .

format: ## Auto-format code
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run type checker
	uv run mypy apps/backend/src apps/worker/src packages/common/src

# ── Cleanup ──────────────────────────────────────────────────────────
clean: ## Remove all containers, volumes, and cache
	docker compose -f infra/docker/docker-compose.yml down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

# ── Install ──────────────────────────────────────────────────────────
install: ## Install all dependencies
	uv sync --all-packages --group dev

install-hooks: ## Install pre-commit hooks
	uv run pre-commit install
