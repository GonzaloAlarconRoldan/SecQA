from __future__ import annotations

from datetime import datetime, timedelta, timezone

from secqa.hub.app import create_app
from secqa.hub.config import Settings

from .conftest import start_run, upload

SQLI = {"title": "SQLi in login", "severity": "critical", "category": "sql-injection", "source": "sast",
        "file_path": "routes/login.ts", "line_start": 34}


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["auth_required"] is False
    assert "critical" in meta["enums"]["severity"]
    assert meta["sla_days"]["critical"] == 7


def test_project_key_validation_and_conflict(client, project):
    assert client.post("/api/projects", json={"key": "shop", "name": "x"}).status_code == 422
    assert client.post("/api/projects", json={"key": "SHOP", "name": "x"}).status_code == 409
    listed = client.get("/api/projects").json()
    assert listed[0]["key"] == "SHOP" and listed[0]["run_count"] == 0


def test_finding_enrichment_and_dedup_within_run(client, project):
    run = start_run(client)
    r = client.post(f"/api/runs/{run['id']}/findings", json=[SQLI, SQLI]).json()
    assert r["created"] == 1 and r["skipped"] == 1
    f = client.get("/api/findings", params={"project": "SHOP"}).json()["items"][0]
    assert (f["owasp_id"], f["cwe_id"], f["iso_control"]) == ("A03:2021", "CWE-89", "A.8.28")
    assert f["triage_status"] == "new"
    assert f["first_seen_run_id"] == run["id"]


def test_false_positive_is_remembered_across_runs(client, project):
    r1 = start_run(client)
    client.post(f"/api/runs/{r1['id']}/findings", json=[SQLI])
    fid = client.get("/api/findings", params={"run_id": r1["id"]}).json()["items"][0]["id"]
    client.patch(f"/api/findings/{fid}", json={"triage_status": "false_positive", "review_comment": "test code"})

    r2 = start_run(client)
    res = client.post(f"/api/runs/{r2['id']}/findings", json=[SQLI]).json()
    assert res["suppressed"] == 1
    f2 = client.get("/api/findings", params={"run_id": r2["id"]}).json()["items"][0]
    assert f2["triage_status"] == "false_positive"
    assert f2["first_seen_run_id"] == r1["id"]
    new_only = client.get("/api/findings", params={"run_id": r2["id"], "new_only": True}).json()
    assert new_only["total"] == 0


def test_promote_findings_to_defect_with_sla(client, project):
    run = start_run(client)
    client.post(f"/api/runs/{run['id']}/findings",
                json=[SQLI, {**SQLI, "title": "XSS", "severity": "medium", "category": "xss", "line_start": 9}])
    ids = [f["id"] for f in client.get("/api/findings", params={"project": "SHOP"}).json()["items"]]
    d = client.post("/api/projects/SHOP/defects/from-findings", json={"finding_ids": ids}).json()
    assert d["key"] == "SHOP-1"
    assert d["severity"] == "critical" and d["priority"] == "P1" and d["kind"] == "vulnerability"
    assert d["finding_count"] == 2
    created = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
    due = datetime.fromisoformat(d["due_at"].replace("Z", "+00:00"))
    assert due - created == timedelta(days=7)
    linked = client.get("/api/findings", params={"project": "SHOP"}).json()["items"]
    assert all(f["triage_status"] == "confirmed" and f["defect_key"] == "SHOP-1" for f in linked)


def test_defect_lifecycle_history_and_comments(client, project):
    d = client.post("/api/projects/SHOP/defects", json={"title": "Broken", "severity": "high"}).json()
    did = d["id"]
    client.patch(f"/api/defects/{did}", json={"status": "in_progress", "assignee": "ana"})
    fixed = client.patch(f"/api/defects/{did}", json={"status": "fixed"}).json()
    assert fixed["resolved_at"] is not None
    client.post(f"/api/defects/{did}/comments", json={"body": "Patched in #42"})
    detail = client.get(f"/api/defects/{did}").json()
    fields = [(e["field"], e["new_value"]) for e in detail["events"]]
    assert ("status", "in_progress") in fields and ("status", "fixed") in fields
    assert ("assignee", "ana") in fields
    assert detail["comments"][0]["author"] == "human:tester"
    # duplicate requires a target
    assert client.patch(f"/api/defects/{did}", json={"status": "duplicate"}).status_code == 400


