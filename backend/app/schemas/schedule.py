from datetime import datetime

from pydantic import BaseModel, Field


class MilestoneIn(BaseModel):
    week_number: int = Field(..., ge=1)
    planned_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    planned_mwpi: float = Field(..., ge=0.0, le=1.0)
    label: str | None = None


class MilestoneOut(BaseModel):
    id: str
    project_id: str
    week_number: int
    planned_date: str
    planned_mwpi: float
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ComparisonEntry(BaseModel):
    week_number: int
    planned_date: str
    planned_mwpi: float
    label: str | None
    actual_mwpi: float | None
    deviation: float | None       # actual_mwpi - planned_mwpi; None if no data yet
    status: str                   # ON_SCHEDULE | SLIGHTLY_BEHIND | DELAYED | PENDING


class ComparisonOut(BaseModel):
    project_id: str
    milestones: list[ComparisonEntry]
    overall_status: str           # status of the most recent milestone with actual data
