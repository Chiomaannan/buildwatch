"""
worker.py — Worker Activity Monitoring API router.

Endpoints:
  POST   /api/v1/projects/{project_id}/shifts          — create/replace active shift
  GET    /api/v1/projects/{project_id}/shifts          — get active shift
  GET    /api/v1/projects/{project_id}/worker-alerts   — list worker alerts (filterable)
  PATCH  /api/v1/worker-alerts/{alert_id}/resolve      — resolve an alert
  GET    /api/v1/projects/{project_id}/presence        — recent presence readings
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.project import Project
from app.models.worker import WorkShift, WorkerAlert, WorkerPresenceReading
from app.schemas.worker import (
    PresenceReadingOut,
    WorkerAlertOut,
    WorkShiftIn,
    WorkShiftOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Worker Monitoring"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return p


# ── Shifts ────────────────────────────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/shifts",
    response_model=WorkShiftOut,
    status_code=status.HTTP_201_CREATED,
)
def create_shift(
    project_id: str,
    payload: WorkShiftIn,
    db: Session = Depends(get_db),
):
    """
    Create (or replace) the active work shift for a project.
    Deactivates any existing active shifts before creating the new one.
    """
    _get_project_or_404(db, project_id)

    db.query(WorkShift).filter(
        WorkShift.project_id == project_id,
        WorkShift.active.is_(True),
    ).update({"active": False})

    shift = WorkShift(
        project_id=project_id,
        contracted_start=payload.contracted_start,
        contracted_end=payload.contracted_end,
        expected_headcount=payload.expected_headcount,
        late_start_grace_minutes=payload.late_start_grace_minutes,
        active=True,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    logger.info(
        f"WorkShift created — project={project_id} "
        f"{payload.contracted_start}–{payload.contracted_end} "
        f"headcount={payload.expected_headcount}"
    )
    return shift


@router.get("/projects/{project_id}/shifts", response_model=WorkShiftOut | None)
def get_active_shift(project_id: str, db: Session = Depends(get_db)):
    """Return the currently active shift for the project, or null if none configured."""
    _get_project_or_404(db, project_id)
    return (
        db.query(WorkShift)
        .filter(WorkShift.project_id == project_id, WorkShift.active.is_(True))
        .order_by(desc(WorkShift.created_at))
        .first()
    )


# ── Worker Alerts ─────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/worker-alerts", response_model=list[WorkerAlertOut])
def list_worker_alerts(
    project_id: str,
    resolved: bool | None = Query(None, description="Filter by resolved status"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List worker activity alerts for a project, newest first."""
    _get_project_or_404(db, project_id)
    q = db.query(WorkerAlert).filter(WorkerAlert.project_id == project_id)
    if resolved is not None:
        q = q.filter(WorkerAlert.resolved.is_(resolved))
    return q.order_by(desc(WorkerAlert.triggered_at)).limit(limit).all()


@router.patch("/worker-alerts/{alert_id}/resolve", response_model=WorkerAlertOut)
def resolve_worker_alert(alert_id: str, db: Session = Depends(get_db)):
    """Mark a worker alert as resolved."""
    alert = db.query(WorkerAlert).filter(WorkerAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    if alert.resolved:
        return alert
    alert.resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert


# ── Presence Readings ─────────────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/presence",
    response_model=list[PresenceReadingOut],
)
def list_presence_readings(
    project_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Return recent worker presence readings for a project, newest first."""
    _get_project_or_404(db, project_id)
    return (
        db.query(WorkerPresenceReading)
        .filter(WorkerPresenceReading.project_id == project_id)
        .order_by(desc(WorkerPresenceReading.captured_at))
        .limit(limit)
        .all()
    )
