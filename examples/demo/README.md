# SecQA demo

```bash
docker compose -f examples/demo/docker-compose.yml up --build
```

| | URL |
|---|---|
| SecQA Hub (seeded with 12 weeks of history) | http://127.0.0.1:8787 |
| OWASP Juice Shop (live target) | http://127.0.0.1:3000 |

Without Docker:

```bash
pip install -e ".[hub]"
secqa demo seed && secqa hub serve
```

## Run a real scan against Juice Shop

```bash
git clone --depth 1 https://github.com/juice-shop/juice-shop /tmp/juice-shop
secqa init /tmp/juice-shop --project JS
cp examples/demo/scope.yml /tmp/juice-shop/scope.yml
cd /tmp/juice-shop && secqa project create JS --name "Juice Shop (live)"
claude   # then: /pentest-run   or   /perf-test
```

Juice Shop is intentionally insecure. Keep it bound to `127.0.0.1` and never expose it.
