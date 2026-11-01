"""JMeter JTL (CSV results file) → perf metric rows.

Run JMeter headless with CSV output, e.g.:
    jmeter -n -t plan.jmx -l results.jtl
"""
from __future__ import annotations

import contextlib
import csv
import io
import math
from collections import defaultdict
from typing import Any


def _pct(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    k = max(0, math.ceil(p / 100 * len(sorted_vals)) - 1)  # nearest-rank
    return sorted_vals[k]


def _stats(name: str, samples: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed = sorted(s["elapsed"] for s in samples)
    count = len(samples)
    failures = sum(1 for s in samples if not s["success"])
    start = min(s["ts"] for s in samples)
    end = max(s["ts"] + s["elapsed"] for s in samples)
    duration_s = max((end - start) / 1000, 0.001)
    return {
        "name": name,
        "requests": count,
        "failures": failures,
        "error_rate": round(failures / count, 6) if count else 0.0,
        "rps": round(count / duration_s, 3),
        "avg_ms": round(sum(elapsed) / count, 3) if count else None,
        "min_ms": elapsed[0] if elapsed else None,
        "med_ms": _pct(elapsed, 50),
        "p90_ms": _pct(elapsed, 90),
        "p95_ms": _pct(elapsed, 95),
        "p99_ms": _pct(elapsed, 99),
        "max_ms": elapsed[-1] if elapsed else None,
        "duration_s": round(duration_s, 3),
    }


def parse_jtl(text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"timeStamp", "elapsed", "label"} <= set(reader.fieldnames):
        raise ValueError("not a JMeter CSV JTL (needs timeStamp, elapsed, label columns)")

    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    everything: list[dict[str, Any]] = []
    max_threads = 0
    for row in reader:
        try:
            sample = {
                "ts": int(row["timeStamp"]),
                "elapsed": float(row["elapsed"]),
                "success": str(row.get("success", "true")).strip().lower() == "true",
            }
        except (TypeError, ValueError):
            continue  # skip malformed lines rather than failing the whole import
        by_label[row["label"]].append(sample)
        everything.append(sample)
        with contextlib.suppress(ValueError):
            max_threads = max(max_threads, int(row.get("allThreads") or 0))

    if not everything:
        raise ValueError("JTL file has no samples")

    total = _stats("__total__", everything)
    total["vus_max"] = max_threads or None
    total["thresholds"] = {}
    rows = [total] + [_stats(label, samples) for label, samples in sorted(by_label.items())]
    return {"rows": rows, "thresholds_passed": None, "duration_s": total["duration_s"], "vus_max": total["vus_max"]}
