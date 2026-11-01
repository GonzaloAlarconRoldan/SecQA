"""Realistic demo dataset modelled on OWASP Juice Shop (a deliberately vulnerable app).

Writes straight to the database so history can be back-dated (trends, MTTR, weekly flow).
Deterministic: same output on every run.
"""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..mapping import enrich
from .config import Settings
from .db import Database, upgrade_schema
from .models import (
    AuditLog,
    Defect,
    DefectComment,
    DefectEvent,
    DefectStatus,
    Finding,
    PerfMetric,
    Project,
    Run,
    RunKind,
    RunStatus,
    TestCase,
    TestResult,
    TriageStatus,
    utcnow,
)
from .services.defects import compute_due
from .services.findings import fingerprint

TEAM = ["ana.garcia", "luis.perez", "maria.lopez", "dev.oncall"]

# (category, severity, title, file_path, line, endpoint, tool, source)
VULNS = [
    ("sql-injection", "critical", "SQL injection in login query built by string concatenation",
     "routes/login.ts", 34, "POST /rest/user/login", "semgrep", "sast"),
    ("xss", "high", "DOM XSS: search term bound with bypassSecurityTrustHtml",
     "frontend/src/app/search-result/search-result.component.ts", 151, "/#/search?q=", "semgrep", "sast"),
    ("sql-injection", "high", "NoSQL injection in product reviews update ($where operator)",
     "routes/updateProductReviews.ts", 17, "PATCH /rest/products/reviews", "manual", "api"),
    ("broken-auth", "critical", "JWT accepted with alg=none",
     "lib/insecurity.ts", 54, "Authorization: Bearer", "manual", "api"),
    ("exposed-secret", "high", "RSA private key hardcoded in source",
     "lib/insecurity.ts", 23, None, "gitleaks", "secrets"),
    ("vulnerable-dependency", "high", "jsonwebtoken 0.4.0 — signature bypass (CVE-2015-9235)",
     "package.json", None, None, "osv-scanner", "sca"),
    ("vulnerable-dependency", "medium", "sanitize-html 1.4.2 — XSS bypass (CVE-2016-1000237)",
     "package.json", None, None, "osv-scanner", "sca"),
    ("idor", "high", "Basket of another user readable by changing the id",
     "routes/basket.ts", 19, "GET /rest/basket/{id}", "manual", "api"),
    ("security-misconfiguration", "medium", "Directory listing enabled on /ftp",
     "server.ts", 268, "GET /ftp", "nuclei", "dast"),
    ("security-misconfiguration", "low", "Missing Content-Security-Policy header",
     None, None, "GET /", "zap", "dast"),
    ("api-rate-limiting", "medium", "No rate limit on password reset endpoint",
     "routes/resetPassword.ts", 12, "POST /rest/user/reset-password", "manual", "api"),
    ("sensitive-data-exposure", "medium", "Stack traces with internal paths returned on errors",
     "server.ts", 640, "GET /rest/does-not-exist", "zap", "dast"),
    ("insecure-deserialization", "high", "Sandboxed eval of user-supplied B2B order payload",
     "routes/b2bOrder.ts", 22, "POST /b2b/v2/orders", "semgrep", "sast"),
    ("security-misconfiguration", "info", "Dockerfile runs as root user", "Dockerfile", 1, None,
     "trivy", "sca"),
    ("api-excessive-data-exposure", "medium", "User list API exposes password hashes and TOTP secrets",
     "routes/angular.ts", 9, "GET /api/Users", "manual", "api"),
]

TEST_CASES = [
    ("Authentication", "Login rejects SQL metacharacters", "security", "A03:2021", "CWE-89", "A.8.28"),
    ("Authentication", "JWT with alg=none is rejected", "security", "A07:2021", "CWE-287", "A.8.5"),
    ("Authentication", "Password reset is rate limited", "api", "API4:2023", "CWE-770", "A.8.6"),
    ("Access control", "Users cannot read other users' baskets", "api", "API1:2023", "CWE-639", "A.8.3"),
    ("Access control", "Admin section requires admin role", "security", "A01:2021", "CWE-284", "A.8.3"),
    ("Input handling", "Search output is HTML-encoded", "security", "A03:2021", "CWE-79", "A.8.28"),
    ("Input handling", "File upload accepts only PDF/ZIP under 100 kB", "security", "A04:2021", "CWE-434",
     "A.8.28"),
    ("Hardening", "Security headers present (CSP, HSTS, XCTO)", "security", "A05:2021", "CWE-16", "A.8.9"),
    ("Hardening", "No secrets in repository", "security", "A02:2021", "CWE-798", "A.8.24"),
    ("Hardening", "Dependencies free of known critical CVEs", "security", "A06:2021", "CWE-1104", "A.8.8"),
    ("Performance", "Product search p95 < 500 ms at 50 VUs", "performance", None, None, "A.8.6"),
    ("Performance", "Login p95 < 800 ms at 50 VUs, error rate < 1 %", "performance", None, None, "A.8.6"),
    ("Checkout", "Order total matches basket after coupon", "functional", None, None, None),
    ("Checkout", "Negative quantities are rejected", "functional", "A04:2021", "CWE-20", "A.8.28"),
]

