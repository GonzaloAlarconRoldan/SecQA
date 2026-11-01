"""Category → OWASP / CWE / ISO/IEC 27001 mapping (shared by CLI and Hub)."""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache
def load_mapping() -> dict[str, dict[str, str]]:
    raw = json.loads(resources.files("secqa.data").joinpath("iso_owasp_map.json").read_text("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@lru_cache
def cwe_to_category() -> dict[str, str]:
    out: dict[str, str] = {}
    for category, entry in load_mapping().items():
        out.setdefault(entry["cwe_id"].upper(), category)
    return out


def enrich(data: dict[str, Any]) -> dict[str, Any]:
    """Fill owasp_id / cwe_id / iso_control from the category when they are missing."""
    entry = load_mapping().get(data.get("category") or "")
    if entry:
        for field in ("owasp_id", "cwe_id", "iso_control"):
            if not data.get(field) and entry.get(field) not in (None, "N/A"):
                data[field] = entry[field]
    return data
