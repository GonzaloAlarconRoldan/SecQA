from __future__ import annotations

import mimetypes
import re
import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..deps import DB, Actor, AppSettings, get_or_404, project_by_key
from ..models import (
    OPEN_DEFECT_STATUSES,
    Attachment,
    AuditLog,
    Defect,
    DefectComment,
    DefectKind,
    DefectStatus,
    Finding,
    Priority,
    Severity,
    TriageStatus,
    utcnow,
)
from ..schemas import (
    AttachmentOut,
    CommentCreate,
    CommentOut,
    DefectCreate,
    DefectDetail,
    DefectFromFindings,
    DefectOut,
    DefectUpdate,
    EventOut,
    FindingOut,
    Page,
)
from ..services.defects import create_defect, is_sla_breached, update_defect

router = APIRouter(tags=["defects"])

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
SEVERITY_RANK = {s: i for i, s in enumerate(Severity)}
SEVERITY_ORDER = case({s.value: i for i, s in enumerate(Severity)}, value=Defect.severity, else_=99)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
# Types a browser may render inline. Everything else is forced to download.
INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "text/plain", "application/pdf"}


def defect_out(db: Session, d: Defect) -> DefectOut:
    count = db.scalar(select(func.count()).where(Finding.defect_id == d.id)) or 0
    return DefectOut.model_validate(d).model_copy(
        update={"sla_breached": is_sla_breached(d), "finding_count": count})


def attachment_out(a: Attachment) -> AttachmentOut:
    return AttachmentOut.model_validate(a).model_copy(update={"url": f"/api/attachments/{a.id}"})


@router.get("/defects", response_model=Page[DefectOut])
def list_defects(
    db: DB,
    project: str | None = None,
    status_: list[DefectStatus] | None = Query(None, alias="status"),
    severity: list[Severity] | None = Query(None),
    kind: DefectKind | None = None,
    priority: Priority | None = None,
    assignee: str | None = None,
    owasp_id: str | None = None,
    iso_control: str | None = None,
    q: str | None = None,
    open_only: bool = False,
    sla_breached: bool = False,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    stmt = select(Defect)
    if project:
        stmt = stmt.where(Defect.project_id == project_by_key(db, project).id)
    if status_:
        stmt = stmt.where(Defect.status.in_(status_))
    if open_only or sla_breached:
        stmt = stmt.where(Defect.status.in_(OPEN_DEFECT_STATUSES))
    if sla_breached:
        stmt = stmt.where(Defect.due_at < utcnow(), Defect.status != DefectStatus.fixed)
    if severity:
        stmt = stmt.where(Defect.severity.in_(severity))
    if kind:
        stmt = stmt.where(Defect.kind == kind)
    if priority:
        stmt = stmt.where(Defect.priority == priority)
    if assignee:
        stmt = stmt.where(Defect.assignee == assignee)
    if owasp_id:
        stmt = stmt.where(Defect.owasp_id == owasp_id)
    if iso_control:
        stmt = stmt.where(Defect.iso_control == iso_control)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Defect.title.ilike(like), Defect.key.ilike(like), Defect.description.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(SEVERITY_ORDER, Defect.priority, Defect.created_at.desc())
                      .limit(limit).offset(offset)).all()
    return Page(items=[defect_out(db, d) for d in rows], total=total or 0, limit=limit, offset=offset)


@router.post("/projects/{key}/defects", response_model=DefectOut, status_code=status.HTTP_201_CREATED)
def new_defect(key: str, body: DefectCreate, db: DB, actor: Actor, settings: AppSettings):
    project = project_by_key(db, key)
    fields = body.model_dump(exclude={"finding_ids"})
    defect = create_defect(db, settings, project, actor, **fields)
    _link_findings(db, defect, body.finding_ids, actor)
    db.add(AuditLog(project_id=project.id, actor=actor, action=f"created defect {defect.key}"))
    db.commit()
    return defect_out(db, defect)


@router.post("/projects/{key}/defects/from-findings", response_model=DefectOut,
             status_code=status.HTTP_201_CREATED)
def defect_from_findings(key: str, body: DefectFromFindings, db: DB, actor: Actor, settings: AppSettings):
    """Promote one or more findings to a single tracked defect (severity = worst finding)."""
    project = project_by_key(db, key)
    findings = db.scalars(select(Finding).where(
        Finding.id.in_(body.finding_ids), Finding.project_id == project.id)).all()
    if not findings:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no matching findings in this project")
    worst = min(findings, key=lambda f: SEVERITY_RANK[f.severity])
    kind = DefectKind.vulnerability if worst.source != "perf" else DefectKind.performance
    location = worst.endpoint or (f"{worst.file_path}:{worst.line_start}" if worst.file_path else None)
    description = "\n\n".join(filter(None, [
        worst.description,
        f"**Location:** `{location}`" if location else None,
        f"**Evidence:**\n```\n{worst.evidence}\n```" if worst.evidence else None,
        f"**Suggested remediation:** {worst.remediation}" if worst.remediation else None,
        f"Promoted from {len(findings)} finding(s): " + ", ".join(f"#{f.id}" for f in findings),
    ]))
    defect = create_defect(
        db, settings, project, actor,
        kind=kind,
        title=body.title or worst.title,
        description=description,
        severity=worst.severity,
        priority=body.priority or _default_priority(worst.severity),
        assignee=body.assignee,
        cwe_id=worst.cwe_id, owasp_id=worst.owasp_id, iso_control=worst.iso_control,
        found_in_run_id=worst.run_id,
        tags=sorted({f.category for f in findings}),
    )
    _link_findings(db, defect, [f.id for f in findings], actor)
    db.add(AuditLog(project_id=project.id, actor=actor,
                    action=f"promoted {len(findings)} finding(s) to defect {defect.key}"))
    db.commit()
    return defect_out(db, defect)


