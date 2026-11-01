// Mirrors src/secqa/hub/schemas.py — keep in sync.

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type RunKind = "security" | "performance" | "functional" | "manual";
export type RunStatus = "running" | "passed" | "failed" | "completed" | "aborted";
export type TriageStatus = "new" | "confirmed" | "false_positive" | "accepted_risk" | "duplicate";
export type DefectKind = "bug" | "vulnerability" | "incident" | "performance";
export type DefectStatus =
  | "new" | "triaged" | "in_progress" | "fixed" | "verified" | "closed" | "wont_fix" | "duplicate";
export type Priority = "P1" | "P2" | "P3" | "P4";
export type TestType = "security" | "performance" | "functional" | "api";
export type TestCaseStatus = "draft" | "active" | "deprecated";
export type ResultStatus = "passed" | "failed" | "skipped" | "blocked" | "error";

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];
export const RUN_KINDS: RunKind[] = ["security", "performance", "functional", "manual"];
export const RUN_STATUSES: RunStatus[] = ["running", "passed", "failed", "completed", "aborted"];
export const TRIAGE_STATUSES: TriageStatus[] = ["new", "confirmed", "false_positive", "accepted_risk", "duplicate"];
export const DEFECT_KINDS: DefectKind[] = ["bug", "vulnerability", "incident", "performance"];
export const DEFECT_STATUSES: DefectStatus[] = [
  "new", "triaged", "in_progress", "fixed", "verified", "closed", "wont_fix", "duplicate",
];
export const KANBAN_COLUMNS: DefectStatus[] = ["new", "triaged", "in_progress", "fixed", "verified", "closed"];
export const PRIORITIES: Priority[] = ["P1", "P2", "P3", "P4"];
export const TEST_TYPES: TestType[] = ["security", "performance", "functional", "api"];
export const TEST_CASE_STATUSES: TestCaseStatus[] = ["draft", "active", "deprecated"];

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Meta {
  version: string;
  auth_required: boolean;
  sla_days: Record<string, number | null>;
  perf_regression_tolerance: number;
  enums: Record<string, string[]>;
  categories: Record<string, { owasp_id: string; owasp_name: string; cwe_id: string; iso_control: string; iso_control_name: string }>;
}

export interface Project {
  id: number;
  key: string;
  name: string;
  description: string | null;
  repo_url: string | null;
  created_at: string;
}

export interface ProjectSummary extends Project {
  open_defects: number;
  critical_open: number;
  last_run_at: string | null;
  run_count: number;
}

export interface PerfRegression {
  scenario: string;
  name: string;
  metric: string;
  baseline: number;
  current: number;
  change: number;
  regressed: boolean;
}

export interface Run {
  id: number;
  project_id: number;
  project_key: string | null;
  kind: RunKind;
  status: RunStatus;
  name: string | null;
  target: string | null;
  environment: string | null;
  branch: string | null;
  commit_sha: string | null;
  triggered_by: string | null;
  scope_snapshot: Record<string, unknown> | null;
  stack_detected: Record<string, unknown> | null;
  summary: Record<string, unknown> | null;
  notes: string | null;
  is_baseline: boolean;
  started_at: string;
  finished_at: string | null;
  duration_s: number | null;
  findings_by_severity: Partial<Record<Severity, number>>;
  results_by_status: Partial<Record<ResultStatus, number>>;
}

export interface Finding {
  id: number;
  run_id: number;
  project_id: number;
  source: string;
  tool: string | null;
  rule_id: string | null;
  category: string;
  title: string;
  description: string | null;
  severity: Severity;
  cvss_score: number | null;
  cvss_vector: string | null;
  cwe_id: string | null;
  owasp_id: string | null;
  iso_control: string | null;
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  endpoint: string | null;
  evidence: string | null;
  remediation: string | null;
  fingerprint: string;
  triage_status: TriageStatus;
  defect_id: number | null;
  defect_key: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
  created_at: string;
  first_seen_run_id: number | null;
}

export interface IngestResult {
  created: number;
  suppressed: number;
  linked_to_defects: number;
  skipped: number;
  detail: Record<string, unknown>;
}

export interface Defect {
  id: number;
  project_id: number;
  key: string;
  kind: DefectKind;
  title: string;
  description: string | null;
  severity: Severity;
  priority: Priority;
  status: DefectStatus;
  assignee: string | null;
  reporter: string | null;
  environment: string | null;
  steps_to_reproduce: string | null;
  expected_result: string | null;
  actual_result: string | null;
  cwe_id: string | null;
  owasp_id: string | null;
  iso_control: string | null;
  tags: string[];
  found_in_run_id: number | null;
  duplicate_of_id: number | null;
  due_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  sla_breached: boolean;
  finding_count: number;
}