ENDPOINTS = {
    "GET /rest/products/search": 120,
    "POST /rest/user/login": 210,
    "GET /api/Products": 80,
    "GET /rest/basket/{id}": 95,
}


def seed(settings: Settings, project_key: str = "JUICE") -> str:
    db_ = Database(settings)
    upgrade_schema(db_.engine)
    with db_.SessionLocal() as db:
        if db.scalars(select(Project).where(Project.key == project_key)).first():
            return f"project {project_key} already exists — nothing to do"
        _seed(db, settings, project_key)
        db.commit()
    return f"seeded demo project {project_key}"


def _seed(db: Session, settings: Settings, key: str) -> None:
    rnd = random.Random(42)  # noqa: S311 - deterministic demo data, not crypto
    now = utcnow()
    start = now - timedelta(days=84)

    project = Project(key=key, name="OWASP Juice Shop", repo_url="https://github.com/juice-shop/juice-shop",
                      description="Deliberately insecure web app used as the SecQA demo target.",
                      created_at=start)
    db.add(project)
    db.flush()

    # --- test cases
    cases: list[TestCase] = []
    for i, (suite, title, ttype, owasp, cwe, iso) in enumerate(TEST_CASES, 1):
        tc = TestCase(
            project_id=project.id, key=f"{key}-TC-{i}", title=title, type=ttype, suite=suite,
            priority="P1" if i <= 4 else "P2" if i <= 10 else "P3",
            description=f"Verify: {title.lower()}.", owasp_id=owasp, cwe_id=cwe, iso_control=iso,
            preconditions="Juice Shop running locally on http://127.0.0.1:3000 (docker compose).",
            steps=[{"action": "Prepare request/data for the scenario", "expected": "Environment ready"},
                   {"action": f"Execute: {title}", "expected": "Control behaves as specified"},
                   {"action": "Capture evidence and record result", "expected": "Evidence attached"}],
            expected_result="The application enforces the control without errors.",
            automated=ttype in ("performance", "api") or i % 3 == 0,
            automation_ref="perf/scenarios/load.js" if ttype == "performance" else None,
            tags=[suite.lower().replace(" ", "-")], created_at=start, updated_at=start,
        )
        db.add(tc)
        cases.append(tc)
    project.testcase_seq = len(cases)
    db.flush()

    # --- security runs: vulnerabilities get discovered then fixed over time
    sec_runs: list[Run] = []
    defects_by_vuln: dict[int, Defect] = {}
    fixed_after = {0: 5, 4: 3, 5: 4, 6: 3, 8: 6}   # vuln index → last run it appears in
    first_seen = {0: 0, 1: 0, 2: 1, 3: 1, 4: 0, 5: 0, 6: 0, 7: 2, 8: 2, 9: 0, 10: 3, 11: 4, 12: 5, 13: 0, 14: 6}
    commits = [f"{rnd.getrandbits(160):040x}" for _ in range(8)]

    for r in range(8):
        started = start + timedelta(days=r * 11 + 1, hours=rnd.randint(8, 18))
        run = Run(project_id=project.id, kind=RunKind.security, status=RunStatus.completed,
                  name=f"Nightly security scan #{r + 1}", target="http://127.0.0.1:3000",
                  environment="local-docker", branch="main", commit_sha=commits[r],
                  triggered_by="agent:claude-code", started_at=started,
                  finished_at=started + timedelta(minutes=rnd.randint(14, 38)),
                  stack_detected={"languages": ["TypeScript"], "frameworks": ["Express", "Angular"],
                                  "has_api": True, "api_kind": ["rest"], "db": ["SQLite", "MarsDB"]})
        db.add(run)
        db.flush()
        sec_runs.append(run)
        db.add(AuditLog(project_id=project.id, run_id=run.id, actor="agent:claude-code", at=started,
                        action=f"started security run #{run.id}", target=run.target))
        db.add(AuditLog(project_id=project.id, run_id=run.id, actor="agent:claude-code",
                        at=started + timedelta(minutes=5), action="zap-baseline.py -t http://127.0.0.1:3000",
                        target="127.0.0.1:3000"))

        for idx, (cat, sev, title, path, line, endpoint, tool, source) in enumerate(VULNS):
            if r < first_seen[idx] or r > fixed_after.get(idx, 7):
                continue
            data = enrich({"category": cat, "severity": sev, "title": title, "file_path": path,
                           "line_start": line, "endpoint": endpoint, "tool": tool, "source": source})
            fp = fingerprint(data)
            f = Finding(run_id=run.id, project_id=project.id, fingerprint=fp, created_at=started,
                        description=f"{title}. Detected by {tool} during {source.upper()} phase.",
                        evidence=_evidence(cat, endpoint), remediation=_remediation(cat),
                        line_end=line, **data)
            if idx == 9:
                f.triage_status = TriageStatus.accepted_risk
                f.reviewed_by, f.reviewed_at = "maria.lopez", started
                f.review_comment = "CSP rollout planned for Q1; risk accepted until then."
            elif idx == 13:
                f.triage_status = TriageStatus.false_positive if r >= 1 else TriageStatus.new
                f.reviewed_by = "luis.perez" if r >= 1 else None
            elif idx in defects_by_vuln:
                f.defect_id = defects_by_vuln[idx].id
                f.triage_status = TriageStatus.confirmed
            elif r < 7:
                f.triage_status = TriageStatus.confirmed
                f.reviewed_by, f.reviewed_at = rnd.choice(TEAM[:3]), started + timedelta(hours=3)
                db.add(f)
                db.flush()
                defects_by_vuln[idx] = _make_defect(db, settings, project, f, run, started, rnd)
                f.defect_id = defects_by_vuln[idx].id
            db.add(f)

        for tc in cases:
            if _v(tc.type) in ("security", "api"):
                status = rnd.choices(["passed", "failed", "skipped"], [6, 3, 1])[0] if r < 6 else \
                    rnd.choices(["passed", "failed"], [8, 2])[0]
                db.add(TestResult(run_id=run.id, test_case_id=tc.id, name=tc.title, status=status,
                                  duration_ms=rnd.uniform(400, 9000), created_at=started,
                                  message="Assertion failed: control not enforced" if status == "failed" else None))
        db.flush()

    # --- lifecycle progression for defects
    for idx, d in defects_by_vuln.items():
        last = fixed_after.get(idx)
        if last is not None and last < 7:
            fixed_at = sec_runs[last].started_at + timedelta(days=rnd.randint(2, 6))
            _transition(db, d, "in_progress", d.created_at + timedelta(days=1), d.assignee or "ana.garcia")
            _transition(db, d, "fixed", fixed_at, d.assignee or "ana.garcia")
            if last < 5:
                _transition(db, d, "verified", fixed_at + timedelta(days=2), "agent:claude-code")
                _transition(db, d, "closed", fixed_at + timedelta(days=3), "maria.lopez")
        elif idx in (1, 7, 12):
            _transition(db, d, "in_progress", d.created_at + timedelta(days=2), d.assignee or "luis.perez")
        elif idx in (2, 3):
            _transition(db, d, "triaged", d.created_at + timedelta(hours=6), "maria.lopez")
        db.add(DefectComment(defect_id=d.id, author="agent:claude-code", created_at=d.created_at,
                             body="Reproduced against local Docker build. Evidence attached in the finding."))
        if d.status in (DefectStatus.in_progress, DefectStatus.fixed, DefectStatus.closed):
            db.add(DefectComment(defect_id=d.id, author=d.assignee or "ana.garcia",
                                 created_at=d.created_at + timedelta(days=1),
                                 body="Taking this one. Fix will use parameterised queries / proper encoding."))

    # an operational incident, no finding behind it
    inc_at = now - timedelta(days=9)
    project.defect_seq += 1
    inc = Defect(project_id=project.id, key=f"{key}-{project.defect_seq}", kind="incident",
                 title="Checkout returned HTTP 500 for 12 minutes after deploy",
                 description="Spike of 500s on POST /api/BasketItems right after release 17.1.0. "
                             "Rolled back; root cause was a missing DB migration.",
                 severity="high", priority="P1", status="closed", assignee="dev.oncall", reporter="dev.oncall",
                 environment="staging", created_at=inc_at, updated_at=inc_at + timedelta(hours=3),
                 resolved_at=inc_at + timedelta(hours=1), closed_at=inc_at + timedelta(hours=3),
                 due_at=compute_due(settings, "high", inc_at), tags=["incident", "checkout"])
    db.add(inc)

    # --- performance runs: baseline at #3, regression in the last run
    perf_runs = []
    for r in range(7):
        started = start + timedelta(days=r * 12 + 4, hours=21)
        regression = r == 6
        run = Run(project_id=project.id, kind=RunKind.performance, name=f"Load test — release 17.{r}",
                  target="http://127.0.0.1:3000", environment="local-docker", branch="main",
                  commit_sha=commits[min(r, 7)], triggered_by="agent:claude-code", started_at=started,
                  finished_at=started + timedelta(minutes=6), is_baseline=(r == 3),
                  status=RunStatus.failed if regression else RunStatus.passed)
        db.add(run)
        db.flush()
        perf_runs.append(run)
        total_reqs, total_fail, weighted = 0, 0, []
        for ep, base in ENDPOINTS.items():
            factor = 1.0 - min(r, 3) * 0.06 + rnd.uniform(-0.04, 0.04)
            if regression and "search" in ep:
                factor *= 1.9
            p95 = base * factor
            reqs = rnd.randint(2800, 4200)
            err = 0.002 + rnd.uniform(0, 0.003) + (0.018 if regression and "search" in ep else 0)
            fails = int(reqs * err)
            total_reqs += reqs
            total_fail += fails
            weighted.append((p95, reqs))
            db.add(PerfMetric(run_id=run.id, scenario="load", name=ep, tool="k6", requests=reqs,
                              failures=fails, error_rate=round(err, 5), rps=round(reqs / 300, 2),
                              avg_ms=round(p95 * 0.45, 1), min_ms=round(p95 * 0.08, 1),
                              med_ms=round(p95 * 0.4, 1), p90_ms=round(p95 * 0.82, 1), p95_ms=round(p95, 1),
                              p99_ms=round(p95 * 1.6, 1), max_ms=round(p95 * 3.1, 1), duration_s=300,
                              thresholds={f"http_req_duration{{name:{ep}}}: p(95)<500": p95 < 500}))
        p95_total = sum(p * n for p, n in weighted) / total_reqs
        err_total = total_fail / total_reqs
        db.add(PerfMetric(run_id=run.id, scenario="load", name="__total__", tool="k6", requests=total_reqs,
                          failures=total_fail, error_rate=round(err_total, 5), rps=round(total_reqs / 300, 2),
                          avg_ms=round(p95_total * 0.45, 1), min_ms=4.2, med_ms=round(p95_total * 0.4, 1),
                          p90_ms=round(p95_total * 0.82, 1), p95_ms=round(p95_total, 1),
                          p99_ms=round(p95_total * 1.6, 1), max_ms=round(p95_total * 3.4, 1), vus_max=50,
                          duration_s=300,
                          thresholds={"http_req_duration: p(95)<500": p95_total < 500,
                                      "http_req_failed: rate<0.01": err_total < 0.01}))
        run.summary = {"perf": {"tool": "k6", "thresholds_passed": err_total < 0.01,
                                "baseline_run_id": perf_runs[3].id if r > 3 else None,
                                "regressions": [{"name": "GET /rest/products/search", "metric": "p95_ms"}]
                                if regression else []}}
    db.flush()
    reg_at = perf_runs[-1].started_at + timedelta(minutes=7)
    project.defect_seq += 1
    db.add(Defect(project_id=project.id, key=f"{key}-{project.defect_seq}", kind="performance",
                  title=f"Performance regression in run #{perf_runs[-1].id} (Load test — release 17.6)",
                  description="Metrics degraded beyond tolerance compared to the baseline run:\n\n"
                              "- `GET /rest/products/search` **p95_ms**: +88%\n"
                              "- `GET /rest/products/search` **error_rate**: 0.4% → 2.2%",
                  severity="high", priority="P2", status="new", reporter="agent:claude-code",
                  environment="local-docker", found_in_run_id=perf_runs[-1].id, created_at=reg_at,
                  updated_at=reg_at, due_at=compute_due(settings, "high", reg_at),
                  tags=["performance", "regression"]))

    # --- a functional regression run
    fr_at = now - timedelta(days=2)
    fr = Run(project_id=project.id, kind=RunKind.functional, name="Checkout regression suite",
             target="http://127.0.0.1:3000", environment="local-docker", branch="main",
             commit_sha=commits[-1], triggered_by="ci:github-actions", started_at=fr_at,
             finished_at=fr_at + timedelta(minutes=4), status=RunStatus.failed)
    db.add(fr)
    db.flush()
    for tc in cases:
        if _v(tc.type) == "functional":
            ok = "Negative" not in tc.title
            db.add(TestResult(run_id=fr.id, test_case_id=tc.id, name=tc.title, created_at=fr_at,
                              status="passed" if ok else "failed", duration_ms=rnd.uniform(800, 3000),
                              message=None if ok else "Expected 400, got 201 for quantity=-1"))


