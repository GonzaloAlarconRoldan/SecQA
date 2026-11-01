"""FastAPI application factory for the SecQA Hub."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .. import __version__
from ..mapping import load_mapping
from .config import Settings, get_settings
from .db import Database, upgrade_schema
from .deps import AppSettings, require_token
from .models import (
    Attachment,
    DefectKind,
    DefectStatus,
    Priority,
    ResultStatus,
    RunKind,
    RunStatus,
    Severity,
    TestCaseStatus,
    TestType,
    TriageStatus,
)
from .routers import defects, findings, insights, projects, reports, runs, testcases
from .services.reports import SANDBOX_CSP, verify

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings)
    upgrade_schema(db.engine)
    settings.attachments_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="SecQA Hub",
        version=__version__,
        description="Central store for security & performance test runs, test cases and defects.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.db = db

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/meta", tags=["meta"])
    def meta(s: AppSettings) -> dict:
        def values(e):
            return [m.value for m in e]

        return {
            "version": __version__,
            "auth_required": bool(s.api_token),
            "sla_days": {sev: s.sla_days(sev) for sev in ("critical", "high", "medium", "low")},
            "perf_regression_tolerance": s.perf_regression_tolerance,
            "enums": {
                "severity": values(Severity),
                "run_kind": values(RunKind),
                "run_status": values(RunStatus),
                "triage_status": values(TriageStatus),
                "defect_kind": values(DefectKind),
                "defect_status": values(DefectStatus),
                "priority": values(Priority),
                "test_type": values(TestType),
                "test_case_status": values(TestCaseStatus),
                "result_status": values(ResultStatus),
            },
            "categories": load_mapping(),
        }

    protected = [Depends(require_token)]
    for router in (projects.router, runs.router, findings.router, defects.router,
                   testcases.router, insights.router, reports.router):
        app.include_router(router, prefix="/api", dependencies=protected)

    @app.get("/r/{report_id}/{exp}/{sig}/{path:path}", include_in_schema=False)
    def view_report(report_id: int, exp: int, sig: str, path: str):
        """Serve a tool's HTML report in a sandboxed, opaque origin (see services/reports.py)."""
        if not verify(settings, report_id, exp, sig):
            raise HTTPException(403, "link expired or invalid — reopen the report from the Hub")
        with db.SessionLocal() as session:
            a = session.get(Attachment, report_id)
        if a is None or a.kind != "report":
            raise HTTPException(404)
        root = (settings.attachments_dir / a.storage_path).resolve()
        target = (root / (path or a.entry or "index.html")).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404)
        media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return FileResponse(target, media_type=media, headers={
            "Content-Security-Policy": SANDBOX_CSP, "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "Cache-Control": "private, max-age=600",
            "Cross-Origin-Resource-Policy": "same-origin",
        })

    if STATIC_DIR.joinpath("index.html").exists():
        # Allow-list built once at startup: the request path is only a dictionary key and never
        # reaches the filesystem, so traversal is impossible by construction.
        static_files = {p.relative_to(STATIC_DIR).as_posix(): p for p in STATIC_DIR.rglob("*") if p.is_file()}
        index_html = STATIC_DIR / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(static_files.get(full_path, index_html))

    return app
