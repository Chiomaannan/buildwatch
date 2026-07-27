"""
reports.py — On-demand PDF report generation endpoint.

POST /api/v1/projects/{project_id}/report
  Query params: date_from, date_to (YYYY-MM-DD, both optional — default last 30 days)
  Response: application/pdf (streamed as attachment)
"""

import asyncio
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import Project
from app.services.report_generator import generate_report_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Reports"])


@router.post("/projects/{project_id}/report")
async def create_report(
    project_id: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    """
    Generate a PDF progress report for the project and return it as a download.
    Defaults to the last 30 days if date_from / date_to are not supplied.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=30)

    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")

    logger.info(f"Generating report for project={project_id} {date_from} → {date_to}")

    try:
        pdf_bytes = await asyncio.to_thread(
            generate_report_pdf,
            project,
            db,
            date_from,
            date_to,
        )
    except Exception as exc:
        logger.exception(f"Report generation failed for project {project_id}: {exc}")
        raise HTTPException(status_code=500, detail="Report generation failed")

    import re
    slug = re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-")
    filename = f"buildwatch-{slug}-{date_from.isoformat()}-to-{date_to.isoformat()}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
