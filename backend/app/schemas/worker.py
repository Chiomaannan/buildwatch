"""
worker.py — Pydantic schemas for Worker Activity Monitoring endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ── WorkShift ─────────────────────────────────────────────────────────────────

class WorkShiftIn(BaseModel):
    contracted_start: str = Field(..., pattern=r"^\d{2}:\d{2}$", examples=["08:00"])
    contracted_end: str = Field(..., pattern=r"^\d{2}:\d{2}$", examples=["17:00"])
    expected_headcount: int = Field(..., ge=1, le=500)
    late_start_grace_minutes: int = Field(30, ge=0, le=120)


class WorkShiftOut(BaseModel):
    id: str
    project_id: str
    contracted_start: str
    contracted_end: str
    expected_headcount: int
    late_start_grace_minutes: int
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── WorkerPresenceReading ─────────────────────────────────────────────────────

class PresenceReadingOut(BaseModel):
    id: str
    project_id: str
    shift_id: str | None
    image_id: str | None
    worker_count: int
    captured_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── WorkerAlert ───────────────────────────────────────────────────────────────

class WorkerAlertOut(BaseModel):
    id: str
    project_id: str
    shift_id: str | None
    alert_type: str
    severity: str
    message: str
    worker_count: int | None
    triggered_at: datetime
    resolved: bool
    resolved_at: datetime | None

    model_config = {"from_attributes": True}
