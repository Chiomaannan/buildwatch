"""
upload.py — Image upload endpoint called by the edge agent.

POST /api/v1/upload
  Form fields:
    image        : JPEG file (multipart)
    project_id   : str
    device_id    : str
    captured_at  : ISO-8601 string
    metadata     : JSON string (optional)

Response:
    { image_id, status, task_id, message }
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.image import Image
from app.models.project import Project
from app.schemas.image import UploadResponse
from app.services.minio_client import upload_bytes
from app.tasks.inference import run_inference
from app.tasks.worker_monitor import run_presence_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Upload"])
settings = get_settings()

MAX_FILE_SIZE = 20 * 1024 * 1024   # 20 MB hard limit


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    image: UploadFile = File(...),
    project_id: str = Form(...),
    device_id: str = Form(...),
    captured_at: str = Form(...),
    metadata: str = Form(default="{}"),
    db: Session = Depends(get_db),
):
    # ── Validate project exists ────────────────────────────────────────
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # ── Validate content type ──────────────────────────────────────────
    if image.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG and PNG images are accepted",
        )

    # ── Read and size-check ────────────────────────────────────────────
    raw_bytes = await image.read()
    if len(raw_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_FILE_SIZE // (1024*1024)} MB limit",
        )

    # ── Parse metadata ────────────────────────────────────────────────
    try:
        meta_dict = json.loads(metadata)
    except json.JSONDecodeError:
        meta_dict = {}

    # ── Store raw image in MinIO ──────────────────────────────────────
    image_id = str(uuid.uuid4())
    filename = image.filename or f"{image_id}.jpg"
    object_name = f"raw/{project_id}/{image_id}.jpg"

    upload_bytes(
        bucket=settings.minio_raw_bucket,
        object_name=object_name,
        data=raw_bytes,
    )

    # ── Create DB record ──────────────────────────────────────────────
    db_image = Image(
        id=image_id,
        project_id=project_id,
        device_id=device_id,
        filename=filename,
        raw_storage_path=object_name,
        captured_at=captured_at,
        status="pending",
        image_metadata=meta_dict,
    )
    db.add(db_image)
    db.commit()

    # ── Dispatch Celery task ──────────────────────────────────────────
    # presence_check images → person counting + alert evaluation
    # all other images     → MWPI inference pipeline
    if meta_dict.get("capture_type") == "presence_check":
        task = run_presence_check.apply_async(args=[image_id], queue="inference")
    else:
        task = run_inference.apply_async(args=[image_id], queue="inference")

    logger.info(
        f"Image {image_id} uploaded | project={project_id} device={device_id} "
        f"size={len(raw_bytes)//1024}KB | task={task.id}"
    )

    return UploadResponse(
        image_id=image_id,
        status="pending",
        task_id=task.id,
        message="Image received. AI inference queued.",
    )
