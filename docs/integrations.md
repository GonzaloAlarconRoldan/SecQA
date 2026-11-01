# Integrations

Everything goes through `secqa ingest <format> <file>` (or `POST /api/runs/{id}/ingest/{format}`).

## Security tools (SARIF)

| Tool | Command | `--source` |
|---|---|---|
| Semgrep | `semgrep --config auto --sarif -o semgrep.sarif .` | `sast` |
| Bandit | `bandit -r . -f sarif -o bandit.sarif` | `sast` |
| gosec | `gosec -fmt sarif -out gosec.sarif ./...` | `sast` |
| CodeQL | `codeql database analyze … --format=sarif-latest` | `sast` |
| osv-scanner | `osv-scanner scan -r --format sarif --output osv.sarif .` | `sca` |
| Trivy | `trivy fs --format sarif -o trivy.sarif .` / `trivy config …` | `sca` |
| Checkov | `checkov -d . -o sarif` | `sca` |
| Gitleaks | `gitleaks detect --redact --report-format sarif --report-path gitleaks.sarif` | `secrets` |
| Nuclei | `nuclei -u http://127.0.0.1:3000 -sarif-export nuclei.sarif` | `dast` |

How SARIF fields are mapped:

| SARIF | Finding |
|---|---|
| `properties.security-severity` (CVSS-like) | severity: ≥9 critical, ≥7 high, ≥4 medium, >0 low |
| `level` (fallback) | error → high, warning → medium, note → low |
| CWE in rule tags | `cwe_id` and category (e.g. CWE-89 → `sql-injection`) |
| tool name | default source/category (gitleaks → secrets / exposed-secret, osv/trivy → sca / vulnerable-dependency…) |
| `partialFingerprints` | fingerprint for de-duplication across runs |
| `region.snippet` | evidence |
| rule `help` | remediation |

Tools without SARIF output (npm audit, pip-audit, ZAP baseline JSON): the agent skills convert the relevant items with `secqa finding add --file findings.json`.

## Performance

| Tool | Produce | Ingest |
|---|---|---|
| k6 (SecQA template) | `handleSummary` writes `secqa-out/k6-summary.json` | `secqa ingest k6 secqa-out/k6-summary.json --scenario load` |
| k6 (any script) | `k6 run --summary-export=summary.json script.js` | `secqa ingest k6 summary.json` |
| JMeter | `jmeter -n -t plan.jmx -l results.jtl -Jjmeter.save.saveservice.output_format=csv` | `secqa ingest jtl results.jtl --scenario load` |

Per-endpoint rows: JMeter uses sampler labels. k6 uses `name` tags, and only reports them in the summary when a threshold references the tagged sub-metric. The SecQA template adds those thresholds automatically. In your own scripts, add `'http_req_duration{name:GET /x}': ['p(95)<500']`.

## Functional / API test results

Any JUnit XML (pytest `--junitxml`, Playwright, Newman, Schemathesis, Jest with `jest-junit`):

```bash
secqa run start --kind functional --name "API regression"
secqa ingest junit report.xml
secqa run finish
```

To link a result to a test case, put its key in the test name: `test_login_rejects_sqli [SHOP-TC-3]`.

## Exports

| Export | Endpoint | Use |
|---|---|---|
| HTML report (print → PDF) | `/api/reports/html?project=KEY&lang=en\|es[&run_id=N][&severity=…]` | Stakeholders, audits |
| Defects CSV | `/api/export/defects.csv?project=KEY` | Spreadsheets, Jira import |
| Findings SARIF | `/api/export/findings.sarif?project=KEY` | GitHub code scanning (`github/codeql-action/upload-sarif`) |
| REST API | `/api/docs` (OpenAPI) | Anything else |

## CI

See [`examples/ci/github-actions-secqa.yml`](../examples/ci/github-actions-secqa.yml): SAST and secrets on every PR, plus a load test that fails the build when the Hub detects a regression against the baseline.
