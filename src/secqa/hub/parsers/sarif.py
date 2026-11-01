"""SARIF 2.1.0 → finding dicts.

Covers Semgrep, Gitleaks, Trivy, osv-scanner, Bandit, CodeQL, Nuclei (via its
SARIF export) and anything else that speaks SARIF.
"""
from __future__ import annotations

import re
from typing import Any

from ...mapping import cwe_to_category

_CWE_RE = re.compile(r"CWE-(\d+)", re.IGNORECASE)

# Tool name (lowercase, substring) → (source, default category)
_TOOL_HINTS: list[tuple[str, str, str]] = [
    ("gitleaks", "secrets", "exposed-secret"),
    ("trufflehog", "secrets", "exposed-secret"),
    ("osv", "sca", "vulnerable-dependency"),
    ("trivy", "sca", "vulnerable-dependency"),
    ("grype", "sca", "vulnerable-dependency"),
    ("dependency-check", "sca", "vulnerable-dependency"),
    ("nuclei", "dast", "security-misconfiguration"),
    ("zap", "dast", "security-misconfiguration"),
    ("checkov", "sca", "security-misconfiguration"),
    ("hadolint", "sca", "security-misconfiguration"),
]

_LEVEL_SEVERITY = {"error": "high", "warning": "medium", "note": "low", "none": "info"}


def _severity(result: dict[str, Any], rule: dict[str, Any]) -> tuple[str, float | None]:
    props = {**rule.get("properties", {}), **result.get("properties", {})}
    raw = props.get("security-severity")
    if raw is not None:
        try:
            score = float(raw)
        except (TypeError, ValueError):
            score = None
        if score is not None:
            if score >= 9.0:
                return "critical", score
            if score >= 7.0:
                return "high", score
            if score >= 4.0:
                return "medium", score
            if score > 0:
                return "low", score
            return "info", score
    level = result.get("level") or rule.get("defaultConfiguration", {}).get("level") or "warning"
    return _LEVEL_SEVERITY.get(level, "medium"), None


def _cwe(rule: dict[str, Any], result: dict[str, Any]) -> str | None:
    haystack: list[str] = []
    for src in (rule.get("properties", {}), result.get("properties", {})):
        for key in ("tags", "cwe"):
            val = src.get(key)
            if isinstance(val, list):
                haystack.extend(str(v) for v in val)
            elif val:
                haystack.append(str(val))
    for text in haystack:
        m = _CWE_RE.search(text)
        if m:
            return f"CWE-{m.group(1)}"
    return None


def _text(obj: dict[str, Any] | None) -> str | None:
    if not obj:
        return None
    return obj.get("markdown") or obj.get("text")


def parse_sarif(doc: dict[str, Any], default_source: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(doc, dict) or "runs" not in doc:
        raise ValueError("not a SARIF document (missing 'runs')")

    findings: list[dict[str, Any]] = []
    for run in doc.get("runs", []):
        driver = run.get("tool", {}).get("driver", {})
        tool = driver.get("name") or "sarif"
        rules = {r.get("id"): r for r in driver.get("rules", []) if r.get("id")}
        source, tool_category = default_source or "sast", None
        for needle, hint_source, hint_cat in _TOOL_HINTS:
            if needle in tool.lower():
                source = default_source or hint_source
                tool_category = hint_cat
                break

        for result in run.get("results", []):
            rule_id = result.get("ruleId") or result.get("rule", {}).get("id")
            rule = rules.get(rule_id, {})
            severity, score = _severity(result, rule)
            cwe = _cwe(rule, result)
            category = tool_category or (cwe and cwe_to_category().get(cwe)) or "security-misconfiguration"
            if cwe and cwe_to_category().get(cwe) and source == "sast":
                category = cwe_to_category()[cwe]

            loc = (result.get("locations") or [{}])[0].get("physicalLocation", {})
            region = loc.get("region", {})
            uri = loc.get("artifactLocation", {}).get("uri")
            message = _text(result.get("message")) or rule_id or "finding"
            title = _text(rule.get("shortDescription")) or message.splitlines()[0][:200]
            fingerprints = result.get("partialFingerprints") or result.get("fingerprints") or {}

            endpoint = None
            if uri and uri.startswith(("http://", "https://")):
                endpoint, uri = uri, None

            findings.append({
                "source": source,
                "tool": tool,
                "rule_id": rule_id,
                "category": category,
                "title": title[:500],
                "description": message,
                "severity": severity,
                "cvss_score": score,
                "cwe_id": cwe,
                "file_path": uri,
                "line_start": region.get("startLine"),
                "line_end": region.get("endLine") or region.get("startLine"),
                "endpoint": endpoint,
                "evidence": _text(region.get("snippet")),
                "remediation": _text(rule.get("help")),
                "fingerprint": next(iter(fingerprints.values()), None),
            })
    return findings
