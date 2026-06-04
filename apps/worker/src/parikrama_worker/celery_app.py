"""
Celery application configuration.

Central broker (Redis), task discovery, and beat schedule.
"""

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "parikrama",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,           # 10 min hard limit
    task_soft_time_limit=540,      # 9 min soft limit
    worker_prefetch_multiplier=1,  # fair scheduling
    task_routes={
        "parikrama_worker.tasks.document_tasks.*": {"queue": "documents"},
        "parikrama_worker.tasks.embedding_tasks.*": {"queue": "embeddings"},
        "parikrama_worker.tasks.email_tasks.*": {"queue": "notifications"},
        "parikrama_worker.tasks.cleanup_tasks.*": {"queue": "default"},
    },
)

# auto-discover tasks from the tasks package
celery_app.autodiscover_tasks(["parikrama_worker.tasks"])

# beat schedule — recurring tasks
celery_app.conf.beat_schedule = {
    "expire-pending-approvals": {
        "task": "parikrama_worker.tasks.cleanup_tasks.expire_pending_approvals",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
}
