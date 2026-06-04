# Phase 9: Monitoring + Observability

## Overview

Phase 9 adds **eyes and ears** to the entire system — you can't fix what you can't see. This phase instruments everything: LLM calls, agent executions, API latency, error rates, WebSocket connections, and per-user cost tracking. When something breaks at 3 AM, you'll know within seconds.

### The Monitoring Stack
```
Application Code → [Structlog] → JSON logs → stdout
                 → [Prometheus Client] → /metrics endpoint → Prometheus → Grafana
                 → [LangSmith SDK] → LLM trace data → LangSmith Dashboard
                 → [Sentry SDK] → Errors + traces → Sentry Dashboard
```

---

## Implementation

### Structlog Configuration

```python
# apps/backend/src/parikrama/core/logging_config.py
"""
Structured logging setup with structlog.

Every log entry is a JSON object with:
- timestamp, level, event (message)
- correlation_id (traces a request across services)
- agent, trip_id, user_id (context-dependent)

JSON logs are parseable by Grafana Loki, CloudWatch, etc.
"""
import logging
import sys

import structlog
from parikrama.config import settings


def setup_logging() -> None:
    """Configure structlog with JSON output for production, pretty for dev."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.APP_ENV == "development":
        # pretty colored output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON output for production (parseable by log aggregators)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[*shared_processors, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
```

### Prometheus Metrics

```python
# apps/backend/src/parikrama/core/metrics.py
"""
Prometheus metrics for PariKrama.

Exposes key performance indicators at /metrics endpoint.
Grafana scrapes this every 10 seconds for dashboards.
"""
from prometheus_client import Counter, Histogram, Gauge, Info

# ── Application Info ──────────────────────────────────────────────────
app_info = Info("parikrama", "PariKrama application information")
app_info.info({"version": "0.1.0", "environment": "development"})

# ── Trip Metrics ─────────────────────────────────────────────────────
trips_planned_total = Counter(
    "parikrama_trips_planned_total",
    "Total number of trips planned",
    ["status"],  # completed, failed, cancelled
)

trip_planning_duration = Histogram(
    "parikrama_trip_planning_duration_seconds",
    "Time taken to plan a trip end-to-end",
    buckets=[5, 10, 20, 30, 60, 120, 300],
)

# ── Agent Metrics ────────────────────────────────────────────────────
agent_duration_seconds = Histogram(
    "parikrama_agent_duration_seconds",
    "Individual agent execution time",
    ["agent_name"],  # orchestrator, research, booking, budget, itinerary
    buckets=[1, 2, 5, 10, 20, 30, 60],
)

agent_errors_total = Counter(
    "parikrama_agent_errors_total",
    "Total agent execution errors",
    ["agent_name", "error_type"],
)

# ── LLM Metrics ──────────────────────────────────────────────────────
llm_tokens_used_total = Counter(
    "parikrama_llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "direction"],  # direction: input/output
)

llm_request_duration = Histogram(
    "parikrama_llm_request_duration_seconds",
    "LLM API call latency",
    ["provider"],  # gemini, groq_llama, groq_mixtral
    buckets=[0.5, 1, 2, 5, 10, 20, 30],
)

llm_fallback_events_total = Counter(
    "parikrama_llm_fallback_events_total",
    "Times the system fell back to secondary LLM",
    ["from_provider", "to_provider", "reason"],
)

# ── WebSocket Metrics ────────────────────────────────────────────────
active_websocket_connections = Gauge(
    "parikrama_active_websocket_connections",
    "Currently active WebSocket connections",
)

# ── RAG Metrics ──────────────────────────────────────────────────────
rag_search_duration = Histogram(
    "parikrama_rag_search_duration_seconds",
    "RAG search latency",
    ["search_type"],  # hybrid, semantic, keyword
    buckets=[0.1, 0.25, 0.5, 1, 2, 5],
)

rag_results_count = Histogram(
    "parikrama_rag_results_count",
    "Number of results returned per search",
    buckets=[0, 1, 3, 5, 10, 20],
)

# ── HTTP Metrics ─────────────────────────────────────────────────────
http_requests_total = Counter(
    "parikrama_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration = Histogram(
    "parikrama_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5],
)

# ── Voice Metrics ────────────────────────────────────────────────────
voice_sessions_total = Counter(
    "parikrama_voice_sessions_total",
    "Total voice sessions started",
)

voice_pipeline_duration = Histogram(
    "parikrama_voice_pipeline_duration_seconds",
    "Voice pipeline latency (speech to response)",
    buckets=[0.3, 0.5, 0.8, 1, 1.5, 2, 3],
)
```

### Prometheus Middleware

