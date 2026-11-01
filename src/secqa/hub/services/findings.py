"""Finding ingestion with fingerprint de-duplication across runs.

When a fingerprint was seen before in the same project:
  * previously marked false_positive / accepted_risk → auto-suppressed with the same status;
  * previously linked to a defect → linked again; if that defect was already fixed/closed,
    it is reopened (regression).
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...mapping import enrich
from ..models import AuditLog, Defect, DefectStatus, Finding, Run, TriageStatus, utcnow
from ..schemas import FindingCreate, IngestResult
from .defects import reopen

SUPPRESSED = {TriageStatus.false_positive, TriageStatus.accepted_risk}
REOPENABLE = {DefectStatus.fixed, DefectStatus.verified, DefectStatus.closed}


def fingerprint(data: dict[str, Any]) -> str:
    parts = [
        data.get("tool") or "",
        data.get("rule_id") or data.get("category") or "",
        data.get("file_path") or "",
        str(data.get("line_start") or ""),
        data.get("endpoint") or "",
        data.get("title") or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:40]


def ingest_findings(db: Session, run: Run, items: Sequence[FindingCreate | dict[str, Any]],
                    actor: str) -> IngestResult:
    result = IngestResult(created=0)
    seen_in_batch: set[str] = set()
    existing_in_run = set(db.scalars(select(Finding.fingerprint).where(Finding.run_id == run.id)))

    for item in items:
        data = item.model_dump() if isinstance(item, FindingCreate) else FindingCreate(**item).model_dump()
        enrich(data)
        fp = data.pop("fingerprint", None) or fingerprint(data)
        fp = fp[:64]
        if fp in seen_in_batch or fp in existing_in_run:
            result.skipped += 1
            continue
        seen_in_batch.add(fp)

        finding = Finding(run_id=run.id, project_id=run.project_id, fingerprint=fp, **data)
        previous = db.scalars(
            select(Finding)
            .where(Finding.project_id == run.project_id, Finding.fingerprint == fp, Finding.run_id != run.id)
            .order_by(Finding.id.desc())
            .limit(1)
        ).first()

        if previous is not None:
            if previous.triage_status in SUPPRESSED:
                finding.triage_status = previous.triage_status
                finding.reviewed_by = "system:auto-suppress"
                finding.reviewed_at = utcnow()
                finding.review_comment = f"Inherited from finding #{previous.id}"
                result.suppressed += 1
            if previous.defect_id:
                finding.defect_id = previous.defect_id
                finding.triage_status = TriageStatus.confirmed
                result.linked_to_defects += 1
                defect = db.get(Defect, previous.defect_id)
                if defect is not None and defect.status in REOPENABLE:
                    reopen(db, defect, "system", f"regression: reappeared in run #{run.id}")

        db.add(finding)
        result.created += 1

    db.add(AuditLog(project_id=run.project_id, run_id=run.id, actor=actor,
                    action=f"ingested {result.created} findings "
                           f"({result.suppressed} auto-suppressed, {result.skipped} duplicates skipped)"))
    db.flush()
    return result
