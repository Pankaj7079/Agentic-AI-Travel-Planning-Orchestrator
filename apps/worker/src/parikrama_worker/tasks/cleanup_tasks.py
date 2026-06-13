"""
Scheduled cleanup tasks for approval timeout and data hygiene.

expire_pending_approvals():
    Runs every 5 minutes via Celery Beat.
    Marks overdue approval_requests as 'expired' and cancels their trips.
    This prevents trips from being stuck in 'awaiting_approval' forever.

Note: This task uses a synchronous DB session (SQLAlchemy core) because
Celery workers run in a sync context. The async session from FastAPI is
not available here.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import structlog

from parikrama_worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

# DB URL from environment — same as backend
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://parikrama:parikrama_dev_2024@localhost:5432/parikrama",
).replace("asyncpg", "psycopg2")  # sync driver for Celery


def _get_sync_engine():
    """Create a synchronous SQLAlchemy engine for Celery tasks."""
    from sqlalchemy import create_engine

    return create_engine(DATABASE_URL, pool_pre_ping=True)


@celery_app.task(name="parikrama_worker.tasks.cleanup_tasks.expire_pending_approvals")
def expire_pending_approvals() -> dict:
    """
    Expire approval requests that have passed their deadline.

    Run by Celery Beat every 5 minutes. Marks expired approvals and
    cancels the associated trips.

    Returns:
        Dict with expired_count.
    """
    from sqlalchemy import select, update
    from sqlalchemy.orm import Session

    engine = _get_sync_engine()
    now = datetime.now(UTC)
    count = 0

    try:
        with Session(engine) as db:
            # Import models inside task to avoid circular imports
            # (backend package must be on Python path for the worker)
            try:
                from parikrama.models.approval import ApprovalRequest
                from parikrama.models.trip import Trip
                from parikrama_common.enums import ApprovalStatus, TripStatus
            except ImportError:
                logger.warning(
                    "cleanup_task_models_unavailable",
                    note="Backend package not in worker Python path",
                )
                return {"expired_count": 0, "error": "models_unavailable"}

            # Find all pending approvals past their deadline
            result = db.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.expires_at < now,
                )
            )
            expired = result.scalars().all()

            for approval in expired:
                approval.status = ApprovalStatus.EXPIRED
                approval.responded_at = now

                # Cancel the associated trip
                db.execute(
                    update(Trip)
                    .where(Trip.id == approval.trip_id)
                    .values(status=TripStatus.CANCELLED)
                )
                count += 1

            db.commit()

        if count > 0:
            logger.info("approvals_expired_by_celery", count=count, now=now.isoformat())

    except Exception as exc:
        logger.error("expire_pending_approvals_failed", error=str(exc))
        return {"expired_count": 0, "error": str(exc)}
    finally:
        engine.dispose()

    return {"expired_count": count}
