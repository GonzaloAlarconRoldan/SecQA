from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..deps import DB, Actor, project_by_key
from ..models import OPEN_DEFECT_STATUSES, AuditLog, Defect, Project, Run, Severity
from ..schemas import AuditCreate, AuditOut, ProjectCreate, ProjectOut, ProjectSummary, ProjectUpdate

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(db: DB):
    projects = db.scalars(select(Project).order_by(Project.name)).all()
    open_counts = dict(db.execute(
        select(Defect.project_id, func.count()).where(Defect.status.in_(OPEN_DEFECT_STATUSES))
        .group_by(Defect.project_id)
    ).all())
    crit_counts = dict(db.execute(
        select(Defect.project_id, func.count())
        .where(Defect.status.in_(OPEN_DEFECT_STATUSES), Defect.severity == Severity.critical)
        .group_by(Defect.project_id)
    ).all())
    run_stats = {pid: (n, last) for pid, n, last in db.execute(
        select(Run.project_id, func.count(), func.max(Run.started_at)).group_by(Run.project_id)
    ).all()}
    out = []
    for p in projects:
        n, last = run_stats.get(p.id, (0, None))
        out.append(ProjectSummary.model_validate(p).model_copy(update={
            "open_defects": open_counts.get(p.id, 0),
            "critical_open": crit_counts.get(p.id, 0),
            "run_count": n,
            "last_run_at": last,
        }))
    return out


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: DB, actor: Actor):
    if db.scalars(select(Project).where(Project.key == body.key)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"project key '{body.key}' already exists")
    project = Project(**body.model_dump())
    db.add(project)
    db.flush()
    db.add(AuditLog(project_id=project.id, actor=actor, action=f"created project {project.key}"))
    db.commit()
    return project


@router.get("/projects/{key}", response_model=ProjectOut)
def get_project(key: str, db: DB):
    return project_by_key(db, key)


@router.patch("/projects/{key}", response_model=ProjectOut)
def update_project(key: str, body: ProjectUpdate, db: DB):
    project = project_by_key(db, key)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    return project


@router.delete("/projects/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(key: str, db: DB):
    db.delete(project_by_key(db, key))
    db.commit()


@router.get("/projects/{key}/audit", response_model=list[AuditOut])
def list_audit(key: str, db: DB, run_id: int | None = None, limit: int = 200):
    project = project_by_key(db, key)
    q = select(AuditLog).where(AuditLog.project_id == project.id)
    if run_id:
        q = q.where(AuditLog.run_id == run_id)
    return db.scalars(q.order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(min(limit, 1000))).all()


@router.post("/projects/{key}/audit", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
def add_audit(key: str, body: AuditCreate, db: DB, actor: Actor):
    """Agents record every active command (DAST, load tests…) here before running it."""
    project = project_by_key(db, key)
    entry = AuditLog(project_id=project.id, actor=actor, **body.model_dump())
    db.add(entry)
    db.commit()
    return entry
