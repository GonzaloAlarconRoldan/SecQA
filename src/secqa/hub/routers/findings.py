from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..deps import DB, Actor, get_or_404, project_by_key
from ..models import AuditLog, Defect, Finding, Severity, TriageStatus, utcnow
from ..schemas import BulkTriage, FindingOut, FindingTriage, Page

router = APIRouter(tags=["findings"])

SEVERITY_ORDER = case(
    {s.value: i for i, s in enumerate(Severity)}, value=Finding.severity, else_=99
)


def _first_seen():
    other = aliased(Finding)
    return (
        select(func.min(other.run_id))
        .where(other.project_id == Finding.project_id, other.fingerprint == Finding.fingerprint)
        .correlate(Finding)
        .scalar_subquery()
    )


def findings_out(db: Session, rows) -> list[FindingOut]:
    out = []
    for finding, first_seen, defect_key in rows:
        out.append(FindingOut.model_validate(finding).model_copy(
            update={"first_seen_run_id": first_seen, "defect_key": defect_key}))
    return out


@router.get("/findings", response_model=Page[FindingOut])
def list_findings(
    db: DB,
    project: str | None = None,
    run_id: int | None = None,
    severity: list[Severity] | None = Query(None),
    triage_status: list[TriageStatus] | None = Query(None),
    source: str | None = None,
    category: str | None = None,
    q: str | None = None,
    new_only: bool = False,
    untracked: bool = Query(False, description="only findings not linked to a defect"),
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    first_seen = _first_seen().label("first_seen")
    stmt = select(Finding, first_seen, Defect.key).outerjoin(Defect, Finding.defect_id == Defect.id)
    if project:
        stmt = stmt.where(Finding.project_id == project_by_key(db, project).id)
    if run_id:
        stmt = stmt.where(Finding.run_id == run_id)
    if severity:
        stmt = stmt.where(Finding.severity.in_(severity))
    if triage_status:
        stmt = stmt.where(Finding.triage_status.in_(triage_status))
    if source:
        stmt = stmt.where(Finding.source == source)
    if category:
        stmt = stmt.where(Finding.category == category)
    if untracked:
        stmt = stmt.where(Finding.defect_id.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Finding.title.ilike(like), Finding.description.ilike(like),
                              Finding.file_path.ilike(like), Finding.endpoint.ilike(like)))
    if new_only:
        stmt = stmt.where(_first_seen() == Finding.run_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(SEVERITY_ORDER, Finding.created_at.desc(), Finding.id.desc())
                      .limit(limit).offset(offset)).all()
    return Page(items=findings_out(db, rows), total=total or 0, limit=limit, offset=offset)


@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: int, db: DB):
    get_or_404(db, Finding, finding_id)
    row = db.execute(
        select(Finding, _first_seen(), Defect.key).outerjoin(Defect, Finding.defect_id == Defect.id)
        .where(Finding.id == finding_id)
    ).one()
    return findings_out(db, [row])[0]


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def triage_finding(finding_id: int, body: FindingTriage, db: DB, actor: Actor):
    finding = get_or_404(db, Finding, finding_id)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(finding, field, value)
    if "triage_status" in changes:
        finding.reviewed_by = actor
        finding.reviewed_at = utcnow()
        db.add(AuditLog(project_id=finding.project_id, run_id=finding.run_id, actor=actor,
                        action=f"triaged finding #{finding.id} as {finding.triage_status.value}"))
    db.commit()
    return get_finding(finding_id, db)


@router.post("/findings/bulk-triage")
def bulk_triage(body: BulkTriage, db: DB, actor: Actor):
    findings = db.scalars(select(Finding).where(Finding.id.in_(body.ids))).all()
    now = utcnow()
    for f in findings:
        f.triage_status = body.triage_status
        f.reviewed_by = actor
        f.reviewed_at = now
        if body.review_comment:
            f.review_comment = body.review_comment
    if findings:
        db.add(AuditLog(project_id=findings[0].project_id, actor=actor,
                        action=f"bulk-triaged {len(findings)} findings as {body.triage_status.value}",
                        target=",".join(str(f.id) for f in findings)))
    db.commit()
    return {"updated": len(findings)}
