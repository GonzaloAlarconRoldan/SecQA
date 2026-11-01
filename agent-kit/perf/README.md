# SecQA performance kit

| File | Purpose |
|---|---|
| `lib/secqa.js` | k6 helpers: load profiles capped by `MAX_VUS`, per-endpoint thresholds, Hub-ready summary |
| `scenarios/endpoints.js` | Data-driven k6 test reading `perf/endpoints.json` |
| `endpoints.example.json` | Template for the endpoint list (copy to `endpoints.json`) |
| `jmeter/plan.jmx` | Headless JMeter starter plan, if your team already uses JMeter |

## k6

```bash
secqa scope check http://127.0.0.1:3000 --profile load --vus 20   # gate: exits 1 if not allowed
secqa run start --kind performance --name "Load — release 1.4" --target http://127.0.0.1:3000
mkdir -p secqa-out
k6 run -e BASE_URL=http://127.0.0.1:3000 -e PROFILE=load -e VUS=20 -e MAX_VUS=50 \
       perf/scenarios/endpoints.js
secqa ingest k6 secqa-out/k6-summary.json --scenario load
secqa run finish          # passed/failed from thresholds + baseline comparison
```

| Profile | Shape | Needs extra confirmation |
|---|---|---|
| `smoke` | 1 VU, 30 s | no |
| `load` | ramp → `VUS` for `DURATION` → down | no |
| `stress` | `VUS` then 2×`VUS` | **yes** |
| `spike` | burst to 3×`VUS` | **yes** |
| `soak` | `VUS` for a long `DURATION` (default 30 m) | **yes** |

All profiles are capped at `MAX_VUS`, which must come from `scope.yml → performance.max_vus`.

## Baselines and regressions

Mark a good run as baseline in the Hub (run page → *Set as baseline*) or with `secqa run update --baseline`.
Every later ingest compares p95, p99, avg, throughput and error rate per endpoint against it. Anything
worse than `SECQA_PERF_REGRESSION_TOLERANCE` (default 10 %) is flagged, and a `performance` defect is
opened automatically (disable with `secqa ingest … --no-defects`).

## JMeter

```bash
jmeter -n -t perf/jmeter/plan.jmx -l secqa-out/results.jtl \
  -Jhost=127.0.0.1 -Jport=3000 -Jusers=20 -Jrampup=30 -Jduration=120 \
  -Jjmeter.save.saveservice.output_format=csv
secqa ingest jtl secqa-out/results.jtl --scenario load
```

Existing `.jmx` plans work as-is: only the CSV `.jtl` output is needed (columns `timeStamp`, `elapsed`, `label`, `success`).
