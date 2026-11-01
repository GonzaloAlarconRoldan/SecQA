from __future__ import annotations

import json

import httpx
import pytest

from secqa import cli
from secqa.detect import detect
from secqa.intel import cvss3_score, nvd_relevance, recommended_fix, run_intel

from .conftest import start_run


@pytest.fixture
def project_tree(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"express": "^4.16.0", "jsonwebtoken": "0.4.0", "sequelize": "^6.0.0"},
        "devDependencies": {"mocha": "^10.0.0"}}))
    (tmp_path / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {
        "": {"name": "shop"},
        "node_modules/express": {"version": "4.16.0"},
        "node_modules/jsonwebtoken": {"version": "0.4.0"},
        "node_modules/sequelize": {"version": "6.1.0"},
        "node_modules/mocha": {"version": "10.0.0", "dev": True}}}))
    (tmp_path / "requirements.txt").write_text("django==3.2.0\nrequests>=2.0\n# comment\n")
    (tmp_path / "go.mod").write_text("module x\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n"
                                     "\tgolang.org/x/net v0.1.0 // indirect\n)\n")
    (tmp_path / "Dockerfile").write_text("FROM node:22-alpine AS build\nFROM nginx:1.19\nEXPOSE 80 443/tcp\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  db:\n    image: postgres:16\n    ports: ['5432:5432']\n")
    (tmp_path / "openapi.yaml").write_text("openapi: 3.0.0\ninfo: {title: x, version: '1'}\npaths: {}\n")
    (tmp_path / ".env").write_text("SECRET=1\n")
    (tmp_path / ".env.example").write_text("SECRET=\n")
    (tmp_path / "yarn.lock").write_text("# yarn\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("export {}\n")
    nm = tmp_path / "node_modules" / "ignored"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text(json.dumps({"dependencies": {"evil": "1.0.0"}}))
    return tmp_path


def test_detect_stack_and_exact_versions(project_tree):
    r = detect(project_tree).to_dict()
    assert {"Express", "Django", "Gin"} <= set(r["frameworks"])
    assert "Sequelize" in r["databases"] and "JWT (jsonwebtoken)" in r["auth"]
    assert r["languages"]["TypeScript"] == 1
    assert {"npm", "pip", "go", "yarn"} <= set(r["package_managers"])
    comps = {(c["ecosystem"], c["name"]): c for c in r["components"]}
    assert comps[("npm", "express")]["version"] == "4.16.0"  # lockfile beats the ^range
    assert comps[("npm", "express")]["spec"] == "^4.16.0" and comps[("npm", "express")]["direct"]
    assert comps[("npm", "mocha")]["dev"] is True
    assert comps[("PyPI", "django")]["version"] == "3.2.0"
    assert comps[("PyPI", "requests")]["version"] is None
    assert comps[("Go", "golang.org/x/net")]["direct"] is False
    assert ("npm", "evil") not in comps  # node_modules is never walked
    assert r["docker_images"] == ["nginx:1.19", "node:22-alpine", "postgres:16"]
    assert r["exposed_ports"] == [80, 443, 5432]
    assert r["has_api"] and r["api_spec_files"] == ["openapi.yaml"]
    assert r["env_files"] == [".env"]
    assert r["unparsed"] == ["yarn.lock"]


def test_cvss_and_recommended_fix():
    assert cvss3_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H") == 10.0
    assert cvss3_score("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:N") == 5.4
    assert cvss3_score("CVSS:4.0/AV:N") is None
    assert recommended_fix("2.14.1", ["2.12.2", "2.3.1", "2.15.0", "2.16.0"]) == "2.15.0"
    assert recommended_fix("3.2.0", ["4.2.26", "5.1.14"]) == "4.2.26"
    assert recommended_fix("9.0.0", ["1.0.0"]) is None


def test_nvd_relevance_filters_keyword_noise():
    def cve(desc, cpe=None):
        conf = [{"nodes": [{"cpeMatch": [{"vulnerable": True, "criteria": cpe}]}]}] if cpe else []
        return {"descriptions": [{"lang": "en", "value": desc}], "configurations": conf}

    assert nvd_relevance(cve("x", "cpe:2.3:a:djangoproject:django:*:*:*:*:*:*:*:*"), "Django") == "cpe"
    assert nvd_relevance(cve("y", "cpe:2.3:a:expressjs:express:*:*:*:*:*:node.js:*:*"), "Express") == "cpe"
    assert nvd_relevance(cve("An issue was discovered in Django 5.2 before 5.2.17."), "Django") == "text"
    assert nvd_relevance(cve("Plane is a tool built with Django. Prior to 1.4.0 …"), "Django") is None
    assert nvd_relevance(cve("Nginx UI is a web user interface for the Nginx web server."), "nginx") is None


OSV_VULN = {
    "id": "GHSA-jfh8-c2jp-5v3q", "aliases": ["CVE-2021-44228"], "summary": "Remote code injection in Log4j",
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"}],
    "database_specific": {"severity": "CRITICAL", "cwe_ids": ["CWE-502"]},
    "affected": [{"package": {"ecosystem": "Maven", "name": "org.apache.logging.log4j:log4j-core"},
                  "ranges": [{"events": [{"introduced": "2.0"}, {"fixed": "2.15.0"}]},
                             {"events": [{"introduced": "2.13"}, {"fixed": "2.3.1"}]}]}],
    "references": [{"type": "ADVISORY", "url": "https://nvd.nist.gov/vuln/detail/CVE-2021-44228"}],
}
DEV_VULN = {"id": "GHSA-dev1-0000-0000", "aliases": ["CVE-2099-0001"], "summary": "ReDoS in mocha",
            "database_specific": {"severity": "HIGH"},
            "affected": [{"package": {"ecosystem": "npm", "name": "mocha"},
                          "ranges": [{"events": [{"fixed": "10.1.0"}]}]}]}


def _mock_transport(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host + request.url.path)
        url = str(request.url)
        if "querybatch" in url:
            qs = json.loads(request.content)["queries"]
            ids = {"org.apache.logging.log4j:log4j-core": "GHSA-jfh8-c2jp-5v3q", "mocha": "GHSA-dev1-0000-0000"}
            return httpx.Response(200, json={"results": [
                {"vulns": [{"id": ids[q["package"]["name"]]}]} if q["package"]["name"] in ids else {} for q in qs]})
        if "/v1/vulns/GHSA-jfh8" in url:
            return httpx.Response(200, json=OSV_VULN)
        if "/v1/vulns/GHSA-dev1" in url:
            return httpx.Response(200, json=DEV_VULN)
        if "known_exploited" in url:
            return httpx.Response(200, json={"catalogVersion": "2026.10.30", "vulnerabilities": [
                {"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10", "dueDate": "2021-12-24",
                 "knownRansomwareCampaignUse": "Known", "requiredAction": "Apply updates"}]})
        if "epss" in url:
            return httpx.Response(200, json={"data": [
                {"cve": "CVE-2021-44228", "epss": "0.99999", "percentile": "1.0"},
                {"cve": "CVE-2099-0001", "epss": "0.6", "percentile": "0.98"}]})
        if "nvd.nist.gov" in url:
            return httpx.Response(200, json={"vulnerabilities": [
                {"cve": {"id": "CVE-2026-1", "published": "2026-10-20T00:00:00",
                         "descriptions": [{"lang": "en", "value": "Nginx 1.19 before 1.19.9 allows …"}],
                         "metrics": {"cvssMetricV31": [{"cvssData": {"baseSeverity": "HIGH", "baseScore": 7.5}}]}}},
                {"cve": {"id": "CVE-2026-2", "descriptions": [{"lang": "en", "value": "Nginx UI is a panel …"}]}}]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


STACK = {"frameworks": [], "databases": [], "docker_images": ["nginx:1.19"], "components": [
    {"ecosystem": "Maven", "name": "org.apache.logging.log4j:log4j-core", "version": "2.14.1", "dev": False,
     "direct": True, "source": "pom.xml"},
    {"ecosystem": "npm", "name": "mocha", "version": "10.0.0", "dev": True, "direct": True,
     "source": "package-lock.json"},
    {"ecosystem": "npm", "name": "express", "version": None, "dev": False, "direct": True, "source": "package.json"},
]}


def test_run_intel_prioritises_kev_and_epss(monkeypatch, tmp_path):
    monkeypatch.setenv("SECQA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr("secqa.intel.time.sleep", lambda s: None)
    calls: list[str] = []
    report = run_intel(STACK, days=30, client=httpx.Client(transport=_mock_transport(calls)))
    assert all(s["ok"] for s in report["sources"].values()), report["sources"]
    assert report["sources"]["osv"]["unpinned"] == 1
    log4j, mocha = report["affected"]
    assert log4j["severity"] == "critical" and log4j["kev"]["cve"] == "CVE-2021-44228"
    assert log4j["recommended_fix"] == "2.15.0" and log4j["cvss_score"] == 10.0
    # high advisory, EPSS 60 % keeps it high, but it is a dev dependency → lowered one level
    assert mocha["severity"] == "medium" and "dev dependency" in mocha["priority_reason"]
    assert report["stats"]["kev"] == 1 and report["stats"]["epss_high"] == 2  # log4j + mocha
    assert [w["id"] for w in report["watchlist"]] == ["CVE-2026-1"]  # "Nginx UI" filtered out
    # second run is served from cache for KEV and OSV advisories
    calls.clear()
    run_intel(STACK, days=30, nvd=False, client=httpx.Client(transport=_mock_transport(calls)))
    assert not any("known_exploited" in c or "/v1/vulns/" in c for c in calls)


def test_run_intel_survives_source_outage(monkeypatch, tmp_path):
    monkeypatch.setenv("SECQA_CACHE_DIR", str(tmp_path / "cache"))
    down = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    report = run_intel(STACK, nvd=False, client=down)
    assert report["sources"]["osv"]["ok"] is False and report["sources"]["kev"]["ok"] is False
    assert report["affected"] == []


def test_hub_ingests_intel_report(client, project, monkeypatch, tmp_path):
    monkeypatch.setenv("SECQA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr("secqa.intel.time.sleep", lambda s: None)
    report = run_intel(STACK, client=httpx.Client(transport=_mock_transport([])))
    run = start_run(client)
    res = client.post(f"/api/runs/{run['id']}/intel", json=report).json()
    assert res["created"] == 2 and res["detail"]["kev"] == 1
    f = client.get("/api/findings", params={"run_id": run["id"], "severity": "critical"}).json()["items"][0]
    assert f["title"].startswith("org.apache.logging.log4j:log4j-core@2.14.1: CVE-2021-44228")
    assert "CISA KEV" in f["description"] and "EPSS" in f["description"]
    assert f["remediation"] == "Upgrade org.apache.logging.log4j:log4j-core to 2.15.0 or later."
    assert (f["category"], f["owasp_id"], f["cwe_id"]) == ("vulnerable-dependency", "A06:2021", "CWE-502")
    summary = client.get(f"/api/runs/{run['id']}").json()["summary"]["intel"]
    assert summary["stats"]["kev"] == 1 and summary["watchlist"][0]["id"] == "CVE-2026-1"
    assert summary["watchlist"][0]["match"] == "text"
    # re-ingesting the same report in the same run does not duplicate
    assert client.post(f"/api/runs/{run['id']}/intel", json=report).json()["created"] == 0


def test_cli_detect_writes_stack(project_tree, monkeypatch, capsys):
    monkeypatch.chdir(project_tree)
    assert cli.main(["detect"]) == 0
    data = json.loads((project_tree / "secqa-out" / "stack.json").read_text())
    assert data["pinned_count"] >= 5
    assert "Express" in capsys.readouterr().out