```python
# added to apps/backend/src/parikrama/core/middleware.py
"""
Prometheus metrics middleware — instruments every HTTP request.
"""
import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from parikrama.core.metrics import http_requests_total, http_request_duration


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record HTTP request metrics for Prometheus."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # skip metrics endpoint itself to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # normalize path (remove UUIDs for cardinality control)
        endpoint = self._normalize_path(request.url.path)

        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(response.status_code),
        ).inc()

        http_request_duration.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)

        return response

    def _normalize_path(self, path: str) -> str:
        """Replace UUID segments with {id} to keep cardinality manageable."""
        import re
        return re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}", path,
        )
```

### Sentry Integration

```python
# added to apps/backend/src/parikrama/main.py (in create_app)
"""Sentry setup for error tracking and performance monitoring."""
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

def init_sentry():
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            send_default_pii=False,  # don't send user emails to Sentry
        )
```

### LangSmith Tracing Setup

```python
# apps/backend/src/parikrama/llm/tracing.py
"""
LangSmith tracing configuration.

Every LLM call, tool use, and chain execution is traced.
Uses LangSmith's free tier (5,000 traces/month).
"""
import os
from parikrama.config import settings


def setup_langsmith():
    """Configure LangSmith environment variables for tracing."""
    if settings.LANGCHAIN_TRACING_V2:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
```

### Grafana Dashboard (JSON Export)

```json
{
  "dashboard": {
    "title": "PariKrama Overview",
    "panels": [
      {
        "title": "Trips Planned (24h)",
        "type": "stat",
        "targets": [{"expr": "sum(increase(parikrama_trips_planned_total[24h]))"}]
      },
      {
        "title": "Avg Trip Planning Time",
        "type": "gauge",
        "targets": [{"expr": "histogram_quantile(0.95, rate(parikrama_trip_planning_duration_seconds_bucket[1h]))"}]
      },
      {
        "title": "Active LLM Provider",
        "type": "stat",
        "targets": [{"expr": "parikrama_info{active_provider!=''}"}]
      },
      {
        "title": "LLM Fallback Events",
        "type": "timeseries",
        "targets": [{"expr": "rate(parikrama_llm_fallback_events_total[5m])"}]
      },
      {
        "title": "Agent Latency (p95)",
        "type": "timeseries",
        "targets": [{"expr": "histogram_quantile(0.95, rate(parikrama_agent_duration_seconds_bucket[5m]))"}],
        "fieldConfig": {"defaults": {"unit": "s"}}
      },
      {
        "title": "Active WebSocket Connections",
        "type": "gauge",
        "targets": [{"expr": "parikrama_active_websocket_connections"}]
      },
      {
        "title": "HTTP Request Rate",
        "type": "timeseries",
        "targets": [{"expr": "sum(rate(parikrama_http_requests_total[5m]))"}]
      },
      {
        "title": "Error Rate",
        "type": "timeseries",
        "targets": [{"expr": "sum(rate(parikrama_http_requests_total{status=~'5..'}[5m]))"}]
      }
    ]
  }
}
```

### Alert Rules

```yaml
# infra/docker/prometheus/alert_rules.yml
groups:
  - name: parikrama_alerts
    rules:
      - alert: HighErrorRate
        expr: sum(rate(parikrama_http_requests_total{status=~"5.."}[5m])) > 0.5
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected (>0.5 req/sec with 5xx)"

      - alert: LLMFallbackActive
        expr: sum(increase(parikrama_llm_fallback_events_total[5m])) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "LLM router switched to fallback provider"

      - alert: HighTripLatency
        expr: histogram_quantile(0.95, rate(parikrama_trip_planning_duration_seconds_bucket[5m])) > 120
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Trip planning p95 latency exceeds 2 minutes"

      - alert: NoActiveConnections
        expr: parikrama_active_websocket_connections == 0
        for: 30m
        labels:
          severity: info
        annotations:
          summary: "No active WebSocket connections for 30 minutes"
```

---

## Definition of Done — Phase 9

- [ ] Structlog configured with JSON output in production, pretty in dev
- [ ] Correlation ID middleware traces requests across all services
- [ ] Prometheus /metrics endpoint exposes all defined metrics
- [ ] Grafana dashboard imported and showing real data
- [ ] LangSmith tracing captures all LLM calls with costs
- [ ] Sentry captures errors with full stack traces
- [ ] Alert rules configured for error rate, latency, and LLM fallback
- [ ] Cost tracking aggregated per user per trip
- [ ] Log correlation works across backend → worker → agents

---

*Phase 9 gives operators complete visibility. When a trip takes 3 minutes instead of 30 seconds, you can trace exactly which agent was slow and which LLM call was the bottleneck.*
