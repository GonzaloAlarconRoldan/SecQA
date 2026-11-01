# SecQA Vuln Lab

A ~150-line, **deliberately vulnerable** shop for trying SecQA end to end without Docker. Python stdlib only, bound to `127.0.0.1`.

```bash
python examples/vuln-lab/app.py          # http://127.0.0.1:5055
```

| Planted issue | Where | Try |
|---|---|---|
| SQL injection → login bypass | `POST /login` | email `' OR 1=1--`, any password → logged in as admin |
| IDOR | `GET /basket?id=N` | log in as anyone, change `id` → other users' name and address |
| Excessive data exposure | `GET /api/users` | password hashes and roles, no auth |
| Reflected XSS | `GET /search?q=` | `?q=<b>secqa</b>` renders as HTML |
| Weak hashing | `app.py` | MD5 passwords (SAST finds it) |

Scope for it (`scope.yml`):

```yaml
allowed_targets:
  - host: "127.0.0.1"
    ports: [5055]
authorized_by: "me (local lab)"
authorized_at: "2026-11-01"
```

Then run `/pentest-run` in Claude Code, or try the evidence flow by hand:

```bash
secqa capture http://127.0.0.1:5055/login -o after.png \
  --fill "#email=' OR 1=1--" --fill "input[name=password]=x" --click button --highlight "#role"
```

Never expose it to a network or reuse its code.
