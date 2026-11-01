"""Read-only aggregates: overview KPIs, performance trends, compliance matrix, reports & exports."""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import timedelta
from importlib import resources
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, PackageLoader, select_autoescape
from sqlalchemy import func, select

from ... import __version__
from ..deps import DB, get_or_404, project_by_key
from ..models import (
    OPEN_DEFECT_STATUSES,
    Defect,
    DefectStatus,
    Finding,
    PerfMetric,
    ResultStatus,
    Run,
    RunKind,
    Severity,
    TestCase,
    TestResult,
    TriageStatus,
    utcnow,
)
from ..schemas import DefectOut, FindingOut, RunOut
from ..services.defects import is_sla_breached
from .runs import run_out

router = APIRouter(tags=["insights"])

ACTIVE_TRIAGE = [TriageStatus.new, TriageStatus.confirmed]
SEVERITIES = [s.value for s in Severity]
_jinja = Environment(loader=PackageLoader("secqa.hub", "templates"), autoescape=select_autoescape(["html"]))


def _pid(db, project: str | None) -> int | None:
    return project_by_key(db, project).id if project else None


def _scoped(stmt, column, pid):
    return stmt.where(column == pid) if pid is not None else stmt


@router.get("/stats/overview")
def overview(db: DB, project: str | None = None):
    pid = _pid(db, project)
    now = utcnow()

    open_defects = db.scalars(_scoped(select(Defect).where(Defect.status.in_(OPEN_DEFECT_STATUSES)),
                                      Defect.project_id, pid)).all()
    by_sev = {s: 0 for s in SEVERITIES}
    for d in open_defects:
        by_sev[d.severity.value] += 1
    breached = sum(1 for d in open_defects if is_sla_breached(d, now))

    resolved = db.scalars(_scoped(
        select(Defect).where(Defect.resolved_at.is_not(None), Defect.resolved_at >= now - timedelta(days=90)),
        Defect.project_id, pid)).all()
    mttr = (sum((d.resolved_at - d.created_at).total_seconds() for d in resolved) / len(resolved) / 86400
            if resolved else None)

    by_status = dict(db.execute(_scoped(select(Defect.status, func.count()).group_by(Defect.status),
                                        Defect.project_id, pid)).all())
    by_kind = dict(db.execute(_scoped(
        select(Defect.kind, func.count()).where(Defect.status.in_(OPEN_DEFECT_STATUSES)).group_by(Defect.kind),
        Defect.project_id, pid)).all())

    pending_triage = db.scalar(_scoped(
        select(func.count()).select_from(Finding).where(Finding.triage_status == TriageStatus.new),
        Finding.project_id, pid)) or 0
    by_category = db.execute(_scoped(
        select(Finding.category, func.count().label("n"))
        .where(Finding.triage_status.in_(ACTIVE_TRIAGE)).group_by(Finding.category)
        .order_by(func.count().desc()).limit(10), Finding.project_id, pid)).all()
    by_source = dict(db.execute(_scoped(
        select(Finding.source, func.count()).where(Finding.triage_status.in_(ACTIVE_TRIAGE))
        .group_by(Finding.source), Finding.project_id, pid)).all())

    since = now - timedelta(days=30)
    results = dict(db.execute(_scoped(
        select(TestResult.status, func.count()).join(Run).where(TestResult.created_at >= since)
        .group_by(TestResult.status), Run.project_id, pid)).all())
    executed = sum(v for k, v in results.items() if k is not ResultStatus.skipped)
    pass_rate = results.get(ResultStatus.passed, 0) / executed if executed else None
    runs_30d = db.scalar(_scoped(select(func.count()).select_from(Run).where(Run.started_at >= since),
                                 Run.project_id, pid)) or 0

    # severity trend over the last 20 security runs (excludes suppressed findings)
    sec_runs = db.scalars(_scoped(
        select(Run).where(Run.kind == RunKind.security).order_by(Run.started_at.desc(), Run.id.desc()).limit(20),
        Run.project_id, pid)).all()[::-1]
    sev_counts: dict[int, dict[str, int]] = defaultdict(dict)
    if sec_runs:
        for run_id, sev, n in db.execute(
            select(Finding.run_id, Finding.severity, func.count())
            .where(Finding.run_id.in_([r.id for r in sec_runs]), Finding.triage_status.in_(ACTIVE_TRIAGE))
            .group_by(Finding.run_id, Finding.severity)
        ).all():
            sev_counts[run_id][sev.value] = n
    findings_trend = [{"run_id": r.id, "started_at": r.started_at.isoformat() + "Z",
                       **{s: sev_counts[r.id].get(s, 0) for s in SEVERITIES}} for r in sec_runs]

    # defects opened vs resolved per ISO week, last 12 weeks
    weeks_start = now - timedelta(weeks=12)
    flow: dict[str, dict[str, int]] = {}
    for i in range(12, -1, -1):
        wk = (now - timedelta(weeks=i)).strftime("%G-W%V")
        flow[wk] = {"opened": 0, "resolved": 0}
    for d in db.scalars(_scoped(select(Defect).where(
            (Defect.created_at >= weeks_start) | (Defect.resolved_at >= weeks_start)), Defect.project_id, pid)):
        if d.created_at >= weeks_start:
            flow.setdefault(d.created_at.strftime("%G-W%V"), {"opened": 0, "resolved": 0})["opened"] += 1
        if d.resolved_at and d.resolved_at >= weeks_start:
            flow.setdefault(d.resolved_at.strftime("%G-W%V"), {"opened": 0, "resolved": 0})["resolved"] += 1
    defect_flow = [{"week": k, **v} for k, v in sorted(flow.items())]

    recent = db.scalars(_scoped(select(Run).order_by(Run.started_at.desc(), Run.id.desc()).limit(8),
                                Run.project_id, pid)).all()

    return {
        "kpis": {
            "open_defects": len(open_defects),
            "critical_open": by_sev["critical"],
            "high_open": by_sev["high"],
            "sla_breached": breached,
            "mttr_days": round(mttr, 1) if mttr is not None else None,
            "pending_triage": pending_triage,
            "runs_30d": runs_30d,
            "pass_rate_30d": round(pass_rate, 4) if pass_rate is not None else None,
        },
        "open_defects_by_severity": by_sev,
        "defects_by_status": {k.value: v for k, v in by_status.items()},
        "open_defects_by_kind": {k.value: v for k, v in by_kind.items()},
        "findings_by_category": [{"category": c, "count": n} for c, n in by_category],
        "findings_by_source": by_source,
        "findings_trend": findings_trend,
        "defect_flow": defect_flow,
        "perf_trend": perf_trend(db, project, limit=20),
        "recent_runs": [run_out(db, r) for r in recent],
    }


