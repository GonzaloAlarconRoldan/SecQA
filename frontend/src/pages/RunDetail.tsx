import { ArrowLeft, Check, Star, X as XIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useAudit, useRun, useRunCompare, useRunPerf, useRunResults, useUpdateRun } from "../api/hooks";
import type { IntelSummary, Run, StackDetected } from "../api/types";
import { FindingsExplorer } from "../components/FindingsExplorer";
import { IntelTab, StackCard } from "../components/RunIntel";
import { ToolReportsCard } from "../components/ToolReports";
import { Card, cx, Empty, ErrorState, Pill, PlainText, SeverityBar, Skeleton, TableSkeleton, Tabs } from "../components/ui";
import { fmtDate, fmtDuration, fmtMs, fmtNum, fmtPct } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";
import { useToast } from "../lib/toast";

type Tab = "findings" | "intel" | "results" | "perf" | "audit";

function ResultsTab({ runId }: { runId: number }) {
  const { t } = usePrefs();
  const [project] = useProjectKey();
  const { data, isLoading, error } = useRunResults(runId);
  if (error) return <ErrorState error={error} />;
  if (isLoading) return <TableSkeleton />;
  if (!data?.length) return <Empty message={t("rn.noResults")} />;
  return (
    <div className="card overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>{t("c.status")}</th>
            <th>{t("c.name")}</th>
            <th>{t("rn.testCase")}</th>
            <th className="num">{t("c.duration")}</th>
            <th>{t("rn.message")}</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.id}>
              <td>
                <Pill value={r.status} />
              </td>
              <td className="max-w-[360px] wrap-break-word font-mono text-xs">{r.name}</td>
              <td className="font-mono text-xs">
                {r.test_case_key ? (
                  <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={withProject("/testcases", project, { q: r.test_case_key })}>
                    {r.test_case_key}
                  </Link>
                ) : (
                  "—"
                )}
              </td>
              <td className="num text-xs">{fmtMs(r.duration_ms)}</td>
              <td className="max-w-[420px] truncate text-xs" title={r.message ?? ""}>
                {r.message ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PerfTab({ run }: { run: Run }) {
  const { t, te } = usePrefs();
  const [project] = useProjectKey();
  const { data, isLoading, error } = useRunPerf(run.id);
  const cmp = useRunCompare(run.id, run.kind === "performance");
  if (error) return <ErrorState error={error} />;
  if (isLoading) return <TableSkeleton />;
  if (!data?.length) return <Empty message={t("rn.noPerf")} />;
  const total = data.find((m) => m.name === "__total__");
  const thresholds = Object.entries(total?.thresholds ?? {});

  return (
    <div className="space-y-4">
      <div className="card overflow-x-auto">
        <table className="tbl">
          <thead>
            <tr>
              <th>{t("pf.scenario")}</th>
              <th>{t("rn.endpoint")}</th>
              <th className="num">{t("rn.requests")}</th>
              <th className="num">RPS</th>
              <th className="num">avg</th>
              <th className="num">p90</th>
              <th className="num">p95</th>
              <th className="num">p99</th>
              <th className="num">max</th>
              <th className="num">{t("ov.errorRate")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((m) => (
              <tr key={m.id} className={m.name === "__total__" ? "font-semibold" : ""}>
                <td className="text-xs">{m.scenario}</td>
                <td className="max-w-[280px] truncate font-mono text-xs">{m.name === "__total__" ? t("pf.total") : m.name}</td>
                <td className="num">{fmtNum(m.requests)}</td>
                <td className="num">{fmtNum(m.rps, 1)}</td>
                <td className="num">{fmtMs(m.avg_ms)}</td>
                <td className="num">{fmtMs(m.p90_ms)}</td>
                <td className="num">{fmtMs(m.p95_ms)}</td>
                <td className="num">{fmtMs(m.p99_ms)}</td>
                <td className="num">{fmtMs(m.max_ms)}</td>
                <td className={cx("num", m.error_rate > 0.01 && "text-red-600 dark:text-red-400")}>{fmtPct(m.error_rate, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {thresholds.length > 0 && (
        <Card title={t("rn.thresholds")}>
          <ul className="grid gap-1 sm:grid-cols-2">
            {thresholds.map(([expr, ok]) => (
              <li key={expr} className="flex items-center gap-2 font-mono text-xs">
                {ok ? <Check className="h-4 w-4 text-emerald-500" /> : <XIcon className="h-4 w-4 text-red-500" />}
                {expr}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card
        title={t("rn.comparison")}
        actions={
          cmp.data?.baseline_run_id ? (
            <Link className="text-xs font-normal text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/runs/${cmp.data.baseline_run_id}`, project)}>
              {t("rn.baseline")} #{cmp.data.baseline_run_id}
            </Link>
          ) : undefined
        }
        bodyClass="overflow-x-auto"
      >
        {cmp.isLoading ? (
          <div className="p-4">
            <Skeleton />
          </div>
        ) : !cmp.data?.baseline_run_id ? (
          <p className="muted p-4 text-sm">{t("rn.noBaseline")}</p>
        ) : cmp.data.comparisons.length === 0 ? (
          <Empty />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("rn.endpoint")}</th>
                <th>{t("rn.metric")}</th>
                <th className="num">{t("rn.baseline")}</th>
                <th className="num">{t("rn.current")}</th>
                <th className="num">{t("rn.change")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {cmp.data.comparisons.map((c) => {
                const pct = c.metric === "error_rate";
                return (
                  <tr key={`${c.scenario}|${c.name}|${c.metric}`} className={c.regressed ? "bg-red-50 dark:bg-red-500/10" : ""}>
                    <td className="max-w-[260px] truncate font-mono text-xs">{c.name === "__total__" ? t("pf.total") : c.name}</td>
                    <td className="font-mono text-xs">{c.metric}</td>
                    <td className="num">{pct ? fmtPct(c.baseline, 2) : fmtNum(c.baseline, 1)}</td>
                    <td className="num">{pct ? fmtPct(c.current, 2) : fmtNum(c.current, 1)}</td>
                    <td className={cx("num", c.regressed && "font-semibold text-red-600 dark:text-red-400")}>
                      {pct ? `${(c.change * 100).toFixed(2)} pp` : `${c.change > 0 ? "+" : ""}${(c.change * 100).toFixed(1)}%`}
                    </td>
                    <td>{c.regressed && <Pill value="failed" />}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
      <p className="muted text-xs">
        {te(run.kind)} · {cmp.data?.regressions.length ?? 0} {t("rn.regressions")}
      </p>
    </div>
  );
}

function AuditTab({ run }: { run: Run }) {
  const { t, lang } = usePrefs();
  const { data, isLoading, error } = useAudit(run.project_key, run.id);
  if (error) return <ErrorState error={error} />;
  if (isLoading) return <TableSkeleton />;
  if (!data?.length) return <Empty message={t("rn.noAudit")} />;
  return (
    <div className="card overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>{t("rn.at")}</th>
            <th>{t("rn.actor")}</th>
            <th>{t("rn.action")}</th>
            <th>{t("c.target")}</th>
          </tr>
        </thead>
        <tbody>
          {data.map((a) => (
            <tr key={a.id}>
              <td className="muted whitespace-nowrap text-xs">{fmtDate(a.at, lang)}</td>
              <td className="font-mono text-xs">{a.actor}</td>
              <td className="text-sm">{a.action}</td>
              <td className="max-w-[300px] truncate font-mono text-xs">{a.target ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RunDetailPage() {
  const { t, lang } = usePrefs();
  const toast = useToast();
  const [project] = useProjectKey();
  const id = Number(useParams().id);
  const { data: run, isLoading, error } = useRun(id);
  const updateRun = useUpdateRun();
  const [tab, setTab] = useState<Tab | null>(null);

  if (error) return <ErrorState error={error} />;
  if (isLoading || !run)
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-28" />
      </div>
    );

  const active: Tab = tab ?? (run.kind === "performance" ? "perf" : run.kind === "functional" ? "results" : "findings");
  const meta: [string, ReactNode][] = [
    [t("c.target"), run.target ? <span className="code break-all">{run.target}</span> : "—"],
    [t("c.environment"), run.environment ?? "—"],
    [t("c.branch"), run.branch ?? "—"],
    [t("c.commit"), run.commit_sha ? <span className="code">{run.commit_sha.slice(0, 12)}</span> : "—"],
    [t("rn.triggeredBy"), run.triggered_by ?? "—"],
    [t("c.started"), fmtDate(run.started_at, lang)],
    [t("c.duration"), fmtDuration(run.duration_s)],
  ];
  const stack = run.stack_detected as StackDetected | null;
  const intel = (run.summary?.intel ?? null) as IntelSummary | null;

  return (
    <>
      <Link to={withProject("/runs", project)} className="muted mb-3 inline-flex items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="h-4 w-4" /> {t("rn.title")}
      </Link>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-slate-500">
              {run.project_key} · #{run.id}
            </span>
            <Pill value={run.kind} />
            <Pill value={run.status} />
            {run.is_baseline && (
              <span className="pill bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
                <Star className="h-3 w-3 fill-current" /> {t("rn.baseline")}
              </span>
            )}
          </div>
          <h1 className="page-title">{run.name || run.target || `Run #${run.id}`}</h1>
        </div>
        {run.kind === "performance" && (
          <button
            className="btn"
            disabled={updateRun.isPending}
            onClick={() =>
              updateRun.mutate(
                { id: run.id, is_baseline: !run.is_baseline },
                { onSuccess: () => toast.success(t("c.saved")), onError: toast.error },
              )
            }
          >
            <Star className={cx("h-4 w-4", run.is_baseline && "fill-amber-400 text-amber-400")} />
            {run.is_baseline ? t("rn.unsetBaseline") : t("rn.setBaseline")}
          </button>
        )}
      </div>

      <div className="card mb-5 grid gap-x-6 gap-y-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        {meta.map(([label, value]) => (
          <div key={label}>
            <div className="label">{label}</div>
            <div className="text-sm">{value}</div>
          </div>
        ))}
        <div>
          <div className="label">{t("rn.findings")}</div>
          <SeverityBar counts={run.findings_by_severity} />
        </div>
        {run.notes && (
          <div className="sm:col-span-2 lg:col-span-4">
            <div className="label">{t("rn.notes")}</div>
            <PlainText text={run.notes} />
          </div>
        )}
      </div>

      <ToolReportsCard runId={run.id} runKind={run.kind} />
      {stack && <StackCard stack={stack} />}

      <Tabs<Tab>
        value={active}
        onChange={setTab}
        tabs={[
          { id: "findings", label: t("rn.findings") },
          ...(intel ? [{ id: "intel" as const, label: `${t("rn.intel")}${intel.stats?.kev ? ` · ${intel.stats.kev} KEV` : ""}` }] : []),
          { id: "results", label: `${t("rn.results")} (${Object.values(run.results_by_status).reduce((a, b) => a + (b ?? 0), 0)})` },
          { id: "perf", label: t("rn.perf") },
          { id: "audit", label: t("rn.audit") },
        ]}
      />
      {active === "findings" && <FindingsExplorer runId={run.id} />}
      {active === "intel" && intel && <IntelTab intel={intel} projectKey={run.project_key} />}
      {active === "results" && <ResultsTab runId={run.id} />}
      {active === "perf" && <PerfTab run={run} />}
      {active === "audit" && <AuditTab run={run} />}
    </>
  );
}
