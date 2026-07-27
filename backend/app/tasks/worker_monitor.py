"""
worker_monitor.py — Celery task: worker detection + activity alert generation.

Triggered when an image is uploaded with metadata.capture_type == "presence_check".

Pipeline:
  1. Download raw image from MinIO
  2. Count workers (buildwatch_best.pt "worker" class, or mock)
  3. Store WorkerPresenceReading
  4. Load active WorkShift for the project
  5. Evaluate alert conditions (LATE_START, LOW_PRESENCE, EARLY_DEPARTURE)
  6. Create WorkerAlert records for any new conditions
  7. Publish WebSocket event
"""

import json
import logging
import random
import time
from datetime import datetime, timezone

from sqlalchemy import desc

import cv2
import numpy as np
import redis

from app.config import get_settings
from app.database import SessionLocal
from app.models.image import Image
from app.models.worker import WorkShift, WorkerAlert, WorkerPresenceReading
from app.services.minio_client import download_to_bytes
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

_WORKER_CONFIDENCE = 0.40


def _count_workers_mock(image_bgr: np.ndarray) -> int:
    """Return a plausible random worker count for testing without real YOLO."""
    return random.randint(0, 6)


def _count_workers(image_bgr: np.ndarray) -> int:
    if settings.mock_inference:
        count = _count_workers_mock(image_bgr)
        logger.info(f"MOCK worker detection: {count} worker(s)")
        return count
    from app.services.ai.detector import count_workers
    return count_workers(image_bgr, confidence=_WORKER_CONFIDENCE)


def _active_shift(db, project_id: str) -> WorkShift | None:
    return (
        db.query(WorkShift)
        .filter(WorkShift.project_id == project_id, WorkShift.active.is_(True))
        .order_by(WorkShift.created_at.desc())
        .first()
    )


def _within_work_hours(shift: WorkShift, now: datetime) -> bool:
    """Return True if `now` (UTC) falls within the shift's contracted hours (naive comparison)."""
    time_str = now.strftime("%H:%M")
    return shift.contracted_start <= time_str <= shift.contracted_end


def _minutes_past_start(shift: WorkShift, now: datetime) -> int:
    """Minutes elapsed since contracted_start. Negative if before start."""
    sh, sm = map(int, shift.contracted_start.split(":"))
    start_mins = sh * 60 + sm
    now_mins = now.hour * 60 + now.minute
    return now_mins - start_mins


def _minutes_to_end(shift: WorkShift, now: datetime) -> int:
    """Minutes until contracted_end. Negative if past end."""
    eh, em = map(int, shift.contracted_end.split(":"))
    end_mins = eh * 60 + em
    now_mins = now.hour * 60 + now.minute
    return end_mins - now_mins


def _alert_already_fired_today(
    db, project_id: str, alert_type: str, today_start: datetime
) -> bool:
    """Prevent duplicate alerts of the same type on the same calendar day."""
    return (
        db.query(WorkerAlert)
        .filter(
            WorkerAlert.project_id == project_id,
            WorkerAlert.alert_type == alert_type,
            WorkerAlert.triggered_at >= today_start,
        )
        .first()
    ) is not None


def _consecutive_low_readings(db, project_id: str, condition_fn, n: int = 2) -> bool:
    """
    Return True only if the last `n` presence readings ALL satisfy condition_fn.
    Prevents single-snapshot false positives (e.g. workers on a break).
    Returns False if fewer than `n` readings exist yet.
    """
    recent = (
        db.query(WorkerPresenceReading)
        .filter(WorkerPresenceReading.project_id == project_id)
        .order_by(desc(WorkerPresenceReading.captured_at))
        .limit(n)
        .all()
    )
    if len(recent) < n:
        return False
    return all(condition_fn(r) for r in recent)


