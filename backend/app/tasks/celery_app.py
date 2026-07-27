"""
celery_app.py — Celery application factory.

Workers are started via:
    celery -A app.tasks.celery_app worker --loglevel=info -Q inference
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "aic_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.inference", "app.tasks.worker_monitor", "app.tasks.plan_analyzer"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,                 # retry if worker crashes mid-task
    worker_prefetch_multiplier=1,        # one task at a time (AI is heavy)
    task_routes={
        "app.tasks.inference.*": {"queue": "inference"},
    },
    task_track_started=True,
    result_expires=86400,                # keep results for 24 hours
)
