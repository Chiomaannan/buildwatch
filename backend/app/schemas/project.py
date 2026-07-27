from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BIMConfig(BaseModel):
    """
    Defines the expected structural components for progress calculation.
    Keys are component class names; values are expected total counts.
    """
    expected_components: dict[str, int] = Field(
        default_factory=dict,
        example={"column": 20, "beam": 40, "slab": 10, "wall": 30},
    )
    phases: list[dict[str, Any]] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    location: str | None = None
    bim_config: BIMConfig | None = None
    client_name: str | None = None
    client_whatsapp_number: str | None = Field(
        None, max_length=32, description="E.164 format, e.g. +233507149092"
    )


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    location: str | None = None
    status: str | None = Field(None, pattern="^(active|paused|completed)$")
    bim_config: BIMConfig | None = None
    client_name: str | None = None
    client_whatsapp_number: str | None = Field(
        None, max_length=32, description="E.164 format, e.g. +233507149092"
    )


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    location: str | None
    status: str
    bim_config: dict | None
    client_name: str | None
    client_whatsapp_number: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
