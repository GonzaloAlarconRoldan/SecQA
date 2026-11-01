"""Pre-run vulnerability intelligence from official sources (`secqa intel`).

Checks the component inventory from `secqa detect` against:

* OSV.dev  — aggregated advisories (GitHub Advisory DB, PyPA, Go, RustSec, …) by exact package version
* CISA KEV — vulnerabilities known to be exploited in the wild (bumps priority to critical)
* FIRST EPSS — probability of exploitation in the next 30 days
* NVD      — CVEs published in the last N days for the detected technologies (watchlist)

Every source is optional: a failure is recorded in the report and the rest still run.
Responses are cached under ~/.cache/secqa (KEV 12 h, OSV advisories 24 h).
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/{id}"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
USER_AGENT = "secqa-intel (+https://github.com/GonzaloAlarconRoldan/SecQA)"
SEV_ORDER = ["critical", "high", "medium", "low", "info"]


def cache_dir() -> Path:
    d = Path(os.environ.get("SECQA_CACHE_DIR") or Path.home() / ".cache" / "secqa")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cached_json(name: str, ttl_s: int, fetch) -> Any:
    path = cache_dir() / name
    if path.is_file() and time.time() - path.stat().st_mtime < ttl_s:
        try:
            return json.loads(path.read_text("utf-8"))
        except ValueError:
            pass
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), "utf-8")
    return data


# ---- CVSS v3.x base score ---------------------------------------------------

_W = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}, "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62}, "C": {"H": 0.56, "L": 0.22, "N": 0.0},
}


def _roundup(x: float) -> float:
    i = round(x * 100000)
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def cvss3_score(vector: str) -> float | None:
    """CVSS v3.0/v3.1 base score from a vector string (None if it isn't one)."""
    if not vector or not vector.startswith("CVSS:3"):
        return None
    m = dict(part.split(":", 1) for part in vector.split("/")[1:] if ":" in part)
    try:
        scope_changed = m["S"] == "C"
        pr = {"N": 0.85, "L": 0.68 if scope_changed else 0.62, "H": 0.5 if scope_changed else 0.27}[m["PR"]]
        iss = 1 - (1 - _W["C"][m["C"]]) * (1 - _W["C"][m["I"]]) * (1 - _W["C"][m["A"]])
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if scope_changed else 6.42 * iss
        exploitability = 8.22 * _W["AV"][m["AV"]] * _W["AC"][m["AC"]] * pr * _W["UI"][m["UI"]]
    except KeyError:
        return None
    if impact <= 0:
        return 0.0
    raw = 1.08 * (impact + exploitability) if scope_changed else impact + exploitability
    return _roundup(min(raw, 10))


def severity_from_score(score: float | None) -> str | None:
    if score is None:
        return None
    return "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else \
        "low" if score > 0 else "info"


# ---- OSV ---------------------------------------------------------------------

def _osv_details(client: httpx.Client, vid: str) -> dict:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", vid)
    return _cached_json(f"osv/{safe}.json", 24 * 3600,
                        lambda: client.get(OSV_VULN.format(id=vid), timeout=30).raise_for_status().json())


def _fixed_versions(vuln: dict, ecosystem: str, name: str) -> list[str]:
    out: list[str] = []
    for aff in vuln.get("affected") or []:
        pkg = aff.get("package") or {}
        if pkg.get("ecosystem") != ecosystem or pkg.get("name", "").lower() != name.lower():
            continue
        for rng in aff.get("ranges") or []:
            out += [e["fixed"] for e in rng.get("events") or [] if "fixed" in e]
    return sorted(set(out))


def _osv_severity(vuln: dict) -> tuple[str, float | None, str | None]:
    vector = next((s["score"] for s in vuln.get("severity") or [] if str(s.get("score", "")).startswith("CVSS:3")),
                  None)
    score = cvss3_score(vector) if vector else None
    label = str((vuln.get("database_specific") or {}).get("severity") or "").lower()
    label = {"moderate": "medium"}.get(label, label)
    if label not in SEV_ORDER:
        label = severity_from_score(score) or "medium"
    return label, score, vector


def query_osv(client: httpx.Client, components: list[dict]) -> tuple[list[dict], dict]:
    pinned = [c for c in components if c.get("version")]
    status: dict[str, Any] = {"ok": True, "queried": len(pinned), "unpinned": len(components) - len(pinned)}
    hits: list[tuple[dict, str]] = []
    for i in range(0, len(pinned), 1000):
        chunk = pinned[i:i + 1000]
        body = {"queries": [{"package": {"name": c["name"], "ecosystem": c["ecosystem"]}, "version": c["version"]}
                            for c in chunk]}
        res = client.post(OSV_BATCH, json=body, timeout=60).raise_for_status().json()
        for comp, result in zip(chunk, res.get("results") or [], strict=False):
            hits += [(comp, v["id"]) for v in result.get("vulns") or []]
    ids = sorted({vid for _, vid in hits})
    with ThreadPoolExecutor(max_workers=8) as pool:
        details = dict(zip(ids, pool.map(lambda v: _osv_details(client, v), ids), strict=True))
    affected = []
    for comp, vid in hits:
        v = details[vid]
        sev, score, vector = _osv_severity(v)
        cves = sorted({a for a in [vid, *(v.get("aliases") or [])] if a.startswith("CVE-")})
        refs = [r["url"] for r in v.get("references") or [] if r.get("type") in ("ADVISORY", "WEB", "FIX")][:5]
        affected.append({
            "component": {k: comp.get(k) for k in ("ecosystem", "name", "version", "dev", "direct", "source")},
            "id": vid, "aliases": v.get("aliases") or [], "cves": cves,
            "summary": (v.get("summary") or (v.get("details") or "")[:200]).strip(),
            "severity": sev, "base_severity": sev, "cvss_score": score, "cvss_vector": vector,
            "cwe_ids": (v.get("database_specific") or {}).get("cwe_ids") or [],
            "fixed": sorted(_fixed_versions(v, comp["ecosystem"], comp["name"]), key=_vkey),
            "published": v.get("published"), "references": refs,
            "url": f"https://osv.dev/vulnerability/{vid}",
        })
    status["vulns"] = len(ids)
    return affected, status


# ---- KEV / EPSS --------------------------------------------------------------

def load_kev(client: httpx.Client) -> dict:
    return _cached_json("kev.json", 12 * 3600, lambda: client.get(KEV_URL, timeout=60).raise_for_status().json())


def query_epss(client: httpx.Client, cves: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(cves), 50):
        res = client.get(EPSS_URL, params={"cve": ",".join(cves[i:i + 50])}, timeout=30).raise_for_status().json()
        for row in res.get("data") or []:
            out[row["cve"]] = {"epss": float(row["epss"]), "percentile": float(row["percentile"])}
    return out


# ---- NVD watchlist -----------------------------------------------------------

def _nvd_severity(cve: dict) -> tuple[str | None, float | None]:
    metrics = cve.get("metrics") or {}
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
        for m in metrics.get(key) or []:
            data = m.get("cvssData") or {}
            return str(data.get("baseSeverity") or "").lower() or None, data.get("baseScore")
    return None, None


_TEXT_FOLLOW = r"(\s+(v?\d|before|prior|through|versions?|is\s+vulnerable|has|allows|contains|from|when|could|may|"\
               r"does|did|was|up\s+to|and\s+earlier)|[,.:;])"


def nvd_relevance(cve: dict, keyword: str) -> str | None:
    """'cpe' if NVD lists the product as affected, 'text' if the description is about the product
    itself (not something built on it), else None. Keyword search alone is far too noisy:
    'Django' matches every app written in Django."""
    kw = re.sub(r"[^a-z0-9]", "", keyword.lower().removesuffix(".js"))
    for conf in cve.get("configurations") or []:
        for node in conf.get("nodes") or []:
            for match in node.get("cpeMatch") or []:
                parts = str(match.get("criteria", "")).split(":")
                if len(parts) > 4 and match.get("vulnerable") and re.sub(r"[^a-z0-9]", "", parts[4]) in (
                        kw, kw + "js"):
                    return "cpe"
    desc = next((d["value"] for d in cve.get("descriptions") or [] if d.get("lang") == "en"), "")
    pattern = rf"^(?:(?:in|an?\s+issue\s+was\s+discovered\s+in|the)\s+)?{re.escape(keyword)}{_TEXT_FOLLOW}"
    return "text" if re.match(pattern, desc.strip(), re.I) else None


def query_nvd(client: httpx.Client, keywords: list[str], days: int) -> tuple[list[dict], dict]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=min(max(days, 1), 120))  # NVD caps the window at 120 days
    key = os.environ.get("NVD_API_KEY")
    headers = {"apiKey": key} if key else {}
    pause = 0.7 if key else 6.5  # public rate limit: 5 requests / 30 s
    watch: list[dict] = []
    for i, kw in enumerate(keywords):
        if i:
            time.sleep(pause)
        params: dict[str, str | int] = {"keywordSearch": kw, "resultsPerPage": 100,
                  "pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
                  "pubEndDate": end.strftime("%Y-%m-%dT%H:%M:%S.000")}
        res = client.get(NVD_URL, params=params, headers=headers, timeout=60).raise_for_status().json()
        for item in res.get("vulnerabilities") or []:
            cve = item.get("cve") or {}
            relevance = nvd_relevance(cve, kw)
            if not relevance:
                continue
            sev, score = _nvd_severity(cve)
            desc = next((d["value"] for d in cve.get("descriptions") or [] if d.get("lang") == "en"), "")
            watch.append({"keyword": kw, "id": cve.get("id"), "published": cve.get("published"),
                          "severity": sev, "score": score, "summary": " ".join(desc.split())[:300],
                          "kev": bool(cve.get("cisaExploitAdd")), "match": relevance,
                          "url": f"https://nvd.nist.gov/vuln/detail/{cve.get('id')}"})
    rank = {s: i for i, s in enumerate(SEV_ORDER)}
    watch.sort(key=lambda w: (not w["kev"], rank.get(w["severity"] or "info", 9), -(w["score"] or 0)))
    return watch, {"ok": True, "keywords": keywords, "results": len(watch), "window_days": days,
                   "authenticated": bool(key)}


