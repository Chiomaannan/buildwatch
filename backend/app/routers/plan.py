"""
plan.py — Building plan upload and retrieval endpoints.

POST /api/v1/projects/{project_id}/plan   Upload a building plan image
GET  /api/v1/projects/{project_id}/plan   Get the current plan + analysis status
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.plan import ProjectPlan
from app.schemas.plan import PlanOut
from app.services.minio_client import get_presigned_url, upload_bytes
from app.tasks.plan_analyzer import analyze_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/projects", tags=["Plan"])
settings = get_settings()


@router.post("/{project_id}/plan", response_model=PlanOut)
async def upload_plan(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a building plan image (photo, architectural render, floor plan).
    Queues background analysis to extract site-specific MWPI weights and
    expected structural element counts.
    Replaces any previously uploaded plan for this project.
    """
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    # Infer extension
    ext = "jpg"
    if file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() or "jpg"
    if ext not in {"jpg", "jpeg", "png", "gif", "webp"}:
        ext = "jpg"

    plan_id   = str(uuid.uuid4())
    obj_path  = f"plans/{project_id}/{plan_id}.{ext}"

    # Store in MinIO (reuse the raw-images bucket)
    upload_bytes(
        bucket=settings.minio_raw_bucket,
        object_name=obj_path,
        data=raw_bytes,
    )

    # Deactivate any existing plan for this project
    db.query(ProjectPlan).filter(
        ProjectPlan.project_id == project_id
    ).delete(synchronize_session=False)

    plan = ProjectPlan(
        id=plan_id,
        project_id=project_id,
        plan_image_path=obj_path,
        analysis_status="pending",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    # Queue analysis task
    analyze_plan.apply_async(args=[plan_id], queue="inference")
    logger.info(f"Plan uploaded — project={project_id} plan={plan_id} queued for analysis")

    return _enrich(plan)


@router.get("/{project_id}/plan", response_model=PlanOut)
def get_plan(project_id: str, db: Session = Depends(get_db)):
    """Return the current building plan and its analysis results."""
    plan = (
        db.query(ProjectPlan)
        .filter(ProjectPlan.project_id == project_id)
        .order_by(ProjectPlan.created_at.desc())
        .first()
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No building plan uploaded for this project",
        )
    return _enrich(plan)


def _enrich(plan: ProjectPlan) -> dict:
    plan_image_url = None
    if plan.plan_image_path:
        try:
            plan_image_url = get_presigned_url(settings.minio_raw_bucket, plan.plan_image_path)
        except Exception:
            pass
    return {
        "id":               plan.id,
        "project_id":       plan.project_id,
        "plan_image_url":   plan_image_url,
        "plan_weights":     plan.plan_weights,
        "expected_counts":  plan.expected_counts,
        "analysis_status":  plan.analysis_status,
        "analysis_notes":   plan.analysis_notes,
        "created_at":       plan.created_at,
        "updated_at":       plan.updated_at,
    }
