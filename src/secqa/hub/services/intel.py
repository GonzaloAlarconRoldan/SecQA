"""Turn a `secqa intel` report into findings + a compact run summary."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Run
from ..schemas import IngestResult
from .findings import ingest_findings

SEVERITIES = {"critical", "high", "medium", "low", "info"}
MAX_WATCHLIST = 40
WATCH_FIELDS = ("keyword", "id", "published", "severity", "score", "summary", "kev", "match", "url")


def _s(value: Any, limit: int = 500) -> str | None:
    return str(value)[:limit] if value not in (None, "") else None


def affected_to_finding(a: dict[str, Any]) -> dict[str, Any]:
    comp = a.get("component") or {}
    name, version = _s(comp.get("name"), 200) or "?", _s(comp.get("version"), 100) or "?"
    label = (a.get("cves") or [None])[0] or a.get("id") or "advisory"
    lines = [_s(a.get("summary"), 2000) or ""]
    kev = a.get("kev")
    if kev:
        lines.append(f"**Actively exploited — CISA KEV** (added {kev.get('date_added')}, "
                     f"federal due date {kev.get('due_date')}, ransomware use: {kev.get('ransomware')}). "
                     f"Required action: {kev.get('required_action')}")
    if a.get("epss") is not None:
        lines.append(f"**EPSS:** {float(a['epss']):.1%} probability of exploitation in the next 30 days "
                     f"(percentile {float(a.get('epss_percentile') or 0):.0%}).")
    if a.get("priority_reason"):
        lines.append(f"**Prioritised:** {a['priority_reason']} (advisory severity: {a.get('base_severity')}).")
    refs = [a.get("url"), *(a.get("references") or [])]
    lines.append("**Sources:** " + " · ".join(f"`{r}`" for r in refs if r))
    fix = a.get("recommended_fix")
    sev = a.get("severity") if a.get("severity") in SEVERITIES else "medium"
    cwe = (a.get("cwe_ids") or [None])[0]
    return {
        "source": "sca",
        "tool": "secqa-intel/osv",
        "rule_id": _s(a.get("id"), 200),
        "category": "vulnerable-dependency",
        "title": f"{name}@{version}: {label} — {_s(a.get('summary'), 300) or 'known vulnerability'}"[:500],
        "description": "\n\n".join(filter(None, lines)),
        "severity": sev,
        "cvss_score": a.get("cvss_score"),
        "cvss_vector": _s(a.get("cvss_vector"), 200),
        "cwe_id": _s(cwe, 32),
        "file_path": _s(comp.get("source"), 1000),
        "evidence": f"{comp.get('ecosystem')} {name} {version}" + (" (dev dependency)" if comp.get("dev") else ""),
        "remediation": (f"Upgrade {name} to {fix} or later." if fix else
                        "No fixed version published for this line — replace the component or apply the "
                        "vendor mitigation."),
    }


def ingest_intel(db: Session, run: Run, report: dict[str, Any], actor: str) -> IngestResult:
    affected = [a for a in report.get("affected") or [] if isinstance(a, dict)]
    result = ingest_findings(db, run, [affected_to_finding(a) for a in affected], actor)
    kev_hits = [{"id": a.get("id"), "cve": (a.get("kev") or {}).get("cve"),
                 "component": f"{(a.get('component') or {}).get('name')}@{(a.get('component') or {}).get('version')}",
                 "due_date": (a.get("kev") or {}).get("due_date"),
                 "ransomware": (a.get("kev") or {}).get("ransomware")}
                for a in affected if a.get("kev")]
    summary = dict(run.summary or {})
    summary["intel"] = {
        "generated_at": report.get("generated_at"),
        "window_days": report.get("window_days"),
        "sources": report.get("sources") or {},
        "stats": report.get("stats") or {},
        "kev": kev_hits,
        "watchlist": [{k: w.get(k) for k in WATCH_FIELDS}
                      for w in (report.get("watchlist") or [])[:MAX_WATCHLIST] if isinstance(w, dict)],
    }
    run.summary = summary
    result.detail = {"kev": len(kev_hits), "watchlist": len(summary["intel"]["watchlist"])}
    return result
