# Phase 10: Production Deployment

## Overview

Phase 10 takes PariKrama from development to production — hardened Docker images, automated CI/CD, database backups, health checks, and deployment to Railway.app. After this phase, every push to `main` deploys to staging automatically, and every version tag deploys to production.

---

## Architecture Decisions

### Decision 1: Railway vs Render vs Self-hosted
| Platform | Free Tier | Ease | PostgreSQL | WebSocket | Docker |
|----------|-----------|------|-----------|-----------|--------|
| **Railway (chosen)** | $5 credit/mo | Easy | Managed | ✅ | ✅ |
| Render | 750 hrs/mo | Easy | Managed | ✅ | ✅ |
| Self-hosted VPS | Varies | Manual | Self-manage | ✅ | ✅ |

**Why Railway:** Best Docker support among free-tier platforms. Native Docker deployment from GitHub. Managed PostgreSQL and Redis. WebSocket support works out of the box. $5/month credit covers a small project.

---

## Production Docker Compose

```yaml
# infra/docker/docker-compose.prod.yml
# Production overrides — extends the base docker-compose.yml
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  backend:
    build:
      target: production
    environment:
      - APP_ENV=production
      - DEBUG=false
      - LOG_LEVEL=INFO
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
        reservations:
          cpus: "0.5"
          memory: 512M
      restart_policy:
        condition: on-failure
        max_attempts: 3
    command: >
      uv run uvicorn parikrama.main:app
      --host 0.0.0.0 --port 8000
      --workers 4 --loop uvloop
      --no-access-log

  worker:
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G        # workers load ML models
        reservations:
          memory: 1G
      restart_policy:
        condition: on-failure
        max_attempts: 3
    command: >
      uv run celery -A parikrama_worker.celery_app worker
      --loglevel=warning --concurrency=4 --max-tasks-per-child=100

  postgres:
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1G

  redis:
    deploy:
      resources:
        limits:
          memory: 512M

  frontend:
    build:
      target: production
    deploy:
      resources:
        limits:
          memory: 512M
```

---

## GitHub Actions — Full CI/CD

### Production Deployment

```yaml
# .github/workflows/deploy-production.yml
name: Deploy to Production

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  validate:
    name: Validate Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Verify tag format
        run: |
          if [[ ! "${{ github.ref_name }}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "Invalid tag format. Use: v1.0.0"
            exit 1
          fi

  test:
    name: Run Full Test Suite
    needs: validate
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.12
      - run: uv sync --frozen --all-packages --group dev
      - run: uv run pytest tests/ -x --cov
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost/test
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret
          JWT_SECRET_KEY: test-jwt

  deploy:
    name: Deploy
    needs: test
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy Backend
        run: railway up --service parikrama-backend
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}

      - name: Deploy Worker
        run: railway up --service parikrama-worker
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}

      - name: Deploy Frontend
        run: railway up --service parikrama-frontend
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}

      - name: Run Migrations
        run: railway run --service parikrama-backend -- uv run alembic upgrade head
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}

      - name: Health Check
        run: |
          sleep 30
          curl -f https://api.parikrama.dev/api/v1/health || exit 1
```

---

## Health Check Implementation

```python
# Complete health check with detailed status
@router.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}

@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    checks = {}

    # DB check
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "fail"

    # Redis check
    try:
        r = redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "fail"

    # LLM check
    from parikrama.llm.router import llm_router
    checks["llm"] = llm_router.active_provider.value

    healthy = all(v != "fail" for v in checks.values())
    status_code = 200 if healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
```

---

## Database Backup Strategy

```python
# infra/scripts/backup_db.py
"""
Automated database backup to MinIO.

Run via Celery Beat daily, or manually:
  uv run python infra/scripts/backup_db.py
"""
import subprocess
import datetime
from minio import Minio
from parikrama.config import settings


def backup_database():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"parikrama_backup_{timestamp}.sql.gz"

    # pg_dump compressed with gzip
    cmd = (
        f"pg_dump {settings.DATABASE_URL.replace('+asyncpg', '')} "
        f"| gzip > /tmp/{filename}"
    )
    subprocess.run(cmd, shell=True, check=True)

    # upload to MinIO
    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    client.fput_object("backups", filename, f"/tmp/{filename}")

    # cleanup: keep only last 30 backups
    objects = list(client.list_objects("backups", prefix="parikrama_backup_"))
    if len(objects) > 30:
        old = sorted(objects, key=lambda o: o.last_modified)[:-30]
        for obj in old:
            client.remove_object("backups", obj.object_name)

    return filename


if __name__ == "__main__":
    print(f"Backup created: {backup_database()}")
```

---

## Graceful Shutdown

```python
# Added to main.py lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logger.info("starting_parikrama")

    yield

    # shutdown — graceful cleanup
    logger.info("shutting_down")

    # close all WebSocket connections
    from parikrama.api.websocket.manager import ws_manager
    # connections will be cleaned up on disconnect

    # dispose DB pool
    await engine.dispose()

    # flush remaining logs/metrics
    logger.info("shutdown_complete")
```

---

## Performance Benchmarks

| Metric | Target | Acceptable | Critical |
|--------|--------|-----------|----------|
| API response (p95) | < 200ms | < 500ms | > 1s |
| Trip planning (p95) | < 60s | < 120s | > 180s |
| LLM latency (p95) | < 5s | < 10s | > 15s |
| WebSocket delivery | < 100ms | < 500ms | > 1s |
| Voice pipeline | < 800ms | < 1.5s | > 2s |
| RAG search | < 500ms | < 1s | > 2s |
| Memory (backend) | < 1GB | < 2GB | > 4GB |
| Memory (worker) | < 2GB | < 4GB | > 8GB |

---

## Rollback Strategy

```bash
# if a deploy goes wrong:

# 1. Rollback to previous Railway deployment
railway rollback --service parikrama-backend

# 2. Rollback database migration
cd apps/backend && uv run alembic downgrade -1

# 3. If using Docker:
docker compose down
docker compose up -d --build  # with previous code
```

---

## Environment-Specific Configuration

| Setting | Development | Staging | Production |
|---------|------------|---------|-----------|
| `DEBUG` | true | true | **false** |
| `LOG_LEVEL` | DEBUG | INFO | **WARNING** |
| `SENTRY_TRACES_RATE` | 0 | 0.5 | **0.1** |
| `CORS_ORIGINS` | localhost:3000 | staging.* | **app.parikrama.dev** |
| `DB_POOL_SIZE` | 5 | 10 | **20** |
| Workers | 1 | 2 | **4** |
| Celery concurrency | 1 | 2 | **4** |

---

## Definition of Done — Phase 10

- [ ] Production Docker Compose with resource limits
- [ ] GitHub Actions deploys to staging on merge to main
- [ ] GitHub Actions deploys to production on version tag
- [ ] Database backup runs daily to MinIO
- [ ] Health endpoints return 503 when dependencies are down
- [ ] Graceful shutdown drains connections before stopping
- [ ] Environment-specific configs validated
- [ ] Performance benchmarks documented
- [ ] Rollback procedure tested
- [ ] Secret rotation documented
- [ ] SSL/TLS configured for all external endpoints

---

*Phase 10 is the final mile. After this, PariKrama is a production system that deploys, monitors, backs up, and recovers automatically.*
