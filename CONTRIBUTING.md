# Contributing

Thanks for wanting to improve SecQA! Contributions in English or Spanish are welcome.

## Good first contributions

- A parser for another report format (ZAP JSON, npm audit, Trivy JSON…) in `src/secqa/hub/parsers/`
- A new category in `src/secqa/data/iso_owasp_map.json`
- A k6 scenario for a common pattern (GraphQL, WebSockets) in `agent-kit/perf/`
- UI polish and translations in `frontend/src/i18n/`
- Docs: guides for a specific stack

## Development setup

```bash
uv venv && uv pip install -e ".[dev]"      # or: python -m venv .venv && pip install -e ".[dev]"
(cd frontend && npm ci)

# terminal 1 — API with demo data
secqa demo seed --data-dir .secqa-data && secqa hub serve --data-dir .secqa-data
# terminal 2 — UI with hot reload on http://localhost:5173 (proxies /api to :8787)
cd frontend && npm run dev
```

## Before opening a PR

```bash
ruff check src tests
mypy src
pytest
(cd frontend && npm run typecheck && npm run lint && npm run build)
```

Schema changes need a migration:

```bash
SECQA_DATA_DIR=.secqa-data alembic revision --autogenerate -m "add x to defects"
```

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat(hub): add ZAP JSON parser
fix(cli): keep run id when finish fails
docs: add GraphQL perf guide
```

## Rules

- **Never commit real findings, secrets, `scope.yml` or Hub databases.** Test fixtures must be synthetic.
- Agent skills must keep the safety gates: `secqa scope check` before any active traffic, audit log entries, masking of secrets.
- Keep the CLI dependency-light (`httpx`, `pyyaml`); Hub-only dependencies go in the `hub` extra.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
