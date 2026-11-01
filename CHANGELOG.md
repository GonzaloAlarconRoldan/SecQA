# Changelog

All notable changes to this project are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows [SemVer](https://semver.org/).

## [2.0.0] - 2026-11-01

### Added
- **SecQA Hub**: multi-project FastAPI + React web app with:
  - overview KPIs (open defects, SLA breaches, MTTR, pass rate),
  - executions, findings triage with bulk actions,
  - defect/incident tracker (table + kanban, comments, attachments, field history),
  - test-case repository with run history,
  - performance trends, OWASP/ISO 27001 compliance matrix,
  - EN/ES HTML reports, CSV and SARIF exports, OpenAPI docs.
- Finding fingerprinting: de-duplication, remembered false positives / accepted risks, automatic defect reopen on regression.
- SLA due dates per severity and breach tracking.
- **Performance testing**: `perf-test` skill and k6 kit (smoke, load, stress, spike, soak profiles capped by `scope.yml`), per-endpoint metrics, baselines, automatic regression defects. JMeter JTL import and a starter `.jmx` plan.
- Parsers for SARIF 2.1.0, k6 summaries (both formats), JMeter CSV JTL and JUnit XML.
- `secqa` CLI: `init`, `hub serve`, `project`, `run`, `ingest`, `finding`, `results`, `audit`, `scope check|show`, `demo seed`.
- `performance` section in `scope.yml` and `secqa scope check` enforcement for all active phases.
- Docker image (non-root, health check), demo stack with OWASP Juice Shop and a seeded dataset.
- CI (ruff, mypy, pytest on 3.10–3.13, UI typecheck/lint/build, k6 script inspection, container smoke test), CodeQL, release workflow publishing to GHCR, Dependabot.
- Docs: architecture, integrations, deployment; bilingual README; contributing, security and conduct policies; issue/PR templates.

### Changed
- Agent skills now write only through the `secqa` CLI (validated) instead of inline SQL; moved to `agent-kit/skills/`.
- Findings use a triage workflow (`new`, `confirmed`, `false_positive`, `accepted_risk`, `duplicate`) instead of `pending/approved/rejected`.
- Mapping file moved to `src/secqa/data/iso_owasp_map.json`.

### Removed
- Stdlib review server, `findings.db` schema/init script, standalone report generator and `install.sh` (replaced by the Hub and `secqa init`).

## [1.0.0] - 2026-10-24

### Added
- Initial framework: phase skills (recon, SAST, SCA, secrets, API, DAST, report, run), SQLite findings DB, local review dashboard, HTML/PDF report generator, OWASP/CWE/ISO mapping.
