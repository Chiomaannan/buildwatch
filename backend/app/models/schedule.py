"""
schedule.py — ProjectSchedule ORM model.

Each row is one planned milestone entry in a project's schedule.
The schedule is what the MWPI comparison is measured against.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ScheduleMilestone(Base):
    """
    One entry in a project's planned construction schedule.

    week_number   — 1-based index from project start
    planned_date  — ISO-8601 date string (YYYY-MM-DD) when this milestone should be reached
    planned_mwpi  — expected MWPI score (0.0–1.0) at this date
    label         — optional human-readable name, e.g. "Foundation complete"
    """

    __tablename__ = "schedule_milestones"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    planned_mwpi: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return (
            f"<ScheduleMilestone project={self.project_id} "
            f"week={self.week_number} planned_mwpi={self.planned_mwpi}>"
        )
