"""`secqa` command-line interface.

The CLI is the only way agents (Claude Code skills) and CI talk to the Hub, so every
write is validated server-side instead of hand-written SQL.

Configuration (highest precedence first):
  * flags (--url, --project, --run)
  * env: SECQA_URL, SECQA_TOKEN, SECQA_PROJECT, SECQA_ACTOR
  * `.secqa/config.yml` in the current directory (hub_url, project) — never put the token there
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

import httpx
import yaml

from . import __version__
from .scope import ScopeError, check_perf, check_target, load_scope

STATE_DIR = Path(".secqa")
CONFIG_FILE = STATE_DIR / "config.yml"
CURRENT_RUN_FILE = STATE_DIR / "current-run"
DEFAULT_URL = "http://127.0.0.1:8787"


class CLIError(Exception):
    pass


# ---- config & client -------------------------------------------------------

def _file_config() -> dict[str, Any]:
    if CONFIG_FILE.is_file():
        return yaml.safe_load(CONFIG_FILE.read_text("utf-8")) or {}
    return {}


def _cfg(args: argparse.Namespace, key: str, env: str, default: str | None = None) -> str | None:
    return getattr(args, key, None) or os.environ.get(env) or _file_config().get(
        "hub_url" if key == "url" else key) or default


def client(args: argparse.Namespace) -> httpx.Client:
    headers = {"X-SecQA-Actor": os.environ.get("SECQA_ACTOR", "agent:secqa-cli"),
               "User-Agent": f"secqa-cli/{__version__}"}
    token = os.environ.get("SECQA_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=_cfg(args, "url", "SECQA_URL", DEFAULT_URL) or DEFAULT_URL,
                        headers=headers, timeout=60)


def _call(args, method: str, path: str, **kwargs) -> Any:
    try:
        with client(args) as c:
            r = c.request(method, path, **kwargs)
    except httpx.ConnectError as exc:
        raise CLIError(f"cannot reach the Hub at {_cfg(args, 'url', 'SECQA_URL', DEFAULT_URL)} "
                       "— start it with `secqa hub serve` or set SECQA_URL") from exc
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text
        raise CLIError(f"{method} {path} → {r.status_code}: {detail}")
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None


def _project(args) -> str:
    key = _cfg(args, "project", "SECQA_PROJECT")
    if not key:
        raise CLIError("no project — pass --project KEY, set SECQA_PROJECT or run `secqa init`")
    return key.upper()


def _run_id(args) -> int:
    if getattr(args, "run", None):
        return int(args.run)
    if os.environ.get("SECQA_RUN"):
        return int(os.environ["SECQA_RUN"])
    if CURRENT_RUN_FILE.is_file():
        return int(CURRENT_RUN_FILE.read_text().strip())
    raise CLIError("no run — pass --run ID or start one with `secqa run start`")


def _out(args, data: Any, human: str | None = None) -> None:
    if getattr(args, "json", False) or human is None:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(human)


def _git(*cmd: str) -> str | None:
    try:
        return subprocess.run(["git", *cmd], capture_output=True, text=True, check=True,  # noqa: S603,S607
                              timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# ---- commands --------------------------------------------------------------

def cmd_hub_serve(args) -> None:
    try:
        import uvicorn

        from .hub.app import create_app
        from .hub.config import Settings
    except ImportError as exc:
        raise CLIError("Hub dependencies missing — install with: pip install 'secqa[hub]'") from exc
    overrides: dict[str, Any] = {}
    if args.data_dir:
        overrides["data_dir"] = Path(args.data_dir)
    settings = Settings(**overrides)
    if os.environ.get("SECQA_DEMO_SEED", "").lower() in ("1", "true", "yes"):
        from .hub.demo import seed

        print(f"[secqa] {seed(settings)}")
    if args.host not in ("127.0.0.1", "localhost", "::1") and not settings.api_token:
        print("[secqa] WARNING: binding to a non-loopback address without SECQA_API_TOKEN — "
              "anyone on the network can read and modify your data.", file=sys.stderr)
    print(f"[secqa] Hub v{__version__} on http://{args.host}:{args.port}  (API docs: /api/docs)")
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="warning")


def cmd_init(args) -> None:
    target = Path(args.path).resolve()
    if not target.is_dir():
        raise CLIError(f"{target} is not a directory")
    kit = resources.files("secqa").joinpath("agent_kit")
    kit_path = Path(str(kit))
    if not kit_path.is_dir():  # running from a source checkout
        kit_path = Path(__file__).resolve().parents[2] / "agent-kit"
    if not kit_path.is_dir():
        raise CLIError("agent kit not found in this installation")

    skills_dst = target / ".claude" / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    for skill in (kit_path / "skills").iterdir():
        dst = skills_dst / skill.name
        if dst.exists() and not args.force:
            print(f"[skip] {dst.relative_to(target)} exists (use --force to overwrite)")
            continue
        shutil.copytree(skill, dst, dirs_exist_ok=True)
        print(f"[ok]   {dst.relative_to(target)}")

    perf_dst = target / "perf"
    if not perf_dst.exists() or args.force:
        shutil.copytree(kit_path / "perf", perf_dst, dirs_exist_ok=True)
        print(f"[ok]   {perf_dst.relative_to(target)}/")
    if not (target / "scope.yml").exists():
        shutil.copy(kit_path / "scope.yml.example", target / "scope.yml.example")
        print("[ok]   scope.yml.example  → copy to scope.yml and fill it in")

    state = target / ".secqa"
    state.mkdir(exist_ok=True)
    cfg = {"hub_url": args.url or DEFAULT_URL}
    if args.project:
        cfg["project"] = args.project.upper()
    (state / "config.yml").write_text(yaml.safe_dump(cfg, sort_keys=False), "utf-8")
    (state / ".gitignore").write_text("current-run\n", "utf-8")

    gitignore = target / ".gitignore"
    rules = "\n# SecQA\nscope.yml\nsecqa-out/\n"
    existing = gitignore.read_text("utf-8") if gitignore.exists() else ""
    if "# SecQA" not in existing:
        gitignore.write_text(existing + rules, "utf-8")
    print(f"[ok]   .secqa/config.yml → hub {cfg['hub_url']}"
          + (f", project {cfg['project']}" if "project" in cfg else ""))
    print("\nNext: create scope.yml, make sure the Hub is running, then in Claude Code run /pentest-run")


def cmd_status(args) -> None:
    health = _call(args, "GET", "/api/health")
    info = {"hub": _cfg(args, "url", "SECQA_URL", DEFAULT_URL), "hub_version": health["version"],
            "project": _cfg(args, "project", "SECQA_PROJECT"),
            "current_run": CURRENT_RUN_FILE.read_text().strip() if CURRENT_RUN_FILE.is_file() else None}
    _out(args, info, "\n".join(f"{k:12} {v}" for k, v in info.items()))


def cmd_project_create(args) -> None:
    body = {"key": args.key.upper(), "name": args.name or args.key, "description": args.description,
            "repo_url": args.repo_url}
    p = _call(args, "POST", "/api/projects", json=body)
    _out(args, p, f"created project {p['key']} (id {p['id']})")


def cmd_project_list(args) -> None:
    rows = _call(args, "GET", "/api/projects")
    _out(args, rows, "\n".join(
        f"{p['key']:10} {p['name']:30} open={p['open_defects']:<4} "
        f"critical={p['critical_open']:<3} runs={p['run_count']}"
        for p in rows) or "(no projects)")


def cmd_run_start(args) -> None:
    body = {
        "kind": args.kind, "name": args.name, "target": args.target, "environment": args.env,
        "branch": args.branch or _git("rev-parse", "--abbrev-ref", "HEAD"),
        "commit_sha": args.commit or _git("rev-parse", "HEAD"),
    }
    if args.scope and Path(args.scope).is_file():
        body["scope_snapshot"] = yaml.safe_load(Path(args.scope).read_text("utf-8"))
    run = _call(args, "POST", f"/api/projects/{_project(args)}/runs", json=body)
    STATE_DIR.mkdir(exist_ok=True)
    CURRENT_RUN_FILE.write_text(str(run["id"]))
    _out(args, run, str(run["id"]) if args.quiet else f"started {run['kind']} run #{run['id']}")


def cmd_run_finish(args) -> None:
    run_id = _run_id(args)
    body = {"status": args.status, "notes": args.notes}
    run = _call(args, "POST", f"/api/runs/{run_id}/finish", json={k: v for k, v in body.items() if v})
    if CURRENT_RUN_FILE.is_file() and CURRENT_RUN_FILE.read_text().strip() == str(run_id):
        CURRENT_RUN_FILE.unlink()
    sev = run.get("findings_by_severity", {})
    _out(args, run, f"run #{run_id} finished: {run['status']}  findings={sev}")


def cmd_run_update(args) -> None:
    body: dict[str, Any] = {}
    if args.stack:
        body["stack_detected"] = json.loads(Path(args.stack).read_text("utf-8"))
    if args.baseline:
        body["is_baseline"] = True
    if args.notes:
        body["notes"] = args.notes
    run = _call(args, "PATCH", f"/api/runs/{_run_id(args)}", json=body)
    _out(args, run, f"updated run #{run['id']}")


def cmd_ingest(args) -> None:
    path = Path(args.file)
    if not path.is_file():
        raise CLIError(f"{path} not found")
    params = {"scenario": args.scenario, "create_defects": str(not args.no_defects).lower()}
    if args.source:
        params["source"] = args.source
    with path.open("rb") as fh:
        res = _call(args, "POST", f"/api/runs/{_run_id(args)}/ingest/{args.format}", params=params,
                    files={"file": (path.name, fh)})
    extra = f" {res['detail']}" if res.get("detail") else ""
    _out(args, res, f"{args.format}: {res['created']} created, {res['suppressed']} auto-suppressed, "
                    f"{res['skipped']} duplicates{extra}")


def cmd_finding_add(args) -> None:
    if args.file:
        items = json.loads(Path(args.file).read_text("utf-8"))
        items = items if isinstance(items, list) else [items]
    else:
        if not (args.title and args.severity):
            raise CLIError("--title and --severity are required (or pass --file findings.json)")
        items = [{k: v for k, v in {
            "title": args.title, "severity": args.severity, "category": args.category, "source": args.source,
            "tool": args.tool, "description": args.description, "file_path": args.path,
            "line_start": args.line, "endpoint": args.endpoint, "evidence": args.evidence,
            "remediation": args.remediation, "cwe_id": args.cwe,
        }.items() if v is not None}]
    res = _call(args, "POST", f"/api/runs/{_run_id(args)}/findings", json=items)
    _out(args, res, f"{res['created']} created, {res['suppressed']} auto-suppressed, "
                    f"{res['linked_to_defects']} linked to existing defects, {res['skipped']} duplicates")


def cmd_results_add(args) -> None:
    items = json.loads(Path(args.file).read_text("utf-8"))
    res = _call(args, "POST", f"/api/runs/{_run_id(args)}/results", json=items)
    _out(args, res, f"{res['created']} results stored")


def cmd_audit(args) -> None:
    run_id = None
    with contextlib.suppress(CLIError):
        run_id = _run_id(args)
    _call(args, "POST", f"/api/projects/{_project(args)}/audit",
          json={"action": args.action, "target": args.target, "run_id": run_id})
    print("[audit] logged")


def cmd_scope_check(args) -> None:
    scope = load_scope(args.scope)
    if args.profile:
        check_perf(scope, args.target, args.profile, args.vus, confirmed_heavy=args.confirm_heavy)
        print(f"[scope] OK — {args.profile} load test against {args.target} with {args.vus} VUs is allowed")
    else:
        check_target(scope, args.target, active=not args.passive)
        print(f"[scope] OK — {args.target} is in scope")


def cmd_scope_show(args) -> None:
    scope = load_scope(args.scope)
    _out(args, {
        "project_name": scope.project_name, "authorized": scope.authorized,
        "authorized_by": scope.authorized_by, "allowed_targets": scope.allowed_targets,
        "dast_aggressiveness": scope.dast_aggressiveness, "performance": scope.perf.__dict__,
    })


def cmd_demo_seed(args) -> None:
    try:
        from .hub.config import Settings
        from .hub.demo import seed
    except ImportError as exc:
        raise CLIError("Hub dependencies missing — install with: pip install 'secqa[hub]'") from exc
    overrides: dict[str, Any] = {"data_dir": Path(args.data_dir)} if args.data_dir else {}
    print(f"[secqa] {seed(Settings(**overrides), args.project_key)}")


# ---- parser ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="secqa", description="SecQA — security & performance QA toolkit")
    p.add_argument("--version", action="version", version=f"secqa {__version__}")
    p.add_argument("--url", help=f"Hub URL (default {DEFAULT_URL})")
    p.add_argument("--project", help="project key")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    hub = sub.add_parser("hub", help="run the Hub server").add_subparsers(dest="sub", required=True)
    s = hub.add_parser("serve", help="start the web Hub")
    s.add_argument("--host", default=os.environ.get("SECQA_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("SECQA_PORT", "8787")))
    s.add_argument("--data-dir")
    s.set_defaults(func=cmd_hub_serve)

    s = sub.add_parser("init", help="install the agent kit (skills, k6 templates, scope) into a project")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--force", action="store_true")
    # SUPPRESS so these don't reset the global --url/--project when omitted here
    s.add_argument("--project", default=argparse.SUPPRESS, help="project key to write into .secqa/config.yml")
    s.add_argument("--url", default=argparse.SUPPRESS, help="Hub URL to write into .secqa/config.yml")
    s.set_defaults(func=cmd_init)

    sub.add_parser("status", help="check Hub connectivity and current context").set_defaults(func=cmd_status)

    proj = sub.add_parser("project", help="manage projects").add_subparsers(dest="sub", required=True)
    s = proj.add_parser("create")
    s.add_argument("key")
    s.add_argument("--name")
    s.add_argument("--description")
    s.add_argument("--repo-url")
    s.set_defaults(func=cmd_project_create)
    proj.add_parser("list").set_defaults(func=cmd_project_list)

    run = sub.add_parser("run", help="manage runs").add_subparsers(dest="sub", required=True)
    s = run.add_parser("start")
    s.add_argument("--kind", required=True, choices=["security", "performance", "functional", "manual"])
    s.add_argument("--name")
    s.add_argument("--target")
    s.add_argument("--env")
    s.add_argument("--branch")
    s.add_argument("--commit")
    s.add_argument("--scope", default="scope.yml", help="snapshot this scope file into the run")
    s.add_argument("-q", "--quiet", action="store_true", help="print only the run id")
    s.set_defaults(func=cmd_run_start)
    s = run.add_parser("finish")
    s.add_argument("--run")
    s.add_argument("--status", choices=["passed", "failed", "completed", "aborted"])
    s.add_argument("--notes")
    s.set_defaults(func=cmd_run_finish)
    s = run.add_parser("update")
    s.add_argument("--run")
    s.add_argument("--stack", help="JSON file with the recon stack summary")
    s.add_argument("--baseline", action="store_true", help="mark as performance baseline")
    s.add_argument("--notes")
    s.set_defaults(func=cmd_run_update)

    s = sub.add_parser("ingest", help="upload a tool report (sarif, k6, jtl, junit)")
    s.add_argument("format", choices=["sarif", "k6", "jtl", "junit"])
    s.add_argument("file")
    s.add_argument("--run")
    s.add_argument("--source", help="sarif: override finding source (sast, sca, secrets, dast, api)")
    s.add_argument("--scenario", default="default", help="k6/jtl: scenario/profile name")
    s.add_argument("--no-defects", action="store_true", help="k6/jtl: don't open a defect on regression")
    s.set_defaults(func=cmd_ingest)

    finding = sub.add_parser("finding", help="add findings").add_subparsers(dest="sub", required=True)
    s = finding.add_parser("add")
    s.add_argument("--run")
    s.add_argument("--file", help="JSON file with one finding or a list")
    s.add_argument("--title")
    s.add_argument("--severity", choices=["critical", "high", "medium", "low", "info"])
    s.add_argument("--category")
    s.add_argument("--source", default="manual")
    s.add_argument("--tool")
    s.add_argument("--description")
    s.add_argument("--path")
    s.add_argument("--line", type=int)
    s.add_argument("--endpoint")
    s.add_argument("--evidence")
    s.add_argument("--remediation")
    s.add_argument("--cwe")
    s.set_defaults(func=cmd_finding_add)

    results = sub.add_parser("results", help="add test results").add_subparsers(dest="sub", required=True)
    s = results.add_parser("add")
    s.add_argument("file", help="JSON list of {name, status, test_case_key?, duration_ms?, message?}")
    s.add_argument("--run")
    s.set_defaults(func=cmd_results_add)

    s = sub.add_parser("audit", help="record an active action in the audit log")
    s.add_argument("action")
    s.add_argument("--target")
    s.add_argument("--run")
    s.set_defaults(func=cmd_audit)

    scope = sub.add_parser("scope", help="validate targets against scope.yml").add_subparsers(
        dest="sub", required=True)
    s = scope.add_parser("check", help="exit 1 unless the target is authorized")
    s.add_argument("target", help="URL or host:port")
    s.add_argument("--scope", default="scope.yml")
    s.add_argument("--passive", action="store_true", help="skip the authorized_by requirement")
    s.add_argument("--profile", help="load-test profile (smoke, load, stress, spike, soak)")
    s.add_argument("--vus", type=int, default=1)
    s.add_argument("--confirm-heavy", action="store_true",
                   help="the user explicitly confirmed a stress/spike/soak test in this session")
    s.set_defaults(func=cmd_scope_check)
    s = scope.add_parser("show")
    s.add_argument("--scope", default="scope.yml")
    s.set_defaults(func=cmd_scope_show)

    demo = sub.add_parser("demo", help="demo data").add_subparsers(dest="sub", required=True)
    s = demo.add_parser("seed", help="load a realistic Juice Shop dataset into the Hub database")
    s.add_argument("--project-key", default="JUICE")
    s.add_argument("--data-dir", help="Hub data dir (default: SECQA_DATA_DIR or .secqa-data)")
    s.set_defaults(func=cmd_demo_seed)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (CLIError, ScopeError) as exc:
        print(f"[secqa] error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
