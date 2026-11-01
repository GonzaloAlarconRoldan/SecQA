from __future__ import annotations

import json

import pytest

from secqa.hub.parsers.jtl import parse_jtl
from secqa.hub.parsers.junit import parse_junit
from secqa.hub.parsers.k6 import parse_k6_summary
from secqa.hub.parsers.sarif import parse_sarif

from .conftest import FIXTURES


def test_sarif_semgrep_maps_cwe_severity_and_location():
    items = parse_sarif(json.loads((FIXTURES / "semgrep.sarif").read_text()))
    assert len(items) == 2
    sqli, xss = items
    assert sqli["category"] == "sql-injection"
    assert sqli["severity"] == "critical"  # security-severity 9.1
    assert sqli["cvss_score"] == 9.1
    assert sqli["cwe_id"] == "CWE-89"
    assert (sqli["file_path"], sqli["line_start"], sqli["line_end"]) == ("routes/login.ts", 34, 36)
    assert sqli["fingerprint"] == "abc123"
    assert sqli["source"] == "sast"
    assert "sequelize" in sqli["evidence"]
    assert xss["category"] == "xss"
    assert xss["severity"] == "medium"  # level=warning, no security-severity


def test_sarif_tool_hint_sets_source_and_category():
    items = parse_sarif(json.loads((FIXTURES / "gitleaks.sarif").read_text()))
    assert items[0]["source"] == "secrets"
    assert items[0]["category"] == "exposed-secret"


def test_sarif_rejects_non_sarif():
    with pytest.raises(ValueError):
        parse_sarif({"hello": "world"})


def test_k6_summary_total_and_per_endpoint():
    parsed = parse_k6_summary(json.loads((FIXTURES / "k6-summary.json").read_text()))
    total, *endpoints = parsed["rows"]
    assert total["name"] == "__total__"
    assert total["requests"] == 1200
    assert total["p95_ms"] == 250.4
    assert total["error_rate"] == 0.005
    assert total["vus_max"] == 20
    assert parsed["duration_s"] == 60
    assert parsed["thresholds_passed"] is False  # POST /login thresholds failed
    names = {e["name"]: e for e in endpoints}
    assert set(names) == {"GET /api/items", "POST /login"}
    assert names["POST /login"]["p95_ms"] == 610.0
    assert names["POST /login"]["requests"] == 400


def test_k6_legacy_summary_export_format():
    legacy = {"metrics": {
        "http_req_duration": {"avg": 10, "p(95)": 20, "thresholds": {"p(95)<500": False}},
        "http_reqs": {"count": 10, "rate": 1.0},
        "http_req_failed": {"value": 0.1, "passes": 1, "fails": 9},
    }}
    parsed = parse_k6_summary(legacy)
    assert parsed["thresholds_passed"] is True  # legacy bool means "failed"
    assert parsed["rows"][0]["error_rate"] == 0.1


def test_jtl_aggregates_per_label():
    parsed = parse_jtl((FIXTURES / "results.jtl").read_text())
    total, items, login = parsed["rows"]
    assert total["requests"] == 4 and total["failures"] == 1
    assert total["error_rate"] == 0.25
    assert total["vus_max"] == 2
    assert items["name"] == "GET /api/items" and items["p95_ms"] == 200
    assert login["failures"] == 1


def test_jtl_rejects_other_csv():
    with pytest.raises(ValueError):
        parse_jtl("a,b\n1,2\n")


def test_junit_statuses_and_case_key():
    results = parse_junit((FIXTURES / "junit.xml").read_text())
    assert [r["status"] for r in results] == ["passed", "failed", "skipped"]
    assert results[0]["test_case_key"] == "SHOP-TC-1"
    assert results[1]["message"] == "expected 429, got 200"
    assert results[0]["duration_ms"] == pytest.approx(120)


def test_junit_blocks_entity_expansion():
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><testsuite><testcase name="&a;"/></testsuite>'
    with pytest.raises(Exception):  # defusedxml refuses entity declarations
        parse_junit(evil)
