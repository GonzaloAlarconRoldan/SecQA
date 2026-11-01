"""Tool HTML reports (k6 web dashboard, JMeter dashboard, ZAP, osv-scanner, Trivy, Playwright…).

Third-party reports ship their own JavaScript, so they are never served as Hub pages:

* they live under an unguessable, **signed and expiring** URL (`/r/{id}/{exp}/{sig}/…`) that works in
  a new tab without the API token (links can't carry an Authorization header);
* every response carries `Content-Security-Policy: sandbox allow-scripts …` *without*
  `allow-same-origin`, so the report runs in an opaque origin and cannot read the Hub's
  localStorage (where the UI keeps the token), cookies or API.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import secrets
import shutil
import stat
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Attachment, AuditLog, Run

MAX_REPORT_BYTES = 200 * 1024 * 1024  # uncompressed
MAX_REPORT_FILES = 5000
VIEW_TTL_S = 12 * 3600
KNOWN_TOOLS = {"k6", "jmeter", "zap", "osv-scanner", "trivy", "nuclei", "semgrep", "playwright", "lighthouse",
               "gatling", "locust", "allure", "other"}
SANDBOX_CSP = ("sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads; "
               "frame-ancestors 'none'")


def report_secret(settings: Settings) -> bytes:
    path = settings.data_dir / ".report-secret"
    if not path.is_file():
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
        path.chmod(0o600)
    return path.read_bytes()


def _sig(secret: bytes, report_id: int, exp: int) -> str:
    return hmac.new(secret, f"{report_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def view_url(settings: Settings, a: Attachment, ttl_s: int = VIEW_TTL_S) -> str:
    exp = int(time.time()) + ttl_s
    return f"/r/{a.id}/{exp}/{_sig(report_secret(settings), a.id, exp)}/{a.entry or 'index.html'}"


def verify(settings: Settings, report_id: int, exp: int, sig: str) -> bool:
    return exp >= time.time() and hmac.compare_digest(sig, _sig(report_secret(settings), report_id, exp))


def _looks_html(data: bytes) -> bool:
    head = data[:2048].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html")) or b"<html" in head


def _extract_zip(data: bytes, dest: Path) -> tuple[int, str]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "not a valid zip file") from exc
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_REPORT_FILES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"report has more than {MAX_REPORT_FILES} files")
    if sum(i.file_size for i in infos) > MAX_REPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "report exceeds 200 MB uncompressed")
    total, html_files = 0, []
    root = dest.resolve()
    for info in infos:
        name = PurePosixPath(info.filename.replace("\\", "/"))
        if name.is_absolute() or ".." in name.parts or stat.S_ISLNK(info.external_attr >> 16):
            continue  # zip-slip / symlink entries are dropped, never written
        target = (root / name).resolve()
        if root not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            written = 0
            while chunk := src.read(1 << 20):
                written += len(chunk)
                if total + written > MAX_REPORT_BYTES:  # don't trust declared sizes (zip bombs)
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "report exceeds 200 MB")
                out.write(chunk)
        total += written
        if name.suffix.lower() in (".html", ".htm"):
            html_files.append(name.as_posix())
    if not html_files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "the zip contains no .html file")
    index = [h for h in html_files if PurePosixPath(h).name.lower() == "index.html"]
    entry = min(index or html_files, key=lambda h: (h.count("/"), len(h)))
    return total, entry


def save_report(db: Session, settings: Settings, run: Run, data: bytes, filename: str, *, tool: str,
                title: str | None, actor: str) -> Attachment:
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "empty file")
    tool = tool.lower().strip() if tool and tool.lower().strip() in KNOWN_TOOLS else "other"
    rel = f"{run.project_id}/reports/{uuid.uuid4().hex}"
    dest = settings.attachments_dir / rel
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if data[:4] == b"PK\x03\x04":
            size, entry = _extract_zip(data, dest)
        elif _looks_html(data):
            if len(data) > MAX_REPORT_BYTES:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "report exceeds 200 MB")
            entry, size = "index.html", len(data)
            (dest / entry).write_bytes(data)
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "upload an .html report or a .zip of a report folder (e.g. JMeter -o dir)")
    except HTTPException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    original = (filename or "report.html").replace("\\", "/").rsplit("/", 1)[-1][:300]
    a = Attachment(project_id=run.project_id, run_id=run.id, kind="report", tool=tool, entry=entry,
                   filename=original, content_type="text/html", size=size, storage_path=rel,
                   caption=(title or None) and title[:300], created_by=actor)
    db.add(a)
    db.add(AuditLog(project_id=run.project_id, run_id=run.id, actor=actor,
                    action=f"uploaded {tool} report '{original}'"))
    return a


def remove_files(settings: Settings, a: Attachment) -> None:
    root = settings.attachments_dir.resolve()
    path = (root / a.storage_path).resolve()
    if root not in path.parents:
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        path.unlink()