@router.get("/perf/trend")
def perf_trend(db: DB, project: str | None = None, scenario: str | None = None,
               name: str = "__total__", limit: int = Query(30, le=200)):
    pid = _pid(db, project)
    stmt = (select(PerfMetric, Run).join(Run)
            .where(Run.kind == RunKind.performance, PerfMetric.name == name))
    if scenario:
        stmt = stmt.where(PerfMetric.scenario == scenario)
    rows = db.execute(_scoped(stmt.order_by(Run.started_at.desc(), Run.id.desc()).limit(limit),
                              Run.project_id, pid)).all()
    return [{
        "run_id": run.id, "run_name": run.name, "started_at": run.started_at.isoformat() + "Z",
        "scenario": m.scenario, "is_baseline": run.is_baseline, "status": run.status.value,
        "p95_ms": m.p95_ms, "p99_ms": m.p99_ms, "avg_ms": m.avg_ms, "rps": m.rps,
        "error_rate": m.error_rate, "requests": m.requests, "vus_max": m.vus_max,
    } for m, run in rows][::-1]


@router.get("/perf/scenarios")
def perf_scenarios(db: DB, project: str | None = None):
    pid = _pid(db, project)
    rows = db.execute(_scoped(select(PerfMetric.scenario, PerfMetric.name).join(Run).distinct(),
                              Run.project_id, pid)).all()
    out: dict[str, list[str]] = defaultdict(list)
    for scenario, name in rows:
        out[scenario].append(name)
    return {k: sorted(v, key=lambda n: (n != "__total__", n)) for k, v in out.items()}


