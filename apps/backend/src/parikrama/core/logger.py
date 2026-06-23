"""
PariKrama Structured Logging System
====================================
Produces CLEAN, CATEGORIZED, GREP-FRIENDLY logs split into:

  logs/
  ├── parikrama.log        ← ALL events (JSON, no ANSI)
  ├── errors.log           ← ERRORS only (fast triage)
  ├── api_requests.log     ← HTTP requests (layer: API)
  ├── agents.log           ← LangGraph agent events
  ├── auth.log             ← Auth events (login/register/token)
  └── database.log         ← SQLAlchemy queries (suppressed unless DEBUG_SQL=true)

Log format (JSON — one line per event, easy to parse with jq):
  {
    "ts": "2026-06-20T09:10:00.123Z",
    "level": "error",
    "layer": "API",           ← API | AGENT | AUTH | DB | SYSTEM | CHATBOT
    "event": "http_request",
    "method": "POST",
    "path": "/api/v1/trips/xxx/plan",
    "status": 503,
    "duration_ms": 128.97,
    "error": "no_llm_provider_configured",
    "hint": "Set GEMINI_API_KEY or GROQ_API_KEY in .env",
    "correlation_id": "abc-123"
  }
"""

import logging
import logging.handlers
import sys
import json
from pathlib import Path
from datetime import UTC, datetime
from typing import Any

import structlog


# ── JSON formatter: clean, no ANSI, one line per event ────────────────────────

class JSONFormatter(logging.Formatter):
    """Write clean JSON logs — no ANSI escape codes, one line per record."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            # structlog already serialised the event into record.msg as a str or dict
            msg = record.getMessage()
            # If structlog already produced JSON, pass through
            if isinstance(msg, str) and msg.startswith("{"):
                return msg
            # Otherwise wrap into a minimal JSON
            return json.dumps({
                "ts": datetime.now(UTC).isoformat(),
                "level": record.levelname.lower(),
                "logger": record.name,
                "event": msg,
            }, ensure_ascii=False)
        except Exception:
            return record.getMessage()


class StructlogJSONFormatter(logging.Formatter):
    """Custom formatter that outputs structlog events as clean JSON."""

    def format(self, record: logging.LogRecord) -> str:
        # structlog's event dict is in record.__dict__
        event_dict = getattr(record, "_record", None)
        if event_dict and isinstance(event_dict, dict):
            return json.dumps(event_dict, default=str, ensure_ascii=False)
        return record.getMessage()


# ── Structured JSON renderer for structlog ────────────────────────────────────

class PariKramaJSONRenderer:
    """
    Structlog processor that renders events as clean JSON lines.
    No colours, no ANSI — only parseable JSON for log files.
    """

    def __call__(self, logger: Any, method: str, event_dict: dict) -> str:
        # Normalise keys
        ts = event_dict.pop("timestamp", datetime.now(UTC).isoformat())
        level = event_dict.pop("level", method)
        event = event_dict.pop("event", "")

        output: dict[str, Any] = {
            "ts": ts,
            "level": level,
            "event": event,
        }
        # Append all remaining context keys in sorted order for readability
        for k in sorted(event_dict.keys()):
            output[k] = event_dict[k]

        return json.dumps(output, default=str, ensure_ascii=False)


# ── Layer-aware log filter ─────────────────────────────────────────────────────

class LayerFilter(logging.Filter):
    """Only pass records whose logger name matches a given layer prefix."""

    def __init__(self, prefixes: list[str]) -> None:
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return any(record.name.startswith(p) for p in self.prefixes)


class ErrorFilter(logging.Filter):
    """Only pass ERROR and CRITICAL records."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.ERROR


class SQLFilter(logging.Filter):
    """Filter out raw SQL engine noise — only show in debug mode."""

    def __init__(self, debug_sql: bool = False) -> None:
        super().__init__()
        self.debug_sql = debug_sql

    def filter(self, record: logging.LogRecord) -> bool:
        is_sql = record.name.startswith("sqlalchemy")
        if is_sql and not self.debug_sql:
            return False
        return True


# ── Main setup ────────────────────────────────────────────────────────────────