export interface Comment {
  id: number;
  author: string;
  body: string;
  created_at: string;
}

export interface DefectEvent {
  id: number;
  actor: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  at: string;
}

export interface Attachment {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  created_at: string;
  url: string;
}

export interface DefectDetail extends Defect {
  comments: Comment[];
  events: DefectEvent[];
  attachments: Attachment[];
  findings: Finding[];
}

export type DefectCreate = {
  kind: DefectKind;
  title: string;
  description?: string | null;
  severity: Severity;
  priority: Priority;
  assignee?: string | null;
  environment?: string | null;
  steps_to_reproduce?: string | null;
  expected_result?: string | null;
  actual_result?: string | null;
  tags?: string[];
};

export type DefectUpdate = Partial<{
  kind: DefectKind;
  title: string;
  description: string | null;
  severity: Severity;
  priority: Priority;
  status: DefectStatus;
  assignee: string | null;
  environment: string | null;
  steps_to_reproduce: string | null;
  expected_result: string | null;
  actual_result: string | null;
  cwe_id: string | null;
  owasp_id: string | null;
  iso_control: string | null;
  tags: string[];
  duplicate_of_id: number | null;
}>;

export interface TestStep {
  action: string;
  expected: string | null;
}

export interface TestCase {
  id: number;
  project_id: number;
  key: string;
  title: string;
  type: TestType;
  suite: string | null;
  priority: Priority;
  status: TestCaseStatus;
  description: string | null;
  preconditions: string | null;
  steps: TestStep[];
  expected_result: string | null;
  automated: boolean;
  automation_ref: string | null;
  cwe_id: string | null;
  owasp_id: string | null;
  iso_control: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  last_status: ResultStatus | null;
  last_run_id: number | null;
}

export type TestCaseInput = Omit<
  TestCase,
  "id" | "project_id" | "key" | "created_at" | "updated_at" | "last_status" | "last_run_id"
>;

export interface TestResult {
  id: number;
  run_id: number;
  test_case_id: number | null;
  test_case_key: string | null;
  name: string;
  status: ResultStatus;
  duration_ms: number | null;
  message: string | null;
  created_at: string;
}

export interface PerfMetric {
  id: number;
  run_id: number;
  scenario: string;
  name: string;
  tool: string;
  requests: number;
  failures: number;
  error_rate: number;
  rps: number | null;
  avg_ms: number | null;
  min_ms: number | null;
  med_ms: number | null;
  p90_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
  vus_max: number | null;
  duration_s: number | null;
  thresholds: Record<string, boolean> | null;
}

export interface Comparison {
  baseline_run_id: number | null;
  tolerance?: number;
  comparisons: PerfRegression[];
  regressions: PerfRegression[];
}

export interface AuditEntry {
  id: number;
  project_id: number | null;
  run_id: number | null;
  actor: string;
  action: string;
  target: string | null;
  at: string;
}

export interface PerfPoint {
  run_id: number;
  run_name: string | null;
  started_at: string;
  scenario: string;
  is_baseline: boolean;
  status: RunStatus;
  p95_ms: number | null;
  p99_ms: number | null;
  avg_ms: number | null;
  rps: number | null;
  error_rate: number;
  requests: number;
  vus_max: number | null;
}

export interface Overview {
  kpis: {
    open_defects: number;
    critical_open: number;
    high_open: number;
    sla_breached: number;
    mttr_days: number | null;
    pending_triage: number;
    runs_30d: number;
    pass_rate_30d: number | null;
  };
  open_defects_by_severity: Record<Severity, number>;
  defects_by_status: Partial<Record<DefectStatus, number>>;
  open_defects_by_kind: Partial<Record<DefectKind, number>>;
  findings_by_category: { category: string; count: number }[];
  findings_by_source: Record<string, number>;
  findings_trend: ({ run_id: number; started_at: string } & Record<Severity, number>)[];
  defect_flow: { week: string; opened: number; resolved: number }[];
  perf_trend: PerfPoint[];
  recent_runs: Run[];
}

export type ComplianceState = "fail" | "warn" | "pass" | "untested";
export interface ComplianceRow {
  id: string;
  title: string;
  open_findings: number;
  open_defects: number;
  test_cases: number;
  state: ComplianceState;
}
export type Compliance = Record<string, ComplianceRow[]>;
