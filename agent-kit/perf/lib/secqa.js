// SecQA k6 helpers: load profiles, per-endpoint thresholds and a summary file the Hub can ingest.
//
// Environment variables (all optional except where noted):
//   BASE_URL   target, e.g. http://127.0.0.1:3000 (must be in scope.yml — run `secqa scope check` first)
//   PROFILE    smoke | load | stress | spike | soak          (default: smoke)
//   VUS        peak virtual users                           (default: 10)
//   DURATION   steady-state duration for load/soak          (default: 2m)
//   MAX_VUS    hard cap from scope.yml performance.max_vus  (required for anything but smoke)
//   P95_MS     latency threshold                            (default: 500)
//   ERROR_RATE max failed-request ratio                     (default: 0.01)
//   SUMMARY    output path                                  (default: secqa-out/k6-summary.json)
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

export function env(name, fallback) {
  const v = __ENV[name];
  return v === undefined || v === '' ? fallback : v;
}

export function profileStages(profile, vus, duration) {
  const maxVus = parseInt(env('MAX_VUS', profile === 'smoke' ? '1' : '0'), 10);
  if (profile !== 'smoke' && !(maxVus > 0)) {
    throw new Error('MAX_VUS is required (take it from scope.yml performance.max_vus)');
  }
  const cap = (n) => Math.max(1, Math.min(n, maxVus || n));
  switch (profile) {
    case 'smoke':
      return [{ duration: '30s', target: 1 }];
    case 'load':
      return [
        { duration: '30s', target: cap(vus) },
        { duration, target: cap(vus) },
        { duration: '30s', target: 0 },
      ];
    case 'stress':
      return [
        { duration: '1m', target: cap(vus) },
        { duration: '2m', target: cap(vus) },
        { duration: '1m', target: cap(vus * 2) },
        { duration: '2m', target: cap(vus * 2) },
        { duration: '1m', target: 0 },
      ];
    case 'spike':
      return [
        { duration: '20s', target: cap(Math.ceil(vus / 5)) },
        { duration: '10s', target: cap(vus * 3) },
        { duration: '1m', target: cap(vus * 3) },
        { duration: '10s', target: cap(Math.ceil(vus / 5)) },
        { duration: '30s', target: 0 },
      ];
    case 'soak':
      return [
        { duration: '2m', target: cap(vus) },
        { duration: env('DURATION', '30m'), target: cap(vus) },
        { duration: '1m', target: 0 },
      ];
    default:
      throw new Error(`unknown PROFILE '${profile}'`);
  }
}

// Thresholds referencing tagged sub-metrics make k6 emit per-endpoint stats in the summary,
// which the Hub turns into one row per endpoint.
export function buildThresholds(names, p95, errorRate) {
  const t = {
    http_req_duration: [`p(95)<${p95}`],
    http_req_failed: [`rate<${errorRate}`],
    checks: ['rate>0.95'],
  };
  for (const n of names) {
    t[`http_req_duration{name:${n}}`] = [`p(95)<${p95}`];
    t[`http_req_failed{name:${n}}`] = [`rate<${errorRate}`];
    t[`http_reqs{name:${n}}`] = ['count>=0'];
  }
  return t;
}

export function secqaSummary(data) {
  const out = env('SUMMARY', 'secqa-out/k6-summary.json');
  return {
    [out]: JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

export function pickWeighted(items) {
  const total = items.reduce((s, r) => s + (r.weight || 1), 0);
  let x = Math.random() * total;
  for (const r of items) {
    x -= r.weight || 1;
    if (x <= 0) return r;
  }
  return items[items.length - 1];
}
