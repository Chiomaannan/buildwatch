from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class UploadResponse(BaseModel):
    image_id: str
    status: str
    task_id: str
    message: str


class InferenceResultOut(BaseModel):
    id: str
    image_id: str
    project_id: str
    annotated_image_url: str | None
    yolo_detections: list[dict[str, Any]] | None
    segmentation_results: list[dict[str, Any]] | None
    component_counts: dict[str, int] | None
    progress_percentage: float | None
    component_progress: dict[str, float] | None
    explanation: Optional[str] = None
    processed_at: datetime
    processing_time_ms: int | None
    error_message: str | None

    model_config = {"from_attributes": True}


class ImageOut(BaseModel):
    id: str
    project_id: str
    device_id: str
    filename: str
    raw_image_url: str | None
    captured_at: str
    uploaded_at: datetime
    status: str
    metadata: dict | None
    inference_result: InferenceResultOut | None

    model_config = {"from_attributes": True}
