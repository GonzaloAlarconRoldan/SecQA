"""k6 summary JSON → perf metric rows.

Accepts both formats k6 can produce:
  * `handleSummary(data)` output (what the SecQA templates write): metrics[m].values + thresholds{expr: {ok}}
  * legacy `--summary-export=file.json`: values flattened into metrics[m], thresholds{expr: <failed bool>}

Per-endpoint rows come from tagged sub-metrics such as `http_req_duration{name:GET /api/items}`,
which k6 only emits when a threshold references them (the SecQA templates add those automatically).
"""
from __future__ import annotations

import re
from typing import Any

_SUBMETRIC_RE = re.compile(r"^(?P<metric>[\w.]+)\{(?P<tags>.*)\}$")


def _values(metric: dict[str, Any]) -> dict[str, Any]:
    return metric.get("values", metric)


def _thresholds(metric: dict[str, Any]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for expr, val in (metric.get("thresholds") or {}).items():
        if isinstance(val, dict):
            out[expr] = bool(val.get("ok"))
        else:  # legacy export stores "lastFailed"
            out[expr] = not bool(val)
    return out


def _ms(value: Any) -> float | None:
    return round(float(value), 3) if value is not None else None


def _row(name: str, dur: dict[str, Any], reqs: dict[str, Any] | None, failed: dict[str, Any] | None,
         duration_s: float | None) -> dict[str, Any]:
    d = _values(dur)
    count = int(_values(reqs).get("count", 0)) if reqs else 0
    error_rate = 0.0
    failures = 0
    if failed:
        fv = _values(failed)
        # http_req_failed is a Rate: passes = failed requests, value = failure ratio
        error_rate = float(fv.get("rate", fv.get("value", 0.0)) or 0.0)
        failures = int(fv.get("passes", round(error_rate * count)))
    rps = None
    if reqs:
        rps = _values(reqs).get("rate")
        if rps is None and duration_s:
            rps = count / duration_s
    return {
        "name": name,
        "requests": count,
        "failures": failures,
        "error_rate": round(error_rate, 6),
        "rps": round(float(rps), 3) if rps is not None else None,
        "avg_ms": _ms(d.get("avg")),
        "min_ms": _ms(d.get("min")),
        "med_ms": _ms(d.get("med")),
        "p90_ms": _ms(d.get("p(90)")),
        "p95_ms": _ms(d.get("p(95)")),
        "p99_ms": _ms(d.get("p(99)")),
        "max_ms": _ms(d.get("max")),
    }


def parse_k6_summary(doc: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = doc.get("metrics") or {}
    if "http_req_duration" not in metrics:
        raise ValueError("not a k6 summary (no http_req_duration metric)")

    state = doc.get("state") or {}
    duration_ms = state.get("testRunDurationMs")
    duration_s = round(duration_ms / 1000, 3) if duration_ms else None
    vus_max = metrics.get("vus_max")
    vus = int(_values(vus_max).get("value") or _values(vus_max).get("max") or 0) if vus_max else None

    all_thresholds: dict[str, bool] = {}
    for mname, metric in metrics.items():
        for expr, ok in _thresholds(metric).items():
            all_thresholds[f"{mname}: {expr}"] = ok

    total = _row("__total__", metrics["http_req_duration"], metrics.get("http_reqs"),
                 metrics.get("http_req_failed"), duration_s)
    total.update(vus_max=vus, duration_s=duration_s, thresholds=all_thresholds)
    rows = [total]

    groups: dict[str, dict[str, Any]] = {}
    for mname, metric in metrics.items():
        m = _SUBMETRIC_RE.match(mname)
        if not m:
            continue
        tags = dict(t.split(":", 1) for t in m.group("tags").split(",") if ":" in t)
        # Only request-group sub-metrics are endpoints; skip k6's built-ins like {expected_response:true}.
        label = tags.get("name") or tags.get("url")
        if not label:
            continue
        groups.setdefault(label, {})[m.group("metric")] = metric
    for label, group in sorted(groups.items()):
        if "http_req_duration" not in group:
            continue
        row = _row(label, group["http_req_duration"], group.get("http_reqs"),
                   group.get("http_req_failed"), duration_s)
        row["thresholds"] = {
            f"{metric}: {expr}": ok for metric, met in group.items() for expr, ok in _thresholds(met).items()
        }
        rows.append(row)

    return {
        "rows": rows,
        "thresholds_passed": all(all_thresholds.values()) if all_thresholds else None,
        "duration_s": duration_s,
        "vus_max": vus,
    }