def _make_defect(db, settings, project, f: Finding, run: Run, at, rnd) -> Defect:
    project.defect_seq += 1
    sev = _v(f.severity)
    d = Defect(project_id=project.id, key=f"{project.key}-{project.defect_seq}", kind="vulnerability",
               title=f.title, severity=sev,
               priority={"critical": "P1", "high": "P2", "medium": "P3"}.get(sev, "P4"),
               description=f"{f.description}\n\n**Location:** `{f.endpoint or f.file_path}`",
               steps_to_reproduce=_steps(f.category, f.endpoint),
               expected_result="Request is rejected / data is not exposed.",
               actual_result="The application processes the malicious input.",
               cwe_id=f.cwe_id, owasp_id=f.owasp_id, iso_control=f.iso_control,
               assignee=rnd.choice(TEAM[:3]) if sev in ("critical", "high") else None,
               reporter="agent:claude-code", environment="local-docker", found_in_run_id=run.id,
               created_at=at + timedelta(hours=4), updated_at=at + timedelta(hours=4),
               due_at=compute_due(settings, sev, at + timedelta(hours=4)), tags=[f.category])
    db.add(d)
    db.flush()
    db.add(DefectEvent(defect_id=d.id, actor="agent:claude-code", field="created", new_value=d.key,
                       at=d.created_at))
    return d


