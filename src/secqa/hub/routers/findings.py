from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..deps import DB, Actor, AppSettings, get_or_404, project_by_key
from ..models import Attachment, AuditLog, Defect, Finding, Severity, TriageStatus, utcnow
from ..schemas import AttachmentOut, BulkTriage, FindingOut, FindingTriage, Page
from ..services.attachments import save_upload

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
    rows = list(rows)
    ids = [r[0].id for r in rows]
    counts = dict(db.execute(
        select(Attachment.finding_id, func.count()).where(Attachment.finding_id.in_(ids))
        .group_by(Attachment.finding_id)
    ).all()) if ids else {}
    out = []
    for finding, first_seen, defect_key in rows:
        out.append(FindingOut.model_validate(finding).model_copy(update={
            "first_seen_run_id": first_seen, "defect_key": defect_key,
            "attachment_count": counts.get(finding.id, 0)}))
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
    owasp_id: str | None = None,
    cwe_id: str | None = None,
    iso_control: str | None = None,
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
    if owasp_id:
        stmt = stmt.where(Finding.owasp_id == owasp_id)
    if cwe_id:
        stmt = stmt.where(Finding.cwe_id == cwe_id)
    if iso_control:
        stmt = stmt.where(Finding.iso_control == iso_control)
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


@router.get("/findings/{finding_id}/attachments", response_model=list[AttachmentOut])
def list_finding_attachments(finding_id: int, db: DB):
    get_or_404(db, Finding, finding_id)
    rows = db.scalars(select(Attachment).where(Attachment.finding_id == finding_id)
                      .order_by(Attachment.created_at, Attachment.id)).all()
    return [AttachmentOut.model_validate(a).model_copy(update={"url": f"/api/attachments/{a.id}"}) for a in rows]


@router.post("/findings/{finding_id}/attachments", response_model=AttachmentOut,
             status_code=status.HTTP_201_CREATED)
async def add_finding_attachment(finding_id: int, db: DB, actor: Actor, settings: AppSettings,
                                 file: UploadFile = File(...), caption: str | None = Form(None),
                                 kind: str | None = Form(None)):
    """Evidence for a finding: screenshots (before/after), HTTP captures, logs."""
    f = get_or_404(db, Finding, finding_id)
    a = await save_upload(db, settings, file, project_id=f.project_id, actor=actor, caption=caption,
                          kind=kind, finding_id=f.id, run_id=f.run_id, label=f"finding #{f.id}")
    db.commit()
    return AttachmentOut.model_validate(a).model_copy(update={"url": f"/api/attachments/{a.id}"})
