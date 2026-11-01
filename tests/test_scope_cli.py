from __future__ import annotations

import textwrap

import pytest

from secqa import cli
from secqa.hub.config import Settings
from secqa.hub.demo import seed
from secqa.scope import ScopeError, check_perf, check_target, load_scope

SCOPE = textwrap.dedent("""
    project_name: demo
    allowed_targets:
      - host: 127.0.0.1
        ports: [3000]
      - host: staging.example.com
        ports: [443]
    performance:
      enabled: true
      max_vus: 20
      allowed_profiles: [smoke, load, stress]
    authorized_by: QA lead
    authorized_at: "2026-11-01"
""")


@pytest.fixture
def scope_file(tmp_path):
    p = tmp_path / "scope.yml"
    p.write_text(SCOPE)
    return p


def test_check_target(scope_file):
    s = load_scope(scope_file)
    check_target(s, "http://127.0.0.1:3000/api")
    check_target(s, "127.0.0.1:3000")
    with pytest.raises(ScopeError):
        check_target(s, "http://127.0.0.1:8080")
    with pytest.raises(ScopeError):
        check_target(s, "https://evil.example.org")


def test_unauthorized_scope_blocks_active(tmp_path):
    p = tmp_path / "scope.yml"
    p.write_text(SCOPE.replace("authorized_by: QA lead", "authorized_by: ''"))
    s = load_scope(p)
    with pytest.raises(ScopeError, match="not authorized"):
        check_target(s, "127.0.0.1:3000")
    check_target(s, "127.0.0.1:3000", active=False)


def test_perf_gates(scope_file):
    s = load_scope(scope_file)
    check_perf(s, "http://127.0.0.1:3000", "load", 20)
    with pytest.raises(ScopeError, match="max_vus"):
        check_perf(s, "http://127.0.0.1:3000", "load", 21)
    with pytest.raises(ScopeError, match="confirmation"):
        check_perf(s, "http://127.0.0.1:3000", "stress", 5)
    check_perf(s, "http://127.0.0.1:3000", "stress", 5, confirmed_heavy=True)
    with pytest.raises(ScopeError, match="allowed_profiles"):
        check_perf(s, "http://127.0.0.1:3000", "soak", 5)
    with pytest.raises(ScopeError, match="not local"):
        check_perf(s, "https://staging.example.com", "load", 5)


def test_cli_scope_check_exit_codes(scope_file, capsys):
    assert cli.main(["scope", "check", "http://127.0.0.1:3000", "--scope", str(scope_file)]) == 0
    assert cli.main(["scope", "check", "http://10.0.0.1", "--scope", str(scope_file)]) == 1
    assert "not listed" in capsys.readouterr().err


def test_cli_init_installs_agent_kit(tmp_path):
    assert cli.main(["init", str(tmp_path), "--project", "shop"]) == 0
    assert (tmp_path / ".claude/skills/pentest-run/SKILL.md").is_file()
    assert (tmp_path / ".claude/skills/perf-test/SKILL.md").is_file()
    assert (tmp_path / "perf/scenarios/endpoints.js").is_file()
    assert "project: SHOP" in (tmp_path / ".secqa/config.yml").read_text()
    assert "scope.yml" in (tmp_path / ".gitignore").read_text()


def test_cli_reports_unreachable_hub(capsys):
    assert cli.main(["--url", "http://127.0.0.1:9", "status"]) == 1
    assert "cannot reach the Hub" in capsys.readouterr().err


def test_demo_seed_is_idempotent(tmp_path):
    s = Settings(data_dir=tmp_path)
    assert "seeded" in seed(s)
    assert "already exists" in seed(s)
