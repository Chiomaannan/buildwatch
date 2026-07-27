"""
celery_app.py — Celery application factory.

Workers are started via:
    celery -A app.tasks.celery_app worker --loglevel=info -Q inference
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "aic_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.inference",
        "app.tasks.worker_monitor",
        "app.tasks.plan_analyzer",
        "app.tasks.report_sender",
    ],
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
        # No dedicated queue for this — it's light and infrequent, so it
        # rides along on the existing inference worker rather than needing
        # its own consumer process.
        "app.tasks.report_sender.*": {"queue": "inference"},
    },
    task_track_started=True,
    result_expires=86400,                # keep results for 24 hours
    # Ghana (Africa/Accra) is UTC+0 year-round, no DST — hour=8 here is
    # already 8am local time, no conversion needed.
    beat_schedule={
        "send-weekly-whatsapp-reports": {
            "task": "app.tasks.report_sender.send_weekly_reports",
            "schedule": crontab(day_of_week="monday", hour=8, minute=0),
        },
    },
)
