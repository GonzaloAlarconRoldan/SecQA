# Deploying the Hub

## Docker (recommended)

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into SECQA_API_TOKEN
docker compose up -d
```

The container runs as a non-root user, stores everything in the `secqa-data` volume (`/data`), applies database migrations on start and exposes a health check at `/api/health`.

Published images (from tagged releases): `ghcr.io/gonzaloalarconroldan/secqa-hub:<version>`.

## pip

```bash
pip install "secqa[hub] @ git+https://github.com/GonzaloAlarconRoldan/SecQA"
SECQA_API_TOKEN=... secqa hub serve --host 127.0.0.1 --port 8787 --data-dir /var/lib/secqa
```

The UI is bundled in released wheels and Docker images. From a source checkout, build it first: `cd frontend && npm ci && npm run build`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SECQA_API_TOKEN` | — | Bearer token required on every `/api` call except `health` and `meta`. **Set it for any shared Hub.** |
| `SECQA_DATA_DIR` | `.secqa-data` | SQLite database and attachments |
| `SECQA_DATABASE_URL` | SQLite in data dir | e.g. `postgresql+psycopg://user:pass@host/secqa` (install `secqa[postgres]`) |
| `SECQA_SLA_{CRITICAL,HIGH,MEDIUM,LOW}_DAYS` | 7 / 30 / 90 / 180 | SLA per severity |
| `SECQA_PERF_REGRESSION_TOLERANCE` | `0.10` | Allowed degradation vs. baseline |
| `SECQA_CORS_ORIGINS` | `[]` | JSON list; only for a UI served from another origin |
| `SECQA_DEMO_SEED` | — | `1` loads the Juice Shop demo dataset on start |

## Postgres

```yaml
# docker-compose.override.yml
services:
  db:
    image: postgres:17-alpine
    environment: { POSTGRES_USER: secqa, POSTGRES_PASSWORD: change-me, POSTGRES_DB: secqa }
    volumes: [pg-data:/var/lib/postgresql/data]
  hub:
    environment:
      SECQA_DATABASE_URL: postgresql+psycopg://secqa:change-me@db:5432/secqa
    depends_on: [db]
volumes:
  pg-data:
```

## Exposing it to a team

The Hub holds vulnerability details. Before it leaves `127.0.0.1`:

1. Set `SECQA_API_TOKEN`.
2. Terminate TLS in a reverse proxy (Caddy, nginx, Traefik) and keep the container port on loopback or a private network.
3. Ideally put SSO in front (oauth2-proxy, Cloudflare Access, Tailscale) — the built-in token is a shared secret, not per-user auth. The `X-SecQA-Actor` header (set by the UI from Settings and by the CLI from `SECQA_ACTOR`) is recorded in history and the audit log, but it is self-declared.

Minimal Caddyfile:

```
secqa.internal.example.com {
  reverse_proxy 127.0.0.1:8787
}
```

## Backups

- SQLite: `sqlite3 /data/secqa.db ".backup '/backup/secqa-$(date +%F).db'"` plus the `/data/attachments` directory.
- Postgres: `pg_dump`, plus attachments.

## Upgrading

Pull the new image (or `pip install -U`) and restart. Migrations run automatically on start; back up first.
