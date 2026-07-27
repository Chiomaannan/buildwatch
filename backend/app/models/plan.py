"""
plan.py — ProjectPlan ORM model.

Stores the uploaded building plan image and the weights + expected counts
that the plan analyzer task extracts from it via Claude vision API.

These drive plan-informed MWPI:
  MWPI = Σ plan_weight(class) × min(1.0, detected_count / expected_count)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectPlan(Base):
    __tablename__ = "project_plans"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # MinIO object path for the uploaded plan image
    plan_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Claude-derived structural weights (sum to 1.0)
    # e.g. {"foundation": 0.10, "column": 0.30, "wall": 0.60}
    plan_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Claude-estimated element counts for the complete building
    # e.g. {"foundation": 2, "column": 8, "wall": 20}
    expected_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # pending → analyzing → completed | failed
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending")

    # Human-readable summary from Claude (what it saw in the plan)
    analysis_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
