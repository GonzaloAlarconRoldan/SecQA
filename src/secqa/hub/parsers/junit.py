"""JUnit XML → test result dicts. Links to test cases when the test name contains a
test-case key such as `[SHOP-TC-12]`."""
from __future__ import annotations

import re
from typing import Any

from defusedxml import ElementTree

_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,15}-TC-\d+)\b")


def parse_junit(xml_text: str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(xml_text)
    results: list[dict[str, Any]] = []
    for case in root.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or "unnamed"
        full = f"{classname}.{name}" if classname else name
        status, message = "passed", None
        for tag, mapped in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
            el = case.find(tag)
            if el is not None:
                status = mapped
                message = (el.get("message") or el.text or "").strip() or None
                break
        try:
            duration_ms = float(case.get("time") or 0) * 1000
        except ValueError:
            duration_ms = None
        key = _KEY_RE.search(full)
        results.append({
            "name": full[:500],
            "status": status,
            "duration_ms": duration_ms,
            "message": message,
            "test_case_key": key.group(1) if key else None,
        })
    return results