def test_closed_defect_reopens_when_finding_reappears(client, project):
    r1 = start_run(client)
    client.post(f"/api/runs/{r1['id']}/findings", json=[SQLI])
    fid = client.get("/api/findings", params={"run_id": r1["id"]}).json()["items"][0]["id"]
    d = client.post("/api/projects/SHOP/defects/from-findings", json={"finding_ids": [fid]}).json()
    client.patch(f"/api/defects/{d['id']}", json={"status": "closed"})

    r2 = start_run(client)
    res = client.post(f"/api/runs/{r2['id']}/findings", json=[SQLI]).json()
    assert res["linked_to_defects"] == 1
    reopened = client.get(f"/api/defects/{d['id']}").json()
    assert reopened["status"] == "new"
    assert reopened["closed_at"] is None
    assert any("regression" in (e["new_value"] or "") for e in reopened["events"])


def test_sarif_ingest_and_sla_breach_filter(client, project):
    run = start_run(client)
    res = upload(client, run["id"], "sarif", "semgrep.sarif")
    assert res["created"] == 2
    fid = client.get("/api/findings", params={"run_id": run["id"], "severity": "critical"}).json()["items"][0]["id"]
    d = client.post("/api/projects/SHOP/defects/from-findings", json={"finding_ids": [fid]}).json()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    client.patch(f"/api/defects/{d['id']}", json={"due_at": past})
    breached = client.get("/api/defects", params={"project": "SHOP", "sla_breached": True}).json()
    assert breached["total"] == 1 and breached["items"][0]["sla_breached"] is True


def test_perf_baseline_regression_opens_defect(client, project):
    base = start_run(client, kind="performance")
    upload(client, base["id"], "k6", "k6-summary.json", scenario="load")
    client.patch(f"/api/runs/{base['id']}", json={"is_baseline": True})
    assert client.post(f"/api/runs/{base['id']}/finish", json={}).json()["status"] == "failed"  # thresholds

    # same data scaled 2x slower → regression
    import json

    from .conftest import FIXTURES
    doc = json.loads((FIXTURES / "k6-summary.json").read_text())
    for name, m in doc["metrics"].items():
        if name.startswith("http_req_duration"):
            m["values"] = {k: v * 2 for k, v in m["values"].items()}
    cur = start_run(client, kind="performance")
    r = client.post(f"/api/runs/{cur['id']}/ingest/k6", params={"scenario": "load"},
                    files={"file": ("k6.json", json.dumps(doc).encode())}).json()
    assert r["detail"]["regressions"] > 0
    assert r["detail"]["defect"].startswith("SHOP-")
    cmp = client.get(f"/api/runs/{cur['id']}/compare").json()
    assert cmp["baseline_run_id"] == base["id"]
    assert any(c["metric"] == "p95_ms" and c["regressed"] for c in cmp["regressions"])
    perf_defects = client.get("/api/defects", params={"project": "SHOP", "kind": "performance"}).json()
    assert perf_defects["total"] == 1
    trend = client.get("/api/perf/trend", params={"project": "SHOP"}).json()
    assert [t["run_id"] for t in trend] == [base["id"], cur["id"]]


def test_baseline_only_for_performance_runs(client, project):
    run = start_run(client)
    assert client.patch(f"/api/runs/{run['id']}", json={"is_baseline": True}).status_code == 400


def test_junit_links_results_to_test_cases(client, project):
    tc = client.post("/api/projects/SHOP/testcases", json={
        "title": "JWT alg none rejected", "type": "security", "owasp_id": "A07:2021",
        "steps": [{"action": "send token with alg none", "expected": "401"}]}).json()
    assert tc["key"] == "SHOP-TC-1"
    run = start_run(client, kind="functional")
    upload(client, run["id"], "junit", "junit.xml")
    finished = client.post(f"/api/runs/{run['id']}/finish", json={}).json()
    assert finished["status"] == "failed"
    assert finished["results_by_status"] == {"passed": 1, "failed": 1, "skipped": 1}
    tc_after = client.get(f"/api/testcases/{tc['id']}").json()
    assert tc_after["last_status"] == "passed" and tc_after["last_run_id"] == run["id"]
    assert len(client.get(f"/api/testcases/{tc['id']}/history").json()) == 1


