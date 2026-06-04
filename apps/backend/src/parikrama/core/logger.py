import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

from parikrama.config import settings


def setup_logging(log_name: str = "parikrama") -> None:
    """
    Configures a robust, structured logging system.
    Logs are written both to the console (for dev) and to a rotating file
    in the `logs/` directory at the project root for management.
    """
    # Create logs directory at project root if it doesn't exist
    # Assuming this runs from apps/backend/src/parikrama/core/logger.py
    # Root is 4 levels up
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / f"{log_name}.log"

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # 1. Setup standard logging handlers
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # Rotating file handler (10 MB max size, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    # File formatter can be standard string or JSON. We'll use structlog's console renderer for readability
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[console_handler, file_handler],
    )

    # 2. Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            # For human readability in files and console
            structlog.dev.ConsoleRenderer(colors=False)
            if settings.APP_ENV == "production"
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
