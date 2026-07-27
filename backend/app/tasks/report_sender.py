"""
report_sender.py — Celery task: send scheduled WhatsApp report digests.

Fires on the beat_schedule defined in celery_app.py. For every active
project with a client_whatsapp_number set, sends a WhatsApp message
whose media_url points back at this backend's own
GET /api/v1/projects/{id}/report/latest.pdf — Twilio fetches the PDF
from there when it delivers the message, so BACKEND_PUBLIC_URL must be
a reachable HTTPS URL (e.g. an ngrok tunnel) at send time.

Demo-scoped — see AIconstruction/CONTEXT.md.
"""

import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models.project import Project
from app.services.whatsapp_sender import send_report_whatsapp
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="app.tasks.report_sender.send_weekly_reports")
def send_weekly_reports() -> dict:
    if not settings.backend_public_url:
        logger.warning(
            "BACKEND_PUBLIC_URL is not set — skipping scheduled WhatsApp reports "
            "(Twilio can't fetch a PDF from localhost)."
        )
        return {"sent": 0, "failed": 0, "skipped_reason": "no_backend_public_url"}

    db = SessionLocal()
    sent, failed = 0, 0
    try:
        projects = (
            db.query(Project)
            .filter(
                Project.status == "active",
                Project.client_whatsapp_number.isnot(None),
            )
            .all()
        )
        logger.info(f"Weekly WhatsApp report run — {len(projects)} project(s) with a client number set")

        for project in projects:
            media_url = (
                f"{settings.backend_public_url}"
                f"/api/v1/projects/{project.id}/report/latest.pdf?days=7"
            )
            try:
                send_report_whatsapp(
                    to_number=project.client_whatsapp_number,
                    project_name=project.name,
                    media_url=media_url,
                )
                sent += 1
            except Exception:
                logger.exception(f"Failed to send WhatsApp report for project {project.id}")
                failed += 1
    finally:
        db.close()

    logger.info(f"Weekly WhatsApp report run complete — sent={sent} failed={failed}")
    return {"sent": sent, "failed": failed}