def _default_priority(severity: Severity) -> Priority:
    return {Severity.critical: Priority.p1, Severity.high: Priority.p2,
            Severity.medium: Priority.p3}.get(severity, Priority.p4)


def _link_findings(db: Session, defect: Defect, ids: list[int], actor: str) -> None:
    if not ids:
        return
    now = utcnow()
    for f in db.scalars(select(Finding).where(Finding.id.in_(ids), Finding.project_id == defect.project_id)):
        f.defect_id = defect.id
        f.triage_status = TriageStatus.confirmed
        f.reviewed_by = f.reviewed_by or actor
        f.reviewed_at = f.reviewed_at or now


@router.get("/defects/{defect_id}", response_model=DefectDetail)
def get_defect(defect_id: int, db: DB):
    d = get_or_404(db, Defect, defect_id)
    base = defect_out(db, d)
    findings = db.scalars(select(Finding).where(Finding.defect_id == d.id).order_by(Finding.id)).all()
    attachments = db.scalars(select(Attachment).where(Attachment.defect_id == d.id)).all()
    return DefectDetail(
        **base.model_dump(),
        comments=[CommentOut.model_validate(c) for c in d.comments],
        events=[EventOut.model_validate(e) for e in d.events],
        attachments=[attachment_out(a) for a in attachments],
        findings=[FindingOut.model_validate(f).model_copy(update={"defect_key": d.key}) for f in findings],
    )


@router.patch("/defects/{defect_id}", response_model=DefectOut)
def patch_defect(defect_id: int, body: DefectUpdate, db: DB, actor: Actor, settings: AppSettings):
    d = get_or_404(db, Defect, defect_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == DefectStatus.duplicate and not (changes.get("duplicate_of_id") or d.duplicate_of_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "duplicate_of_id is required when status=duplicate")
    if changes.get("duplicate_of_id") == d.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a defect cannot duplicate itself")
    update_defect(db, settings, d, actor, changes)
    if "status" in changes:
        db.add(AuditLog(project_id=d.project_id, actor=actor,
                        action=f"moved defect {d.key} to {d.status.value}"))
    db.commit()
    return defect_out(db, d)


@router.delete("/defects/{defect_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_defect(defect_id: int, db: DB, actor: Actor):
    d = get_or_404(db, Defect, defect_id)
    db.add(AuditLog(project_id=d.project_id, actor=actor, action=f"deleted defect {d.key}"))
    db.delete(d)
    db.commit()


@router.post("/defects/{defect_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(defect_id: int, body: CommentCreate, db: DB, actor: Actor):
    d = get_or_404(db, Defect, defect_id)
    c = DefectComment(defect_id=d.id, author=actor, body=body.body)
    db.add(c)
    d.updated_at = utcnow()
    db.commit()
    return c


@router.post("/defects/{defect_id}/attachments", response_model=AttachmentOut,
             status_code=status.HTTP_201_CREATED)
async def add_attachment(defect_id: int, db: DB, actor: Actor, settings: AppSettings,
                         file: UploadFile = File(...)):
    d = get_or_404(db, Defect, defect_id)
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "attachment exceeds 20 MB")
    original = (file.filename or "file").rsplit("/", 1)[-1]
    safe = _SAFE_NAME.sub("_", original)[:120] or "file"
    rel = f"{d.project_id}/{uuid.uuid4().hex}_{safe}"
    path = settings.attachments_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    content_type = file.content_type or mimetypes.guess_type(safe)[0] or "application/octet-stream"
    a = Attachment(project_id=d.project_id, defect_id=d.id, filename=original[:300],
                   content_type=content_type[:100], size=len(data), storage_path=rel)
    db.add(a)
    db.add(AuditLog(project_id=d.project_id, actor=actor, action=f"attached '{original}' to {d.key}"))
    db.commit()
    return attachment_out(a)


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, db: DB, settings: AppSettings):
    a = get_or_404(db, Attachment, attachment_id)
    root = settings.attachments_dir.resolve()
    path = (root / a.storage_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment file missing")
    inline = a.content_type in INLINE_TYPES
    return FileResponse(
        path,
        media_type=a.content_type if inline else "application/octet-stream",
        filename=a.filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )
