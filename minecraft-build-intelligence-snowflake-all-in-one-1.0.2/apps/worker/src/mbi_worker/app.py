from __future__ import annotations

import os

try:
    from celery import Celery  # type: ignore
except ImportError:  # development/test fallback, never production
    from .compat import InlineCelery as Celery

celery_app = Celery(
    "mbi",
    broker=os.getenv("MBI_REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("MBI_REDIS_URL", "redis://localhost:6379/0"),
    include=["mbi_worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=1800,
    task_soft_time_limit=1740,
    broker_connection_retry_on_startup=True,
)
