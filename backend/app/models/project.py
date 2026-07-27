"""
project.py — Project ORM model.

A Project represents one construction site being monitored.
It holds the BIM configuration that the progress engine uses to
calculate completion percentages.

BIM config example (stored as JSON):
{
    "expected_components": {
        "column":     20,
        "beam":       40,
        "slab":       10,
        "wall":       30,
        "door":       15,
        "window":     25,
        "scaffolding": 8
    },
    "phases": [
        {"name": "Foundation",  "weight": 0.20},
        {"name": "Structure",   "weight": 0.50},
        {"name": "Finishing",   "weight": 0.30}
    ]
}
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # E.164 format, e.g. "+233507149092" — the "whatsapp:" prefix Twilio needs
    # is added at send time, not stored here.
    client_whatsapp_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active | paused | completed
    bim_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # MWPI ratchet state: {"latched_ratios": {class: ratio}, "updated_at": iso}.
    # Stores ratios (not contributions) so weight changes re-apply to history.
    # Cleared by POST /projects/{id}/reset-progress (rework/demolition).
    mwpi_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r} status={self.status}>"