def _evaluate_alerts(
    db,
    project_id: str,
    shift: WorkShift,
    worker_count: int,
    now: datetime,
) -> list[WorkerAlert]:
    """Check all alert conditions and return any new WorkerAlert objects to persist."""
    from datetime import timezone as tz

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fired: list[WorkerAlert] = []

    mins_past_start = _minutes_past_start(shift, now)
    mins_to_end = _minutes_to_end(shift, now)
    in_hours = _within_work_hours(shift, now)

    # ── LATE_START ──────────────────────────────────────────────────────────
    # Fires once when we're past the grace window and still no workers on site.
    # Requires 2 consecutive zero-worker readings to avoid break-time false positives.
    if (
        mins_past_start >= shift.late_start_grace_minutes
        and mins_past_start < shift.late_start_grace_minutes + 60  # only in the first hour
        and worker_count == 0
        and not _alert_already_fired_today(db, project_id, "LATE_START", today_start)
        and _consecutive_low_readings(db, project_id, lambda r: r.worker_count == 0)
    ):
        fired.append(WorkerAlert(
            project_id=project_id,
            shift_id=shift.id,
            alert_type="LATE_START",
            severity="warning",
            message=(
                f"No workers detected {mins_past_start} minutes after contracted start "
                f"({shift.contracted_start}). Grace period of "
                f"{shift.late_start_grace_minutes} min has elapsed."
            ),
            worker_count=worker_count,
        ))

    # ── LOW_PRESENCE ────────────────────────────────────────────────────────
    # Fires once per day when headcount drops below 50% of expected during work hours.
    # Requires 2 consecutive low readings to avoid break-time false positives.
    threshold = max(1, shift.expected_headcount // 2)
    if (
        in_hours
        and worker_count < threshold
        and not _alert_already_fired_today(db, project_id, "LOW_PRESENCE", today_start)
        and _consecutive_low_readings(
            db, project_id, lambda r: r.worker_count < threshold
        )
    ):
        fired.append(WorkerAlert(
            project_id=project_id,
            shift_id=shift.id,
            alert_type="LOW_PRESENCE",
            severity="critical",
            message=(
                f"Only {worker_count} worker(s) detected on site during contracted hours. "
                f"Expected at least {threshold} (50% of {shift.expected_headcount}). "
                f"Captured at {now.strftime('%H:%M')}."
            ),
            worker_count=worker_count,
        ))

    # ── EARLY_DEPARTURE ─────────────────────────────────────────────────────
    # Fires once per day when count drops to 0 with more than 60 min left in the shift.
    # Requires 2 consecutive zero-worker readings to avoid break-time false positives.
    if (
        in_hours
        and mins_to_end > 60
        and worker_count == 0
        and not _alert_already_fired_today(db, project_id, "EARLY_DEPARTURE", today_start)
        and _consecutive_low_readings(db, project_id, lambda r: r.worker_count == 0)
    ):
        fired.append(WorkerAlert(
            project_id=project_id,
            shift_id=shift.id,
            alert_type="EARLY_DEPARTURE",
            severity="critical",
            message=(
                f"No workers detected on site with {mins_to_end} minutes remaining "
                f"in the contracted shift (ends {shift.contracted_end}). "
                f"Possible early departure or site abandonment."
            ),
            worker_count=worker_count,
        ))

    return fired


def _publish_worker_event(project_id: str, event: dict) -> None:
    try:
        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.publish(f"project:{project_id}:events", json.dumps(event))
        r.close()
    except Exception as exc:
        logger.warning(f"Redis publish failed (non-fatal): {exc}")


@celery_app.task(
    name="app.tasks.worker_monitor.run_presence_check",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_presence_check(self, image_id: str) -> dict:
    """
    Presence check task — dispatched for images with capture_type='presence_check'.

    Counts workers, stores a WorkerPresenceReading, evaluates alert conditions
    against the project's active WorkShift, and fires WorkerAlerts as needed.
    """
    db = SessionLocal()
    try:
        image: Image | None = db.query(Image).filter(Image.id == image_id).first()
        if image is None:
            logger.error(f"Presence check: image {image_id} not found")
            return {"status": "error", "reason": "image not found"}

        image.status = "processing"
        db.commit()

        # ── Download + decode ─────────────────────────────────────────────
        raw_bytes = download_to_bytes(
            bucket=settings.minio_raw_bucket,
            object_name=image.raw_storage_path,
        )
        img_array = np.frombuffer(raw_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise ValueError("Could not decode image bytes")

        # ── Worker count ──────────────────────────────────────────────────
        worker_count = _count_workers(img_bgr)
        now = datetime.now(timezone.utc)

        # ── Store reading ─────────────────────────────────────────────────
        shift = _active_shift(db, image.project_id)
        reading = WorkerPresenceReading(
            project_id=image.project_id,
            shift_id=shift.id if shift else None,
            image_id=image_id,
            worker_count=worker_count,
            captured_at=now,
        )
        db.add(reading)
        image.status = "completed"
        db.commit()

        logger.info(
            f"Presence check done — image={image_id} "
            f"workers={worker_count} shift={'yes' if shift else 'none'}"
        )

        # ── Alert evaluation ──────────────────────────────────────────────
        new_alerts: list = []
        if shift:
            new_alerts = _evaluate_alerts(db, image.project_id, shift, worker_count, now)
            for alert in new_alerts:
                db.add(alert)
            if new_alerts:
                db.commit()
                logger.info(
                    f"Fired {len(new_alerts)} worker alert(s): "
                    f"{[a.alert_type for a in new_alerts]}"
                )

        # ── WebSocket event ───────────────────────────────────────────────
        _publish_worker_event(
            image.project_id,
            {
                "event": "worker_presence",
                "project_id": image.project_id,
                "image_id": image_id,
                "worker_count": worker_count,
                "alerts_fired": [a.alert_type for a in new_alerts],
                "timestamp": now.isoformat(),
            },
        )

        return {
            "status": "completed",
            "image_id": image_id,
            "worker_count": worker_count,
            "alerts_fired": [a.alert_type for a in new_alerts],
        }

    except Exception as exc:
        logger.exception(f"Presence check failed for image {image_id}: {exc}")
        try:
            img = db.query(Image).filter(Image.id == image_id).first()
            if img:
                img.status = "failed"
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc)

    finally:
        db.close()