def default_keywords(stack: dict, limit: int = 6) -> list[str]:
    words: list[str] = []
    for fw in (stack.get("frameworks") or []) + (stack.get("databases") or []):
        w = re.sub(r"\s*\(.*\)", "", fw).strip()
        if w and w.lower() not in (x.lower() for x in words):
            words.append(w)
    for image in stack.get("docker_images") or []:
        base = image.split("@")[0].split(":")[0].rsplit("/", 1)[-1]
        if base and base.lower() not in (x.lower() for x in words) and base not in ("alpine", "scratch", "debian"):
            words.append(base)
    return words[:limit]


# ---- orchestration -------------------------------------------------------------

class _IPv4FirstTransport(httpx.BaseTransport):
    """Try IPv4 first, fall back to the system default (IPv6) if IPv4 can't connect.

    On networks with a half-working IPv6 route Python waits ~60 s per host before falling back
    (curl and browsers race both families). IPv6-only networks still work through the fallback.
    """

    def __init__(self) -> None:
        self._v4 = httpx.HTTPTransport(local_address="0.0.0.0", retries=1)  # noqa: S104 - outbound bind
        self._default = httpx.HTTPTransport(retries=1)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return self._v4.handle_request(request)
        except httpx.ConnectError:
            return self._default.handle_request(request)

    def close(self) -> None:
        self._v4.close()
        self._default.close()


