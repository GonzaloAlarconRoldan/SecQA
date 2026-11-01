"""Defect lifecycle: key allocation, SLA due dates, audited field changes."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import (
    OPEN_DEFECT_STATUSES,
    Defect,
    DefectEvent,
    DefectStatus,
    Project,
    utcnow,
)

RESOLVED_STATUSES = {DefectStatus.fixed, DefectStatus.verified}
CLOSED_STATUSES = {DefectStatus.closed, DefectStatus.wont_fix, DefectStatus.duplicate}
TRACKED_FIELDS = (
    "kind", "title", "severity", "priority", "status", "assignee", "environment",
    "cwe_id", "owasp_id", "iso_control", "duplicate_of_id", "due_at",
)


def next_defect_key(db: Session, project: Project) -> str:
    project.defect_seq += 1
    db.flush()
    return f"{project.key}-{project.defect_seq}"


def compute_due(settings: Settings, severity: str, created: datetime) -> datetime | None:
    days = settings.sla_days(severity)
    return created + timedelta(days=days) if days else None


def is_sla_breached(defect: Defect, now: datetime | None = None) -> bool:
    if defect.due_at is None:
        return False
    if defect.status in OPEN_DEFECT_STATUSES and defect.status is not DefectStatus.fixed:
        return (now or utcnow()) > defect.due_at
    done_at = defect.resolved_at or defect.closed_at
    return bool(done_at and done_at > defect.due_at)


def create_defect(db: Session, settings: Settings, project: Project, actor: str, **fields: Any) -> Defect:
    created = utcnow()
    defect = Defect(
        project_id=project.id,
        key=next_defect_key(db, project),
        reporter=actor,
        created_at=created,
        updated_at=created,
        **fields,
    )
    if defect.due_at is None:
        defect.due_at = compute_due(settings, _val(defect.severity), created)
    db.add(defect)
    db.flush()
    db.add(DefectEvent(defect_id=defect.id, actor=actor, field="created", new_value=defect.key))
    return defect


def update_defect(db: Session, settings: Settings, defect: Defect, actor: str, changes: dict[str, Any]) -> None:
    sla_reset = "severity" in changes and "due_at" not in changes
    for field, new in changes.items():
        old = getattr(defect, field)
        if _val(old) == _val(new):
            continue
        setattr(defect, field, new)
        if field in TRACKED_FIELDS:
            db.add(DefectEvent(defect_id=defect.id, actor=actor, field=field,
                               old_value=_fmt(old), new_value=_fmt(new)))
    if sla_reset:
        defect.due_at = compute_due(settings, _val(defect.severity), defect.created_at)
    if "status" in changes:
        apply_status_timestamps(defect)
    defect.updated_at = utcnow()


def apply_status_timestamps(defect: Defect) -> None:
    now = utcnow()
    status = DefectStatus(_val(defect.status))
    if status in RESOLVED_STATUSES and defect.resolved_at is None:
        defect.resolved_at = now
    if status in CLOSED_STATUSES and defect.closed_at is None:
        defect.closed_at = now
    if status in {DefectStatus.new, DefectStatus.triaged, DefectStatus.in_progress}:
        defect.resolved_at = None
        defect.closed_at = None


def reopen(db: Session, defect: Defect, actor: str, reason: str) -> None:
    old = defect.status
    defect.status = DefectStatus.new
    apply_status_timestamps(defect)
    defect.updated_at = utcnow()
    db.add(DefectEvent(defect_id=defect.id, actor=actor, field="status",
                       old_value=_fmt(old), new_value=f"new ({reason})"))


def _val(v: Any) -> Any:
    return v.value if hasattr(v, "value") else v


def _fmt(v: Any) -> str | None:
    v = _val(v)
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)
