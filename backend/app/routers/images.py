"""
images.py — Image retrieval and analytics endpoints.

GET  /api/v1/images                      List images (filter by project, status)
GET  /api/v1/images/{id}                 Get single image with inference result
GET  /api/v1/images/{id}/status          Lightweight status poll
GET  /api/v1/projects/{id}/progress      Latest progress summary for dashboard
GET  /api/v1/projects/{id}/timeline      Progress over time (for charts)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.image import Image, InferenceResult
from app.schemas.image import ImageOut, InferenceResultOut
from app.services.ai.progress import avg_confidence
from app.services.minio_client import get_presigned_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Images"])
settings = get_settings()


@router.get("/images", response_model=list[ImageOut])
def list_images(
    project_id: str | None = Query(None),
    device_id: str | None = Query(None),
    image_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Image)
    if project_id:
        query = query.filter(Image.project_id == project_id)
    if device_id:
        query = query.filter(Image.device_id == device_id)
    if image_status:
        query = query.filter(Image.status == image_status)

    # Exclude presence-check images — these are for worker monitoring only,
    # not for the Gallery or any MWPI-facing surface.
    ct = func.json_extract_path_text(Image.image_metadata, 'capture_type')
    query = query.filter(
        or_(
            Image.image_metadata.is_(None),
            ct.is_(None),
            ct != 'presence_check',
        )
    )

    images = query.order_by(desc(Image.uploaded_at)).offset(offset).limit(limit).all()
    return [_enrich_image(img) for img in images]


@router.get("/images/{image_id}", response_model=ImageOut)
def get_image(image_id: str, db: Session = Depends(get_db)):
    img = _get_image_or_404(db, image_id)
    return _enrich_image(img)


@router.get("/images/{image_id}/status")
def get_image_status(image_id: str, db: Session = Depends(get_db)) -> dict:
    img = _get_image_or_404(db, image_id)
    return {
        "image_id": img.id,
        "status": img.status,
        "has_result": img.inference_result is not None,
        "progress_percentage": (
            img.inference_result.progress_percentage
            if img.inference_result
            else None
        ),
    }


@router.get("/projects/{project_id}/progress")
def get_project_progress(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Return the latest inference result for the project.
    Used by the dashboard's main progress card.
    """
    latest_result = (
        db.query(InferenceResult)
        .join(Image, Image.id == InferenceResult.image_id)
        .filter(InferenceResult.project_id == project_id)
        .filter(InferenceResult.progress_percentage.isnot(None))
        .filter(
            or_(
                Image.image_metadata.is_(None),
                func.json_extract_path_text(Image.image_metadata, 'capture_type').is_(None),
                func.json_extract_path_text(Image.image_metadata, 'capture_type') != 'presence_check',
            )
        )
        .order_by(desc(InferenceResult.processed_at))
        .first()
    )

    if not latest_result:
        return {
            "project_id": project_id,
            "mwpi_score": None,
            "progress_percentage": None,
            "detected_classes": [],
            "component_counts": {},
            "component_progress": {},
            "avg_confidence": None,
            "message": "No completed inference results yet.",
        }

    conf = avg_confidence(latest_result.yolo_detections or [])

    return {
        "project_id": project_id,
        "image_id": latest_result.image_id,
        "mwpi_score": latest_result.mwpi_score,
        "progress_percentage": latest_result.progress_percentage,
        "detected_classes": latest_result.detected_classes or [],
        "component_counts": latest_result.component_counts or {},
        "component_progress": latest_result.component_progress or {},
        "avg_confidence": conf,
        "processed_at": latest_result.processed_at.isoformat(),
        "explanation": latest_result.explanation,
        "annotated_image_url": _annotated_url(latest_result.annotated_image_path),
    }


@router.get("/projects/{project_id}/timeline")
def get_project_timeline(
    project_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Return a time-series of progress percentages for charting.
    Each entry corresponds to one processed image.
    """
    results = (
        db.query(
            InferenceResult.processed_at,
            InferenceResult.progress_percentage,
            InferenceResult.image_id,
            InferenceResult.component_counts,
        )
        .filter(InferenceResult.project_id == project_id)
        .filter(InferenceResult.progress_percentage.isnot(None))
        .order_by(InferenceResult.processed_at.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "timestamp": r.processed_at.isoformat(),
            "progress_percentage": r.progress_percentage,
            "image_id": r.image_id,
            "component_counts": r.component_counts or {},
        }
        for r in results
    ]


# ── Helpers ────────────────────────────────────────────────────────────

def _get_image_or_404(db: Session, image_id: str) -> Image:
    img = db.query(Image).filter(Image.id == image_id).first()
    if not img:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image {image_id} not found",
        )
    return img


def _enrich_image(img: Image) -> dict[str, Any]:
    """Add pre-signed URLs before serialising."""
    data = {
        "id": img.id,
        "project_id": img.project_id,
        "device_id": img.device_id,
        "filename": img.filename,
        "captured_at": img.captured_at,
        "uploaded_at": img.uploaded_at,
        "status": img.status,
        "metadata": img.image_metadata,
        "raw_image_url": None,
        "inference_result": None,
    }

    try:
        data["raw_image_url"] = get_presigned_url(
            settings.minio_raw_bucket, img.raw_storage_path
        )
    except Exception:
        pass

    if img.inference_result:
        ir = img.inference_result
        ir_data = {
            "id": ir.id,
            "image_id": ir.image_id,
            "project_id": ir.project_id,
            "yolo_detections": ir.yolo_detections,
            "segmentation_results": ir.segmentation_results,
            "component_counts": ir.component_counts,
            "progress_percentage": ir.progress_percentage,
            "mwpi_score": ir.mwpi_score,
            "detected_classes": ir.detected_classes,
            "component_progress": ir.component_progress,
            "avg_confidence": avg_confidence(ir.yolo_detections or []),
            "explanation": ir.explanation,
            "processed_at": ir.processed_at,
            "processing_time_ms": ir.processing_time_ms,
            "error_message": ir.error_message,
            "annotated_image_url": _annotated_url(ir.annotated_image_path),
        }
        data["inference_result"] = ir_data

    return data


def _annotated_url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return get_presigned_url(settings.minio_annotated_bucket, path)
    except Exception:
        return None
