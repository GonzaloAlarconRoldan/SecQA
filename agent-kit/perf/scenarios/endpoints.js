// Data-driven HTTP load test. Endpoints come from perf/endpoints.json (the perf-test skill
// generates it from recon's perf_candidates); thresholds and profile come from env vars.
//
//   k6 run -e BASE_URL=http://127.0.0.1:3000 -e PROFILE=load -e VUS=20 -e MAX_VUS=50 perf/scenarios/endpoints.js
//   secqa ingest k6 secqa-out/k6-summary.json --scenario load
import http from 'k6/http';
import { check, sleep } from 'k6';
import { buildThresholds, env, pickWeighted, profileStages, secqaSummary } from '../lib/secqa.js';

const config = JSON.parse(open(env('ENDPOINTS', '../endpoints.json')));
const BASE_URL = env('BASE_URL', config.base_url);
const PROFILE = env('PROFILE', 'smoke');
const VUS = parseInt(env('VUS', '10'), 10);
const P95 = parseFloat(env('P95_MS', String(config.thresholds?.p95_ms ?? 500)));
const ERR = parseFloat(env('ERROR_RATE', String(config.thresholds?.error_rate ?? 0.01)));

if (!BASE_URL) throw new Error('BASE_URL is required');

export const options = {
  scenarios: {
    [PROFILE]: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: profileStages(PROFILE, VUS, env('DURATION', '2m')),
      gracefulRampDown: '10s',
    },
  },
  thresholds: buildThresholds(config.requests.map((r) => r.name), P95, ERR),
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  userAgent: 'SecQA-k6/2.0',
  // Never follow redirects off the scoped host.
  maxRedirects: 0,
};

export function setup() {
  // Optional login step: if config.auth is set, obtain a token once and share it with all VUs.
  if (!config.auth) return {};
  const a = config.auth;
  const res = http.post(`${BASE_URL}${a.path}`, JSON.stringify(a.body), {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'setup: auth' },
  });
  const token = a.token_json_path
    ? a.token_json_path.split('.').reduce((o, k) => (o ? o[k] : undefined), res.json())
    : undefined;
  if (!token) throw new Error(`auth failed (${res.status}) — check perf/endpoints.json auth block`);
  return { token };
}

export default function (data) {
  const r = pickWeighted(config.requests);
  const headers = Object.assign({ 'Content-Type': 'application/json' }, r.headers || {});
  if (data.token) headers.Authorization = `Bearer ${data.token}`;
  const body = r.body === undefined ? null : JSON.stringify(r.body);
  const res = http.request(r.method || 'GET', `${BASE_URL}${r.path}`, body, {
    headers,
    tags: { name: r.name },
  });
  check(res, { [`${r.name} → ${r.expect_status || 200}`]: (x) => x.status === (r.expect_status || 200) });
  sleep(parseFloat(env('THINK_TIME', '1')));
}

export function handleSummary(data) {
  return secqaSummary(data);
}
