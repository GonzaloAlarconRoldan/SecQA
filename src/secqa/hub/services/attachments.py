"""Evidence storage: screenshots, HTTP captures and other files attached to findings or defects."""
from __future__ import annotations

import base64
import mimetypes
import re
import uuid
from collections.abc import Iterable

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Attachment, AuditLog, Finding

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_REPORT_IMAGE_BYTES = 3 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
KINDS = {"screenshot", "http", "file"}

# Magic numbers: an upload is only treated as an image if its bytes say so, so a file named
# shot.png that is really HTML can never be served inline as markup.
_IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}


def sniff_image(data: bytes) -> str | None:
    for sig, ctype in _IMAGE_SIGNATURES.items():
        if data.startswith(sig):
            return ctype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def save_upload(db: Session, settings: Settings, file: UploadFile, *, project_id: int, actor: str,
                      caption: str | None = None, kind: str | None = None, finding_id: int | None = None,
                      defect_id: int | None = None, run_id: int | None = None, label: str = "") -> Attachment:
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "attachment exceeds 20 MB")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "empty file")
    original = (file.filename or "file").replace("\\", "/").rsplit("/", 1)[-1] or "file"
    safe = _SAFE_NAME.sub("_", original)[:120] or "file"

    image_type = sniff_image(data)
    if image_type:
        content_type = image_type
    else:
        declared = file.content_type or mimetypes.guess_type(safe)[0] or "application/octet-stream"
        # never trust a declared image/* type the bytes don't back up
        content_type = "application/octet-stream" if declared.startswith("image/") else declared
    if kind not in KINDS:
        kind = "screenshot" if image_type else "file"

    rel = f"{project_id}/{uuid.uuid4().hex}_{safe}"
    path = settings.attachments_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    a = Attachment(project_id=project_id, finding_id=finding_id, defect_id=defect_id, run_id=run_id,
                   filename=original[:300], content_type=content_type[:100], size=len(data),
                   storage_path=rel, kind=kind, caption=(caption or None) and caption[:2000],
                   created_by=actor)
    db.add(a)
    db.add(AuditLog(project_id=project_id, run_id=run_id, actor=actor,
                    action=f"attached {kind} '{original}' to {label}"))
    return a


def evidence_query(defect_id: int | None = None, finding_ids: Iterable[int] = ()):
    """Attachments of a defect plus those of its linked findings (evidence travels with promotion)."""
    ids = list(finding_ids)
    clauses = []
    if defect_id is not None:
        clauses.append(Attachment.defect_id == defect_id)
    if ids:
        clauses.append(Attachment.finding_id.in_(ids))
    return (select(Attachment).where(or_(*clauses), Attachment.kind != "report")
            .order_by(Attachment.created_at, Attachment.id))


def linked_finding_ids(db: Session, defect_id: int) -> list[int]:
    return list(db.scalars(select(Finding.id).where(Finding.defect_id == defect_id)))


def data_uri(settings: Settings, a: Attachment) -> str | None:
    """Inline image for self-contained HTML/PDF reports."""
    if not a.content_type.startswith("image/") or a.size > MAX_REPORT_IMAGE_BYTES:
        return None
    root = settings.attachments_dir.resolve()
    path = (root / a.storage_path).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return f"data:{a.content_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
