"""
schedule.py — Plan vs Actual schedule endpoints.

POST  /api/v1/projects/{id}/schedule    Set (replace) the project schedule
GET   /api/v1/projects/{id}/schedule    Get the planned schedule
GET   /api/v1/projects/{id}/comparison  Planned vs actual MWPI per milestone
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import Image, InferenceResult
from app.models.project import Project
from app.models.schedule import ScheduleMilestone
from app.schemas.schedule import ComparisonEntry, ComparisonOut, MilestoneIn, MilestoneOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/projects", tags=["Schedule"])

# ── deviation thresholds (MWPI units) ─────────────────────────────────────────
_ON_SCHEDULE     =  0.0
_SLIGHTLY_BEHIND = -0.10


def _deviation_status(deviation: float) -> str:
    if deviation >= _ON_SCHEDULE:
        return "ON_SCHEDULE"
    if deviation >= _SLIGHTLY_BEHIND:
        return "SLIGHTLY_BEHIND"
    return "DELAYED"


# ── helpers ────────────────────────────────────────────────────────────────────

def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return p


# ── endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/{project_id}/schedule",
    response_model=list[MilestoneOut],
    status_code=status.HTTP_201_CREATED,
)
def set_schedule(
    project_id: str,
    milestones: list[MilestoneIn],
    db: Session = Depends(get_db),
):
    """
    Replace the entire schedule for a project.
    Existing milestones are deleted and replaced with the new list.
    """
    _get_project_or_404(db, project_id)

    if not milestones:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Schedule must contain at least one milestone.",
        )

    # Validate week_number uniqueness within the submitted list
    week_numbers = [m.week_number for m in milestones]
    if len(week_numbers) != len(set(week_numbers)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="week_number must be unique within a schedule.",
        )

    # Validate planned_mwpi is non-decreasing (construction only moves forward)
    sorted_ms = sorted(milestones, key=lambda m: m.week_number)
    for i in range(1, len(sorted_ms)):
        if sorted_ms[i].planned_mwpi < sorted_ms[i - 1].planned_mwpi:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"planned_mwpi must be non-decreasing: "
                    f"week {sorted_ms[i].week_number} ({sorted_ms[i].planned_mwpi}) "
                    f"< week {sorted_ms[i-1].week_number} ({sorted_ms[i-1].planned_mwpi})"
                ),
            )

    db.query(ScheduleMilestone).filter(
        ScheduleMilestone.project_id == project_id
    ).delete()

    rows = [
        ScheduleMilestone(
            project_id=project_id,
            week_number=m.week_number,
            planned_date=m.planned_date,
            planned_mwpi=m.planned_mwpi,
            label=m.label,
        )
        for m in milestones
    ]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)

    logger.info(f"Schedule set for project {project_id}: {len(rows)} milestones")
    return rows


@router.get("/{project_id}/schedule", response_model=list[MilestoneOut])
def get_schedule(project_id: str, db: Session = Depends(get_db)):
    """Return the planned schedule milestones ordered by week."""
    _get_project_or_404(db, project_id)
    return (
        db.query(ScheduleMilestone)
        .filter(ScheduleMilestone.project_id == project_id)
        .order_by(ScheduleMilestone.week_number)
        .all()
    )


@router.get("/{project_id}/comparison", response_model=ComparisonOut)
def get_comparison(project_id: str, db: Session = Depends(get_db)):
    """
    Return planned vs actual MWPI for every scheduled milestone.

    For each milestone date, the actual MWPI is taken from the latest
    InferenceResult whose processed_at date is <= that milestone's planned_date.
    Future milestones with no data yet are marked PENDING.
    """
    _get_project_or_404(db, project_id)

    milestones = (
        db.query(ScheduleMilestone)
        .filter(ScheduleMilestone.project_id == project_id)
        .order_by(ScheduleMilestone.week_number)
        .all()
    )

    if not milestones:
        return ComparisonOut(project_id=project_id, milestones=[], overall_status="PENDING")

    # Fetch all completed inference results for this project, ordered by capture time
    all_results = (
        db.query(InferenceResult)
        .join(Image, InferenceResult.image_id == Image.id)
        .filter(
            InferenceResult.project_id == project_id,
            InferenceResult.mwpi_score.isnot(None),
        )
        .order_by(desc(Image.captured_at))
        .all()
    )

    today = date.today().isoformat()
    entries: list[ComparisonEntry] = []
    last_status = "PENDING"

    for m in milestones:
        # Find the latest inference result captured on or before the milestone date
        actual_result = next(
            (
                r for r in all_results
                if r.image.captured_at[:10] <= m.planned_date
            ),
            None,
        )

        if actual_result is None:
            # No data at all yet for this milestone date
            entry_status = "PENDING" if m.planned_date > today else "DELAYED"
            entries.append(
                ComparisonEntry(
                    week_number=m.week_number,
                    planned_date=m.planned_date,
                    planned_mwpi=m.planned_mwpi,
                    label=m.label,
                    actual_mwpi=None,
                    deviation=None,
                    status=entry_status,
                )
            )
        else:
            actual = round(actual_result.mwpi_score, 4)
            deviation = round(actual - m.planned_mwpi, 4)
            entry_status = _deviation_status(deviation)
            last_status = entry_status
            entries.append(
                ComparisonEntry(
                    week_number=m.week_number,
                    planned_date=m.planned_date,
                    planned_mwpi=m.planned_mwpi,
                    label=m.label,
                    actual_mwpi=actual,
                    deviation=deviation,
                    status=entry_status,
                )
            )

    return ComparisonOut(
        project_id=project_id,
        milestones=entries,
        overall_status=last_status,
    )