def _frameworks() -> dict[str, dict[str, str]]:
    raw = json.loads(resources.files("secqa.data").joinpath("frameworks.json").read_text("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@router.get("/compliance")
def compliance(db: DB, project: str | None = None):
    """Coverage matrix per OWASP Top 10, OWASP API Top 10 and ISO 27001 Annex A control."""
    pid = _pid(db, project)
    fields = {"owasp": (Finding.owasp_id, Defect.owasp_id, TestCase.owasp_id),
              "iso": (Finding.iso_control, Defect.iso_control, TestCase.iso_control)}

    def counts(col_f, col_d, col_t):
        f = dict(db.execute(_scoped(select(col_f, func.count()).where(Finding.triage_status.in_(ACTIVE_TRIAGE))
                                    .group_by(col_f), Finding.project_id, pid)).all())
        d = dict(db.execute(_scoped(select(col_d, func.count()).where(Defect.status.in_(OPEN_DEFECT_STATUSES))
                                    .group_by(col_d), Defect.project_id, pid)).all())
        t = dict(db.execute(_scoped(select(col_t, func.count()).group_by(col_t), TestCase.project_id, pid)).all())
        return f, d, t

    owasp_counts = counts(*fields["owasp"])
    iso_counts = counts(*fields["iso"])
    result = {}
    for fw, items in _frameworks().items():
        f, d, t = iso_counts if fw.startswith("iso") else owasp_counts
        rows = []
        for item_id, title in items.items():
            nf, nd, nt = f.get(item_id, 0), d.get(item_id, 0), t.get(item_id, 0)
            state = "fail" if nd else "warn" if nf else "pass" if nt else "untested"
            rows.append({"id": item_id, "title": title, "open_findings": nf, "open_defects": nd,
                         "test_cases": nt, "state": state})
        result[fw] = rows
    return result


# ---- reports & exports -----------------------------------------------------

REPORT_TEXT = {
    "en": {"title": "Security & Performance QA Report", "summary": "Executive summary",
           "defects": "Tracked defects", "findings": "Confirmed findings", "perf": "Performance",
           "runs": "Runs included", "generated": "Generated", "severity": "Severity", "status": "Status",
           "location": "Location", "remediation": "Remediation", "none": "Nothing to report.",
           "open": "Open defects", "breached": "SLA breached", "confidential": "Confidential",
           "p95": "p95 latency", "errors": "Error rate", "rps": "Throughput"},
    "es": {"title": "Reporte de QA de Seguridad y Performance", "summary": "Resumen ejecutivo",
           "defects": "Defectos registrados", "findings": "Hallazgos confirmados", "perf": "Performance",
           "runs": "Ejecuciones incluidas", "generated": "Generado", "severity": "Severidad",
           "status": "Estado", "location": "Ubicación", "remediation": "Remediación",
           "none": "Nada que reportar.", "open": "Defectos abiertos", "breached": "SLA vencido",
           "confidential": "Confidencial", "p95": "Latencia p95", "errors": "Tasa de error",
           "rps": "Throughput"},
}


@router.get("/reports/html", response_class=HTMLResponse)
def report_html(
    db: DB,
    project: str,
    run_id: int | None = None,
    severity: list[Severity] | None = Query(None),
    lang: Literal["en", "es"] = "en",
    include_closed: bool = False,
):
    """Shareable report. Only human-validated data: confirmed findings and tracked defects
    — never untriaged tool output. Print to PDF from the browser."""
    proj = project_by_key(db, project)
    d_stmt = select(Defect).where(Defect.project_id == proj.id)
    f_stmt = select(Finding).where(Finding.project_id == proj.id, Finding.triage_status == TriageStatus.confirmed)
    runs: list[Run]
    if run_id:
        run = get_or_404(db, Run, run_id)
        runs = [run]
        f_stmt = f_stmt.where(Finding.run_id == run_id)
        linked = select(Finding.defect_id).where(Finding.run_id == run_id, Finding.defect_id.is_not(None))
        d_stmt = d_stmt.where((Defect.found_in_run_id == run_id) | Defect.id.in_(linked))
    else:
        runs = list(db.scalars(select(Run).where(Run.project_id == proj.id)
                               .order_by(Run.started_at.desc(), Run.id.desc()).limit(15)))
    if not include_closed:
        d_stmt = d_stmt.where(Defect.status.notin_([DefectStatus.closed, DefectStatus.wont_fix,
                                                    DefectStatus.duplicate]))
    if severity:
        d_stmt = d_stmt.where(Defect.severity.in_(severity))
        f_stmt = f_stmt.where(Finding.severity.in_(severity))

    rank = {s: i for i, s in enumerate(Severity)}
    defects = sorted(db.scalars(d_stmt).all(), key=lambda d: (rank[d.severity], d.priority.value))
    findings = sorted(db.scalars(f_stmt).all(), key=lambda f: rank[f.severity])
    perf_runs = [r for r in runs if r.kind is RunKind.performance]
    perf = {r.id: [m for m in r.perf_metrics if m.name == "__total__"] for r in perf_runs}

    sev_counts = {s: 0 for s in SEVERITIES}
    for d in defects:
        sev_counts[d.severity.value] += 1

    html = _jinja.get_template("report.html").render(
        t=REPORT_TEXT[lang], lang=lang, project=proj, version=__version__,
        generated_at=utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        defects=[DefectOut.model_validate(d).model_copy(update={"sla_breached": is_sla_breached(d)})
                 for d in defects],
        findings=[FindingOut.model_validate(f) for f in findings],
        runs=[RunOut.model_validate(r).model_copy(update={"project_key": proj.key}) for r in runs],
        perf_runs=perf_runs, perf=perf, sev_counts=sev_counts, run_id=run_id,
        breached=sum(1 for d in defects if is_sla_breached(d)),
    )
    return HTMLResponse(html)


@router.get("/export/defects.csv")
def export_defects_csv(db: DB, project: str):
    proj = project_by_key(db, project)
    buf = io.StringIO()
    cols = ["key", "kind", "title", "severity", "priority", "status", "assignee", "reporter", "environment",
            "cwe_id", "owasp_id", "iso_control", "created_at", "due_at", "resolved_at", "closed_at", "sla_breached"]
    w = csv.writer(buf)
    w.writerow(cols)
    for d in db.scalars(select(Defect).where(Defect.project_id == proj.id).order_by(Defect.id)):
        row = DefectOut.model_validate(d).model_copy(update={"sla_breached": is_sla_breached(d)})
        data = row.model_dump(mode="json")
        # Neutralise spreadsheet formula injection (CWE-1236).
        w.writerow([_csv_safe(data.get(c)) for c in cols])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{proj.key}-defects.csv"'})


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/export/findings.sarif")
def export_findings_sarif(db: DB, project: str, run_id: int | None = None):
    """Confirmed findings as SARIF 2.1.0 — e.g. to upload to GitHub code scanning."""
    proj = project_by_key(db, project)
    stmt = select(Finding).where(Finding.project_id == proj.id, Finding.triage_status == TriageStatus.confirmed)
    if run_id:
        stmt = stmt.where(Finding.run_id == run_id)
    level = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "note"}
    score = {"critical": "9.5", "high": "8.0", "medium": "5.5", "low": "2.0", "info": "0.0"}
    rules: dict[str, dict] = {}
    results = []
    for f in db.scalars(stmt):
        rid = f.rule_id or f.category
        rules.setdefault(rid, {
            "id": rid, "shortDescription": {"text": f.title[:200]},
            "properties": {"tags": [t for t in ("security", f.cwe_id, f.owasp_id) if t],
                           "security-severity": score[f.severity.value]},
        })
        loc = {}
        if f.file_path:
            loc = {"physicalLocation": {"artifactLocation": {"uri": f.file_path},
                                        "region": {"startLine": f.line_start or 1}}}
        results.append({"ruleId": rid, "level": level[f.severity.value],
                        "message": {"text": f.description or f.title},
                        "locations": [loc] if loc else [],
                        "partialFingerprints": {"secqa/v1": f.fingerprint}})
    doc = {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
           "runs": [{"tool": {"driver": {"name": "SecQA", "version": __version__,
                                         "informationUri": "https://github.com/GonzaloAlarconRoldan/SecQA",
                                         "rules": list(rules.values())}},
                     "results": results}]}
    return Response(json.dumps(doc, indent=2), media_type="application/sarif+json",
                    headers={"Content-Disposition": f'attachment; filename="{proj.key}-findings.sarif"'})