def setup_logging(log_name: str = "parikrama", debug_sql: bool = False) -> None:
    """
    Configure PariKrama's structured logging.

    Outputs:
      - Console  : coloured dev output (structlog ConsoleRenderer)
      - logs/parikrama.log     : ALL events as clean JSON (rotating 10 MB × 5)
      - logs/errors.log        : ERROR+ only, JSON
      - logs/api_requests.log  : HTTP layer events
      - logs/agents.log        : LangGraph agent events
      - logs/auth.log          : Auth events
      - logs/database.log      : SQLAlchemy (if debug_sql=True or DB_LOG=true env)
    """
    import os
    debug_sql = debug_sql or os.getenv("DB_LOG", "false").lower() == "true"

    # ── Directories ────────────────────────────────────────────────────────
    # logger.py path: <root>/apps/backend/src/parikrama/core/logger.py
    #                  [0]   [1]     [2]  [3]      [4]   [5]
    # parents[5] → project root  → then "apps/logs"
    project_root = Path(__file__).resolve().parents[5]
    logs_dir = project_root / "apps" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # ── Determine log level from env ──────────────────────────────────────
    from parikrama.config import settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # ── Helper to build a rotating file handler ───────────────────────────
    def _rotating(filename: str, max_mb: int = 10, backups: int = 5) -> logging.Handler:
        h = logging.handlers.RotatingFileHandler(
            filename=logs_dir / filename,
            maxBytes=max_mb * 1024 * 1024,
            backupCount=backups,
            encoding="utf-8",
        )
        h.setFormatter(logging.Formatter("%(message)s"))
        return h

    # ── Console handler (coloured for humans in terminal) ─────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # ── ALL events → parikrama.log (clean JSON) ───────────────────────────
    all_handler = _rotating("parikrama.log")
    all_handler.addFilter(SQLFilter(debug_sql))

    # ── Errors only → errors.log ──────────────────────────────────────────
    error_handler = _rotating("errors.log", max_mb=5)
    error_handler.addFilter(ErrorFilter())

    # ── API layer → api_requests.log ─────────────────────────────────────
    api_handler = _rotating("api_requests.log", max_mb=20)
    api_handler.addFilter(LayerFilter(["parikrama.core.middleware", "parikrama.api"]))

    # ── Agent layer → agents.log ──────────────────────────────────────────
    agent_handler = _rotating("agents.log", max_mb=20)
    agent_handler.addFilter(LayerFilter([
        "parikrama.agents", "parikrama.services.async_planner",
        "parikrama.llm",
    ]))

    # ── Auth layer → auth.log ─────────────────────────────────────────────
    auth_handler = _rotating("auth.log", max_mb=5)
    auth_handler.addFilter(LayerFilter([
        "parikrama.services.auth_service", "parikrama.core.security",
        "parikrama.api.v1.auth",
    ]))

    # ── Database layer → database.log (only if debug_sql) ─────────────────
    db_handler = _rotating("database.log", max_mb=50, backups=2)
    db_handler.addFilter(LayerFilter(["sqlalchemy"]))

    # ── Root stdlib logger ─────────────────────────────────────────────────
    root_handlers: list[logging.Handler] = [
        console_handler,
        all_handler,
        error_handler,
        api_handler,
        agent_handler,
        auth_handler,
    ]
    if debug_sql:
        root_handlers.append(db_handler)

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=root_handlers,
        force=True,  # override any existing config
    )

    # Silence noisy SQLAlchemy engine logs unless debug_sql
    if not debug_sql:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)

    # Silence uvicorn access spam (we have our own middleware)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # ── Structlog configuration ────────────────────────────────────────────
    # Console: coloured for dev, plain JSON for production
    if settings.APP_ENV == "production":
        renderer = PariKramaJSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,        # correlation_id, etc.
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.CallsiteParameterAdder(
                [structlog.processors.CallsiteParameter.FUNC_NAME]
            ),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── Startup banner ─────────────────────────────────────────────────────
    import structlog as sl
    log = sl.get_logger("parikrama.core.logger")
    log.info(
        "logging_initialized",
        layer="SYSTEM",
        logs_dir=str(logs_dir),
        log_level=settings.LOG_LEVEL,
        files=[
            "parikrama.log (ALL)",
            "errors.log (ERRORS)",
            "api_requests.log (HTTP)",
            "agents.log (AI pipeline)",
            "auth.log (Auth)",
            f"database.log (SQL {'ENABLED' if debug_sql else 'DISABLED — set DB_LOG=true'})",
        ],
    )