def make_client() -> httpx.Client:
    transport = None if os.environ.get("SECQA_IPV6") == "1" else _IPv4FirstTransport()
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, transport=transport)


def _vkey(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else -1 for p in re.split(r"[.+-]", v.lstrip("v")) if p)


def recommended_fix(current: str | None, fixed: list[str]) -> str | None:
    """Smallest fixed version above the installed one (same major first, if any)."""
    if not fixed:
        return None
    if not current:
        return sorted(fixed, key=_vkey)[0]
    cur = _vkey(current)
    above = sorted((f for f in fixed if _vkey(f) > cur), key=_vkey)
    same_major = [f for f in above if _vkey(f)[:1] == cur[:1]]
    pick = same_major or above
    return pick[0] if pick else None

def _bump(sev: str, to: str) -> str:
    return to if SEV_ORDER.index(to) < SEV_ORDER.index(sev) else sev


def _lower(sev: str) -> str:
    return SEV_ORDER[min(SEV_ORDER.index(sev) + 1, len(SEV_ORDER) - 1)]


def run_intel(stack: dict, *, days: int = 30, nvd: bool = True, keywords: list[str] | None = None,
              include_dev: bool = True, client: httpx.Client | None = None) -> dict:
    own = client is None
    client = client or make_client()
    sources: dict[str, Any] = {}
    components = [c for c in stack.get("components") or [] if include_dev or not c.get("dev")]
    try:
        try:
            affected, sources["osv"] = query_osv(client, components)
        except (httpx.HTTPError, ValueError) as exc:
            affected, sources["osv"] = [], {"ok": False, "error": str(exc)[:200]}

        kev_index: dict[str, dict] = {}
        try:
            kev = load_kev(client)
            kev_index = {v["cveID"]: v for v in kev.get("vulnerabilities") or []}
            sources["kev"] = {"ok": True, "catalog_version": kev.get("catalogVersion"), "count": len(kev_index)}
        except (httpx.HTTPError, ValueError) as exc:
            sources["kev"] = {"ok": False, "error": str(exc)[:200]}

        cves = sorted({c for a in affected for c in a["cves"]})
        epss: dict[str, dict] = {}
        if cves:
            try:
                epss = query_epss(client, cves)
                sources["epss"] = {"ok": True, "scored": len(epss)}
            except (httpx.HTTPError, ValueError) as exc:
                sources["epss"] = {"ok": False, "error": str(exc)[:200]}
        else:
            sources["epss"] = {"ok": True, "scored": 0}

        for a in affected:
            a["recommended_fix"] = recommended_fix(a["component"].get("version"), a["fixed"])
            reasons = []
            k = next((kev_index[c] for c in a["cves"] if c in kev_index), None)
            a["kev"] = {"cve": k["cveID"], "date_added": k.get("dateAdded"), "due_date": k.get("dueDate"),
                        "ransomware": k.get("knownRansomwareCampaignUse"),
                        "required_action": k.get("requiredAction")} if k else None
            best = max((epss[c] for c in a["cves"] if c in epss), key=lambda e: e["epss"], default=None)
            a["epss"] = best["epss"] if best else None
            a["epss_percentile"] = best["percentile"] if best else None
            if k:
                a["severity"] = "critical"
                reasons.append("in CISA KEV (actively exploited)")
            elif best and best["epss"] >= 0.5:
                a["severity"] = _bump(a["severity"], "high")
                reasons.append(f"EPSS {best['epss']:.0%} exploitation probability")
            if a["component"].get("dev") and not k:
                a["severity"] = _lower(a["severity"])
                reasons.append("dev dependency: lowered one level")
            a["priority_reason"] = "; ".join(reasons) or None

        watchlist: list[dict] = []
        if nvd:
            kws = keywords if keywords is not None else default_keywords(stack)
            if kws:
                try:
                    watchlist, sources["nvd"] = query_nvd(client, kws, days)
                except (httpx.HTTPError, ValueError) as exc:
                    sources["nvd"] = {"ok": False, "keywords": kws, "error": str(exc)[:200]}
            else:
                sources["nvd"] = {"ok": True, "keywords": [], "results": 0}
    finally:
        if own:
            client.close()

    rank = {s: i for i, s in enumerate(SEV_ORDER)}
    affected.sort(key=lambda a: (a["kev"] is None, rank[a["severity"]], -(a["epss"] or 0)))
    by_sev: dict[str, int] = {}
    for a in affected:
        by_sev[a["severity"]] = by_sev.get(a["severity"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "sources": sources,
        "stats": {
            "components": len(components),
            "affected_components": len({(a["component"]["ecosystem"], a["component"]["name"],
                                         a["component"]["version"]) for a in affected}),
            "vulns": len(affected),
            "kev": sum(1 for a in affected if a["kev"]),
            "epss_high": sum(1 for a in affected if (a["epss"] or 0) >= 0.5),
            "by_severity": by_sev,
            "watchlist": len(watchlist),
        },
        "affected": affected,
        "watchlist": watchlist,
    }
