# SecQA — notes for Claude Code

This repo is the SecQA framework itself (not a project under test).

- `src/secqa/hub/` — FastAPI Hub (models, routers, parsers, services). Schema changes need an Alembic migration in `src/secqa/hub/migrations/versions/`.
- `src/secqa/cli.py` — `secqa` CLI; the only way agent skills write to the Hub.
- `agent-kit/` — what `secqa init` copies into target projects: skills (`agent-kit/skills`, symlinked from `.claude/skills` so they load here too), k6/JMeter kit, `scope.yml.example`.
- `frontend/` — React UI, built into `src/secqa/hub/static/`.

Checks: `ruff check src tests && mypy src && pytest`, and in `frontend/`: `npm run typecheck && npm run lint && npm run build`.

Safety invariants to preserve in any change: active traffic only after `secqa scope check`; load tests capped by `performance.max_vus`; secrets masked before ingestion; reports only include triaged data.
