"""FastAPI application factory for the SecQA Hub."""
from __future__ import annotations

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
from .routers import defects, findings, insights, projects, runs, testcases

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
                   testcases.router, insights.router):
        app.include_router(router, prefix="/api", dependencies=protected)

    if STATIC_DIR.joinpath("index.html").exists():
        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404)
            candidate = (STATIC_DIR / full_path).resolve()
            if full_path and candidate.is_file() and STATIC_DIR in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app
