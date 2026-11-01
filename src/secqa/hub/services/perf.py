"""Performance ingestion and baseline comparison."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import PerfMetric, Run, RunKind

# metric → higher-is-worse?
COMPARED = {"p95_ms": True, "p99_ms": True, "avg_ms": True, "error_rate": True, "rps": False}


def store_perf(db: Session, run: Run, parsed: dict[str, Any], tool: str, scenario: str) -> list[PerfMetric]:
    db.query(PerfMetric).filter(PerfMetric.run_id == run.id, PerfMetric.scenario == scenario).delete()
    rows = []
    for row in parsed["rows"]:
        metric = PerfMetric(run_id=run.id, scenario=scenario, tool=tool, **row)
        db.add(metric)
        rows.append(metric)
    db.flush()
    return rows


def find_baseline(db: Session, run: Run) -> Run | None:
    return db.scalars(
        select(Run)
        .where(Run.project_id == run.project_id, Run.kind == RunKind.performance,
               Run.is_baseline.is_(True), Run.id != run.id)
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(1)
    ).first()


def compare_to_baseline(db: Session, settings: Settings, run: Run) -> dict[str, Any] | None:
    baseline = find_baseline(db, run)
    if baseline is None:
        return None
    current = {(m.scenario, m.name): m for m in run.perf_metrics}
    base = {(m.scenario, m.name): m for m in baseline.perf_metrics}
    tol = settings.perf_regression_tolerance
    comparisons = []
    regressions = []
    for key, cur in current.items():
        ref = base.get(key)
        if ref is None:
            continue
        for metric, higher_is_worse in COMPARED.items():
            a, b = getattr(ref, metric), getattr(cur, metric)
            if a is None or b is None:
                continue
            if metric == "error_rate":
                # absolute: +1 percentage point beyond tolerance-scaled baseline
                delta = b - a
                regressed = delta > max(0.01, a * tol)
                change = delta
            else:
                if a == 0:
                    continue
                change = (b - a) / a
                regressed = change > tol if higher_is_worse else change < -tol
            entry = {"scenario": key[0], "name": key[1], "metric": metric,
                     "baseline": a, "current": b, "change": round(change, 4), "regressed": regressed}
            comparisons.append(entry)
            if regressed:
                regressions.append(entry)
    return {
        "baseline_run_id": baseline.id,
        "tolerance": tol,
        "comparisons": comparisons,
        "regressions": regressions,
    }