def _transition(db, d: Defect, status: str, at, actor: str) -> None:
    db.add(DefectEvent(defect_id=d.id, actor=actor, field="status", old_value=_v(d.status), new_value=status, at=at))
    d.status = DefectStatus(status)
    d.updated_at = at
    if status in ("fixed", "verified") and d.resolved_at is None:
        d.resolved_at = at
    if status == "closed":
        d.closed_at = at


def _v(x):
    return getattr(x, "value", x)


def _evidence(cat: str, endpoint: str | None) -> str | None:
    samples = {
        "sql-injection": "POST /rest/user/login\n{\"email\":\"' OR 1=1--\",\"password\":\"x\"}\n\n"
                         "HTTP/1.1 200 OK\n"
                         "{\"authentication\":{\"token\":\"eyJhbGciOi…\",\"umail\":\"admin@juice-sh.op\"}}",
        "xss": "GET /#/search?q=<iframe src=\"javascript:alert(`xss`)\">\n→ payload rendered unescaped in DOM",
        "idor": "GET /rest/basket/2  (authenticated as user id 1)\n\nHTTP/1.1 200 OK  → basket of user 2 returned",
        "exposed-secret": "lib/insecurity.ts:23  "
                          "const privateKey = '-----BEGIN RSA PRIVATE KEY-----\\r\\nMIIC****…' (masked)",
        "broken-auth": "Header: {\"alg\":\"none\",\"typ\":\"JWT\"}  → request accepted as admin",
    }
    return samples.get(cat) or (f"{endpoint} → see tool output" if endpoint else None)


