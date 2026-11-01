# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue. Use [GitHub private vulnerability reporting](https://github.com/GonzaloAlarconRoldan/SecQA/security/advisories/new). You will get a response within 7 days.

## Supported versions

| Version | Supported |
|---|---|
| 2.x | ✅ |
| 1.x (stdlib dashboard) | ❌ |

## Using SecQA responsibly

SecQA drives security scanners and load generators. Misused, those are attacks.

- **Only test systems you own or are explicitly authorized to test.** `scope.yml` and `secqa scope check` enforce an allow-list, but they cannot know whether your authorization is real.
- Active phases (dynamic API tests, DAST, load tests) are designed for **local or self-owned containers** — never production, shared staging or third-party hosts.
- Load-test profiles are capped by `performance.max_vus`; `stress`, `spike` and `soak` need explicit confirmation per session.

## Hardening the Hub

- The Hub stores vulnerability details — treat its database as sensitive.
- It binds to `127.0.0.1` by default. Before exposing it to a team, set `SECQA_API_TOKEN` and put it behind a TLS reverse proxy.
- Secrets found by scanners must be **masked** before ingestion (`gitleaks --redact`). The agent skills enforce this; manual uploads should too.
- Attachments are always served as downloads (`Content-Disposition: attachment`, `nosniff`, `CSP: sandbox`) except a small allow-list of image/PDF/text types.
- Reports and CSV exports only include triaged data; CSV cells are neutralised against formula injection.
