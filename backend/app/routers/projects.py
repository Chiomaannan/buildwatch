"""
projects.py — CRUD endpoints for construction projects.

POST   /api/v1/projects          Create project
GET    /api/v1/projects          List all projects
GET    /api/v1/projects/{id}     Get project by ID
PATCH  /api/v1/projects/{id}     Update project (name, BIM config, status)
DELETE /api/v1/projects/{id}     Delete project (soft: sets status=archived)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        name=payload.name,
        description=payload.description,
        location=payload.location,
        bim_config=payload.bim_config.model_dump() if payload.bim_config else None,
        client_name=payload.client_name,
        client_whatsapp_number=payload.client_whatsapp_number,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    logger.info(f"Created project {project.id}: {project.name!r}")
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Project)
    if status_filter:
        query = query.filter(Project.status == status_filter)
    return query.order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
):
    project = _get_or_404(db, project_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "bim_config" in update_data and update_data["bim_config"] is not None:
        update_data["bim_config"] = update_data["bim_config"].model_dump()

    for field, value in update_data.items():
        setattr(project, field, value)

    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/reset-progress", response_model=ProjectOut)
def reset_progress(project_id: str, db: Session = Depends(get_db)):
    """
    Clear the MWPI ratchet state (latched per-class ratios).

    The MWPI is monotone non-decreasing by design — construction progress is
    irreversible at capture timescale. Rework or demolition is the explicit
    exception, handled here: the next inference starts latching from zero.
    """
    project = _get_or_404(db, project_id)
    # reset_at fences off pre-reset frames from the median filter — otherwise
    # old raw ratios would immediately re-latch the values we just cleared.
    project.mwpi_state = {
        "latched_ratios": {},
        "reset_at": datetime.now(timezone.utc).isoformat(),
    }
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    logger.info(f"MWPI ratchet reset for project {project_id}")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    project.status = "archived"
    project.updated_at = datetime.now(timezone.utc)
    db.commit()


def _get_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project