def _remediation(cat: str) -> str:
    return {
        "sql-injection": "Use parameterised queries / ORM bindings; never concatenate user input into SQL.",
        "xss": "Remove bypassSecurityTrustHtml; rely on Angular's default contextual escaping.",
        "idor": "Check that the basket belongs to the authenticated user before returning it.",
        "exposed-secret": "Move the key to a secret manager, rotate it, and purge it from git history.",
        "vulnerable-dependency": "Upgrade to a patched version and add SCA to CI.",
        "broken-auth": "Pin accepted algorithms (RS256) when verifying JWTs.",
        "api-rate-limiting": "Add per-IP and per-account rate limiting with exponential back-off.",
        "security-misconfiguration": "Harden the server configuration; disable directory listing; add headers.",
        "sensitive-data-exposure": "Return generic error messages; log details server-side only.",
        "insecure-deserialization": "Never evaluate user input; parse with a strict schema.",
        "api-excessive-data-exposure": "Serialise an explicit allow-list of fields in API responses.",
    }.get(cat, "Review and fix according to the referenced CWE.")


def _steps(cat: str, endpoint: str | None) -> str:
    return (f"1. Start Juice Shop locally (docker compose up).\n"
            f"2. Send the request shown in the evidence to `{endpoint or 'the affected component'}`.\n"
            f"3. Observe the response.")
