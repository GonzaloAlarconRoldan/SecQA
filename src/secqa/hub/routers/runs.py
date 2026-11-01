from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import DB, Actor, AppSettings, get_or_404, project_by_key
from ..models import (
    AuditLog,
    DefectKind,
    Finding,
    PerfMetric,
    Priority,
    ResultStatus,
    Run,
    RunKind,
    RunStatus,
    TestCase,
    TestResult,
    TriageStatus,
    utcnow,
)
from ..parsers.jtl import parse_jtl
from ..parsers.junit import parse_junit
from ..parsers.k6 import parse_k6_summary
from ..parsers.sarif import parse_sarif
from ..schemas import (
    FindingCreate,
    IngestResult,
    Page,
    PerfMetricOut,
    RunCreate,
    RunFinish,
    RunOut,
    RunUpdate,
    TestResultCreate,
    TestResultOut,
)
from ..services.defects import create_defect
from ..services.findings import ingest_findings
from ..services.perf import compare_to_baseline, store_perf

router = APIRouter(tags=["runs"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def run_out(db: Session, run: Run) -> RunOut:
    by_sev = dict(db.execute(
        select(Finding.severity, func.count()).where(
            Finding.run_id == run.id,
            Finding.triage_status.notin_([TriageStatus.false_positive, TriageStatus.accepted_risk]),
        ).group_by(Finding.severity)
    ).all())
    by_res = dict(db.execute(
        select(TestResult.status, func.count()).where(TestResult.run_id == run.id).group_by(TestResult.status)
    ).all())
    duration = (run.finished_at - run.started_at).total_seconds() if run.finished_at else None
    return RunOut.model_validate(run).model_copy(update={
        "project_key": run.project.key,
        "duration_s": duration,
        "findings_by_severity": {k.value: v for k, v in by_sev.items()},
        "results_by_status": {k.value: v for k, v in by_res.items()},
    })


def _merge_summary(run: Run, **parts) -> None:
    summary = dict(run.summary or {})
    summary.update(parts)
    run.summary = summary  # reassign so SQLAlchemy sees the JSON change


@router.get("/runs", response_model=Page[RunOut])
def list_runs(
    db: DB,
    project: str | None = None,
    kind: RunKind | None = None,
    status_: RunStatus | None = Query(None, alias="status"),
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    q = select(Run)
    if project:
        q = q.where(Run.project_id == project_by_key(db, project).id)
    if kind:
        q = q.where(Run.kind == kind)
    if status_:
        q = q.where(Run.status == status_)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    runs = db.scalars(q.order_by(Run.started_at.desc(), Run.id.desc()).limit(limit).offset(offset)).all()
    return Page(items=[run_out(db, r) for r in runs], total=total or 0, limit=limit, offset=offset)


@router.post("/projects/{key}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def start_run(key: str, body: RunCreate, db: DB, actor: Actor):
    project = project_by_key(db, key)
    run = Run(project_id=project.id, triggered_by=body.triggered_by or actor,
              **body.model_dump(exclude={"triggered_by"}))
    db.add(run)
    db.flush()
    db.add(AuditLog(project_id=project.id, run_id=run.id, actor=actor,
                    action=f"started {run.kind.value} run #{run.id}", target=run.target))
    db.commit()
    return run_out(db, run)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: DB):
    return run_out(db, get_or_404(db, Run, run_id))


@router.patch("/runs/{run_id}", response_model=RunOut)
def update_run(run_id: int, body: RunUpdate, db: DB, actor: Actor):
    run = get_or_404(db, Run, run_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("is_baseline"):
        if run.kind is not RunKind.performance:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "only performance runs can be a baseline")
        db.query(Run).filter(Run.project_id == run.project_id, Run.id != run.id).update(
            {Run.is_baseline: False})
        db.add(AuditLog(project_id=run.project_id, run_id=run.id, actor=actor,
                        action=f"marked run #{run.id} as performance baseline"))
    for field, value in changes.items():
        setattr(run, field, value)
    db.commit()
    return run_out(db, run)


@router.post("/runs/{run_id}/finish", response_model=RunOut)
def finish_run(run_id: int, body: RunFinish, db: DB, actor: Actor):
    run = get_or_404(db, Run, run_id)
    run.finished_at = utcnow()
    if body.notes:
        run.notes = body.notes
    run.status = body.status or _infer_status(db, run)
    db.add(AuditLog(project_id=run.project_id, run_id=run.id, actor=actor,
                    action=f"finished run #{run.id} with status {run.status.value}"))
    db.commit()
    return run_out(db, run)


def _infer_status(db: Session, run: Run) -> RunStatus:
    summary = run.summary or {}
    if run.kind is RunKind.performance:
        perf = summary.get("perf", {})
        if perf.get("thresholds_passed") is False or perf.get("regressions"):
            return RunStatus.failed
        return RunStatus.passed
    failed = db.scalar(select(func.count()).where(
        TestResult.run_id == run.id, TestResult.status.in_([ResultStatus.failed, ResultStatus.error])))
    has_results = db.scalar(select(func.count()).where(TestResult.run_id == run.id))
    if has_results:
        return RunStatus.failed if failed else RunStatus.passed
    return RunStatus.completed


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(run_id: int, db: DB):
    db.delete(get_or_404(db, Run, run_id))
    db.commit()


# ---- ingestion -------------------------------------------------------------

@router.post("/runs/{run_id}/findings", response_model=IngestResult)
def add_findings(run_id: int, body: list[FindingCreate], db: DB, actor: Actor):
    run = get_or_404(db, Run, run_id)
    result = ingest_findings(db, run, body, actor)
    db.commit()
    return result


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file exceeds 50 MB")
    return data


@router.post("/runs/{run_id}/ingest/{fmt}", response_model=IngestResult)
async def ingest_file(
    run_id: int,
    fmt: Literal["sarif", "k6", "jtl", "junit"],
    db: DB,
    actor: Actor,
    settings: AppSettings,
    file: UploadFile = File(...),
    source: str | None = Query(None, description="SARIF only: override finding source (sast, sca, …)"),
    scenario: str = Query("default", description="k6/jtl: scenario name, e.g. load, stress"),
    create_defects: bool = Query(True, description="k6/jtl: open a defect when a regression is detected"),
):
    run = get_or_404(db, Run, run_id)
    raw = await _read_upload(file)
    try:
        if fmt == "sarif":
            items = parse_sarif(json.loads(raw), default_source=source)
            result = ingest_findings(db, run, items, actor)
            _merge_summary(run, **{f"sarif:{items[0]['tool'] if items else 'empty'}": result.created})
        elif fmt == "junit":
            junit_rows = parse_junit(raw.decode("utf-8", errors="replace"))
            n = _store_results(db, run, [TestResultCreate(**r) for r in junit_rows])
            result = IngestResult(created=n)
        else:
            parsed = parse_k6_summary(json.loads(raw)) if fmt == "k6" else parse_jtl(raw.decode("utf-8"))
            tool = "k6" if fmt == "k6" else "jmeter"
            store_perf(db, run, parsed, tool, scenario)
            db.refresh(run)
            comparison = compare_to_baseline(db, settings, run)
            regressions = comparison["regressions"] if comparison else []
            _merge_summary(run, perf={
                "tool": tool,
                "thresholds_passed": parsed["thresholds_passed"],
                "baseline_run_id": comparison["baseline_run_id"] if comparison else None,
                "regressions": regressions,
            })
            detail = {"thresholds_passed": parsed["thresholds_passed"], "regressions": len(regressions)}
            if regressions and create_defects:
                defect = _regression_defect(db, settings, run, regressions, parsed["thresholds_passed"], actor)
                detail["defect"] = defect.key
            result = IngestResult(created=len(parsed["rows"]), detail=detail)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"could not parse {fmt}: {exc}") from exc
    db.add(AuditLog(project_id=run.project_id, run_id=run.id, actor=actor,
                    action=f"ingested {fmt} file '{file.filename}'"))
    db.commit()
    return result


def _regression_defect(db: Session, settings, run: Run, regressions: list[dict], thresholds_passed, actor):
    lines = [
        f"- `{r['name']}` **{r['metric']}**: {r['baseline']:.2f} → {r['current']:.2f} ({r['change']:+.1%})"
        if r["metric"] != "error_rate" else
        f"- `{r['name']}` **error_rate**: {r['baseline']:.2%} → {r['current']:.2%}"
        for r in regressions
    ]
    project = run.project
    return create_defect(
        db, settings, project, actor,
        kind=DefectKind.performance,
        title=f"Performance regression in run #{run.id}" + (f" ({run.name})" if run.name else ""),
        description="Metrics degraded beyond tolerance compared to the baseline run:\n\n" + "\n".join(lines),
        severity="high" if thresholds_passed is False else "medium",
        priority=Priority.p2,
        environment=run.environment,
        found_in_run_id=run.id,
        tags=["performance", "regression"],
    )


def _store_results(db: Session, run: Run, items: list[TestResultCreate]) -> int:
    keys = {i.test_case_key for i in items if i.test_case_key}
    cases = {}
    if keys:
        cases = {tc.key: tc.id for tc in db.scalars(
            select(TestCase).where(TestCase.project_id == run.project_id, TestCase.key.in_(keys)))}
    for item in items:
        db.add(TestResult(run_id=run.id, test_case_id=cases.get(item.test_case_key or ""),
                          **item.model_dump(exclude={"test_case_key"})))
    db.flush()
    return len(items)


@router.post("/runs/{run_id}/results", response_model=IngestResult)
def add_results(run_id: int, body: list[TestResultCreate], db: DB):
    run = get_or_404(db, Run, run_id)
    n = _store_results(db, run, body)
    db.commit()
    return IngestResult(created=n)


@router.get("/runs/{run_id}/results", response_model=list[TestResultOut])
def list_results(run_id: int, db: DB):
    get_or_404(db, Run, run_id)
    rows = db.execute(
        select(TestResult, TestCase.key).outerjoin(TestCase, TestResult.test_case_id == TestCase.id)
        .where(TestResult.run_id == run_id).order_by(TestResult.id)
    ).all()
    return [TestResultOut.model_validate(r).model_copy(update={"test_case_key": k}) for r, k in rows]


@router.get("/runs/{run_id}/perf", response_model=list[PerfMetricOut])
def list_perf(run_id: int, db: DB):
    get_or_404(db, Run, run_id)
    return db.scalars(select(PerfMetric).where(PerfMetric.run_id == run_id)
                      .order_by(PerfMetric.scenario, PerfMetric.name != "__total__", PerfMetric.name)).all()


@router.get("/runs/{run_id}/compare")
def compare(run_id: int, db: DB, settings: AppSettings):
    run = get_or_404(db, Run, run_id)
    return compare_to_baseline(db, settings, run) or {"baseline_run_id": None, "comparisons": [],
                                                       "regressions": []}