def test_overview_compliance_and_reports(client, project):
    run = start_run(client)
    client.post(f"/api/runs/{run['id']}/findings", json=[SQLI])
    fid = client.get("/api/findings").json()["items"][0]["id"]
    client.post("/api/projects/SHOP/defects/from-findings", json={"finding_ids": [fid]})
    ov = client.get("/api/stats/overview", params={"project": "SHOP"}).json()
    assert ov["kpis"]["open_defects"] == 1 and ov["kpis"]["critical_open"] == 1
    comp = client.get("/api/compliance", params={"project": "SHOP"}).json()
    a03 = next(r for r in comp["owasp-top10-2021"] if r["id"] == "A03:2021")
    assert a03["state"] == "fail" and a03["open_defects"] == 1

    html = client.get("/api/reports/html", params={"project": "SHOP", "lang": "es"})
    assert html.status_code == 200 and "SHOP-1" in html.text and "Resumen ejecutivo" in html.text
    sarif = client.get("/api/export/findings.sarif", params={"project": "SHOP"}).json()
    assert sarif["runs"][0]["results"][0]["ruleId"] == "sql-injection"
    csv_text = client.get("/api/export/defects.csv", params={"project": "SHOP"}).text
    assert csv_text.splitlines()[1].startswith("SHOP-1,vulnerability")


def test_report_escapes_html_from_tool_output(client, project):
    run = start_run(client)
    client.post(f"/api/runs/{run['id']}/findings", json=[{**SQLI, "title": "<script>alert(1)</script>"}])
    fid = client.get("/api/findings").json()["items"][0]["id"]
    client.patch(f"/api/findings/{fid}", json={"triage_status": "confirmed"})
    html = client.get("/api/reports/html", params={"project": "SHOP"}).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_csv_export_neutralises_formulas(client, project):
    client.post("/api/projects/SHOP/defects", json={"title": "=HYPERLINK(\"http://x\")", "severity": "low"})
    line = client.get("/api/export/defects.csv", params={"project": "SHOP"}).text.splitlines()[1]
    assert "'=HYPERLINK" in line


def test_attachments_are_stored_and_served_as_download(client, project):
    d = client.post("/api/projects/SHOP/defects", json={"title": "x", "severity": "low"}).json()
    up = client.post(f"/api/defects/{d['id']}/attachments",
                     files={"file": ("../../evil.html", b"<script>x</script>", "text/html")})
    assert up.status_code == 201
    att = up.json()
    assert att["filename"] == "evil.html"
    got = client.get(att["url"])
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/octet-stream"
    assert got.headers["content-disposition"].startswith("attachment")


def test_token_auth(tmp_path):
    from fastapi.testclient import TestClient

    c = TestClient(create_app(Settings(data_dir=tmp_path, api_token="s3cret")))
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/meta").json()["auth_required"] is True
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/projects", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/api/projects", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_bad_upload_is_422(client, project):
    run = start_run(client)
    r = client.post(f"/api/runs/{run['id']}/ingest/k6", files={"file": ("x.json", b"not json")})
    assert r.status_code == 422


def test_audit_log(client, project):
    run = start_run(client)
    client.post("/api/projects/SHOP/audit", json={"action": "nuclei -u http://127.0.0.1:3000",
                                                   "target": "127.0.0.1:3000", "run_id": run["id"]})
    log = client.get("/api/projects/SHOP/audit", params={"run_id": run["id"]}).json()
    assert any(e["action"].startswith("nuclei") and e["actor"] == "human:tester" for e in log)


def test_filter_findings_and_defects_by_owasp_and_iso(client, project):
    run = start_run(client)
    client.post(f"/api/runs/{run['id']}/findings",
                json=[SQLI, {**SQLI, "title": "IDOR", "category": "idor", "severity": "high", "line_start": 2}])
    by_owasp = client.get("/api/findings", params={"project": "SHOP", "owasp_id": "A01:2021"}).json()
    assert [f["category"] for f in by_owasp["items"]] == ["idor"]
    by_iso = client.get("/api/findings", params={"project": "SHOP", "iso_control": "A.8.28"}).json()
    assert [f["category"] for f in by_iso["items"]] == ["sql-injection"]
    fid = by_iso["items"][0]["id"]
    client.post("/api/projects/SHOP/defects/from-findings", json={"finding_ids": [fid]})
    assert client.get("/api/defects", params={"owasp_id": "A03:2021"}).json()["total"] == 1
    assert client.get("/api/defects", params={"iso_control": "A.8.3"}).json()["total"] == 0
