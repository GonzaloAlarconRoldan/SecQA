import type { Severity } from "../api/types";

export const SEVERITY_HEX: Record<Severity, string> = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#d97706",
  low: "#2563eb",
  info: "#64748b",
};

export const SEVERITY_CLASS: Record<Severity, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-orange-500 text-white",
  medium: "bg-amber-400 text-amber-950",
  low: "bg-blue-600 text-white",
  info: "bg-slate-400 text-white dark:bg-slate-600",
};

const tone = {
  green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  red: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  blue: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  violet: "bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-300",
  indigo: "bg-indigo-100 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300",
  slate: "bg-slate-100 text-slate-700 dark:bg-slate-700/40 dark:text-slate-300",
  cyan: "bg-cyan-100 text-cyan-800 dark:bg-cyan-500/15 dark:text-cyan-300",
};
export type Tone = keyof typeof tone;
export const toneClass = (t: Tone) => tone[t];

export const STATUS_TONE: Record<string, Tone> = {
  // runs
  running: "blue", passed: "green", failed: "red", completed: "slate", aborted: "amber",
  // triage
  new: "blue", confirmed: "red", false_positive: "slate", accepted_risk: "amber", duplicate: "slate",
  // defects
  triaged: "violet", in_progress: "indigo", fixed: "cyan", verified: "green", closed: "slate", wont_fix: "slate",
  // test cases / results
  draft: "slate", active: "green", deprecated: "slate", skipped: "slate", blocked: "amber", error: "red",
  // compliance
  fail: "red", warn: "amber", pass: "green", untested: "slate",
  // kinds
  security: "violet", performance: "cyan", functional: "blue", manual: "slate", api: "indigo",
  bug: "blue", vulnerability: "red", incident: "amber",
};

export const PRIORITY_TONE: Record<string, Tone> = { P1: "red", P2: "amber", P3: "blue", P4: "slate" };

export const CHART = {
  grid: { light: "#e2e8f0", dark: "#1e293b" },
  axis: { light: "#64748b", dark: "#94a3b8" },
  primary: "#6366f1",
  secondary: "#14b8a6",
  danger: "#ef4444",
  ok: "#10b981",
};
