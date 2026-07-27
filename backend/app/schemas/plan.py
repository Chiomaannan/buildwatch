from datetime import datetime

from pydantic import BaseModel


class PlanOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: str
    plan_image_url: str | None = None
    plan_weights: dict | None = None
    expected_counts: dict | None = None
    analysis_status: str
    analysis_notes: str | None = None
    created_at: datetime
    updated_at: datetime
