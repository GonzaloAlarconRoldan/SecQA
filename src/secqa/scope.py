"""scope.yml loading and enforcement. Every active phase (DAST, dynamic API tests, load tests)
must pass `check_target` before sending a single request."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

PROFILES_NEEDING_EXTRA_CONFIRMATION = {"stress", "spike", "soak", "breakpoint"}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0", "host.docker.internal"}  # noqa: S104


class ScopeError(Exception):
    pass


@dataclass
class PerfLimits:
    enabled: bool = False
    max_vus: int = 20
    max_duration: str = "5m"
    allowed_profiles: list[str] = field(default_factory=lambda: ["smoke", "load"])
    thresholds: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scope:
    project_name: str
    allowed_targets: list[dict[str, Any]]
    exclude_paths: list[str]
    dast_aggressiveness: str
    authorized_by: str
    authorized_at: str
    perf: PerfLimits
    raw: dict[str, Any]

    @property
    def authorized(self) -> bool:
        return bool(self.authorized_by and self.authorized_at)


def load_scope(path: str | Path = "scope.yml") -> Scope:
    p = Path(path)
    if not p.is_file():
        raise ScopeError(f"{p} not found — copy scope.yml.example to scope.yml and fill it in")
    data = yaml.safe_load(p.read_text("utf-8")) or {}
    perf_raw = data.get("performance") or {}
    perf = PerfLimits(**{k: v for k, v in perf_raw.items() if k in PerfLimits.__dataclass_fields__})
    return Scope(
        project_name=str(data.get("project_name", "")),
        allowed_targets=list(data.get("allowed_targets") or []),
        exclude_paths=list(data.get("exclude_paths") or []),
        dast_aggressiveness=str(data.get("dast_aggressiveness", "passive")),
        authorized_by=str(data.get("authorized_by") or ""),
        authorized_at=str(data.get("authorized_at") or ""),
        perf=perf,
        raw=data,
    )


def _host_port(target: str) -> tuple[str, int | None]:
    if "://" not in target:
        target = "http://" + target
    u = urlparse(target)
    if not u.hostname:
        raise ScopeError(f"cannot parse target '{target}'")
    port = u.port or {"http": 80, "https": 443}.get(u.scheme)
    return u.hostname.lower(), port


def check_target(scope: Scope, target: str, *, active: bool = True) -> None:
    """Raise ScopeError unless `target` (URL or host:port) is explicitly allowed."""
    if active and not scope.authorized:
        raise ScopeError("scope.yml has no authorized_by/authorized_at — active testing is not authorized")
    host, port = _host_port(target)
    for entry in scope.allowed_targets:
        if str(entry.get("host", "")).lower() != host:
            continue
        ports = entry.get("ports")
        if not ports or port in [int(p) for p in ports]:
            return
    raise ScopeError(f"{host}:{port} is not listed in scope.yml allowed_targets")


def check_perf(scope: Scope, target: str, profile: str, vus: int, *, confirmed_heavy: bool = False) -> None:
    """Gate a load test: target in scope, perf enabled, profile allowed, VUs under the cap."""
    check_target(scope, target, active=True)
    perf = scope.perf
    if not perf.enabled:
        raise ScopeError("performance testing is disabled in scope.yml (performance.enabled: false)")
    if profile not in perf.allowed_profiles:
        raise ScopeError(f"profile '{profile}' is not in performance.allowed_profiles {perf.allowed_profiles}")
    if profile in PROFILES_NEEDING_EXTRA_CONFIRMATION and not confirmed_heavy:
        raise ScopeError(f"profile '{profile}' needs explicit user confirmation (--confirm-heavy)")
    if vus > perf.max_vus:
        raise ScopeError(f"{vus} VUs exceeds performance.max_vus={perf.max_vus}")
    host, _ = _host_port(target)
    if host not in LOCAL_HOSTS and not any(e.get("non_local_ok") for e in scope.allowed_targets
                                           if str(e.get("host", "")).lower() == host):
        raise ScopeError(f"{host} is not local; load tests only run against local/owned containers "
                         "(set non_local_ok: true on that target if you own it and accept the risk)")
