"""Tool HTML reports attached to runs (k6 dashboard, JMeter dashboard, ZAP, osv-scanner…)."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from sqlalchemy import select

from ..deps import DB, Actor, AppSettings, get_or_404, project_by_key
from ..models import Attachment, Run
from ..schemas import ToolReportOut
from ..services.attachments import MAX_ATTACHMENT_BYTES
from ..services.reports import MAX_REPORT_BYTES, save_report, view_url

router = APIRouter(tags=["tool reports"])
MAX_UPLOAD = max(MAX_ATTACHMENT_BYTES, 100 * 1024 * 1024)


def report_out(settings, a: Attachment, run: Run) -> ToolReportOut:
    return ToolReportOut(
        id=a.id, run_id=run.id, run_name=run.name, run_kind=run.kind.value, project_key=run.project.key,
        tool=a.tool or "other", title=a.caption, filename=a.filename, size=a.size, created_by=a.created_by,
        created_at=a.created_at, view_url=view_url(settings, a),
    )


@router.post("/runs/{run_id}/reports", response_model=ToolReportOut, status_code=status.HTTP_201_CREATED)
async def upload_report(run_id: int, db: DB, actor: Actor, settings: AppSettings,
                        file: UploadFile = File(..., description=".html report, or .zip of a report folder"),
                        tool: str = Form("other"), title: str | None = Form(None)):
    run = get_or_404(db, Run, run_id)
    data = await file.read(min(MAX_UPLOAD, MAX_REPORT_BYTES) + 1)
    if len(data) > min(MAX_UPLOAD, MAX_REPORT_BYTES):
        from fastapi import HTTPException

        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "upload exceeds 100 MB")
    a = save_report(db, settings, run, data, file.filename or "report.html", tool=tool, title=title, actor=actor)
    db.commit()
    return report_out(settings, a, run)


@router.get("/runs/{run_id}/reports", response_model=list[ToolReportOut])
def run_reports(run_id: int, db: DB, settings: AppSettings):
    run = get_or_404(db, Run, run_id)
    rows = db.scalars(select(Attachment).where(Attachment.run_id == run_id, Attachment.kind == "report")
                      .order_by(Attachment.created_at, Attachment.id)).all()
    return [report_out(settings, a, run) for a in rows]


@router.get("/tool-reports", response_model=list[ToolReportOut])
def list_reports(db: DB, settings: AppSettings, project: str | None = None, tool: str | None = None,
                 limit: int = Query(50, le=500)):
    stmt = select(Attachment, Run).join(Run, Attachment.run_id == Run.id).where(Attachment.kind == "report")
    if project:
        stmt = stmt.where(Attachment.project_id == project_by_key(db, project).id)
    if tool:
        stmt = stmt.where(Attachment.tool == tool)
    rows = db.execute(stmt.order_by(Attachment.created_at.desc(), Attachment.id.desc()).limit(limit)).all()
    return [report_out(settings, a, run) for a, run in rows]
