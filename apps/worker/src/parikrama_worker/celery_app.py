"""
Celery application configuration.
"""

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

from celery.signals import setup_logging as celery_setup_logging


@celery_setup_logging.connect
def configure_celery_logging(**kwargs):
    try:
        from parikrama.core.logger import setup_logging

        setup_logging(log_name="worker")
    except ImportError:
        pass  # Fails gracefully if backend isn't in Python path


celery_app = Celery("parikrama", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_routes={
        "parikrama_worker.tasks.document_tasks.*": {"queue": "documents"},
        "parikrama_worker.tasks.embedding_tasks.*": {"queue": "embeddings"},
        "parikrama_worker.tasks.email_tasks.*": {"queue": "notifications"},
        "parikrama_worker.tasks.cleanup_tasks.*": {"queue": "default"},
        "parikrama_worker.tasks.trip_tasks.*": {"queue": "trips"},
    },
)

celery_app.autodiscover_tasks(["parikrama_worker.tasks"])

celery_app.conf.beat_schedule = {
    "expire-pending-approvals": {
        "task": "parikrama_worker.tasks.cleanup_tasks.expire_pending_approvals",
        "schedule": crontab(minute="*/5"),
    },
}
