import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useOverview } from "../api/hooks";
import { SEVERITIES } from "../api/types";
import { ChartBox, useChartTheme } from "../components/charts";
import { RunsTable } from "../components/RunsTable";
import { Card, ErrorState, Kpi, PageHeader, Skeleton } from "../components/ui";
import { CHART, SEVERITY_HEX } from "../lib/colors";
import { fmtPct, shortDate } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";

export default function OverviewPage() {
  const { t, te } = usePrefs();
  const [project] = useProjectKey();
  const { data, isLoading, error } = useOverview(project);
  const ct = useChartTheme();

  if (error) return <ErrorState error={error} />;

  const k = data?.kpis;
  const sevData = SEVERITIES.filter((s) => s !== "info").map((s) => ({
    name: te(s),
    sev: s,
    value: data?.open_defects_by_severity[s] ?? 0,
  }));
  const trend = (data?.findings_trend ?? []).map((r) => ({ ...r, label: `#${r.run_id}` }));
  const perf = (data?.perf_trend ?? []).map((p) => ({
    label: `#${p.run_id}`,
    date: shortDate(p.started_at),
    p95: p.p95_ms,
    err: +(p.error_rate * 100).toFixed(2),
  }));
  const maxCat = Math.max(1, ...(data?.findings_by_category ?? []).map((c) => c.count));

  return (
    <>
      <PageHeader title={t("ov.title")} subtitle={t("ov.subtitle")} />

      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        {isLoading || !k ? (
          Array.from({ length: 7 }, (_, i) => <Skeleton key={i} className="h-[74px]" />)
        ) : (
          <>
            <Kpi label={t("ov.openDefects")} value={k.open_defects} />
            <Kpi label={t("ov.criticalOpen")} value={k.critical_open} tone={k.critical_open ? "danger" : "ok"} />
            <Kpi label={t("ov.slaBreached")} value={k.sla_breached} tone={k.sla_breached ? "danger" : "ok"} />
            <Kpi label={t("ov.mttr")} value={k.mttr_days ?? "—"} hint={k.mttr_days !== null ? t("ov.days") : undefined} />
            <Kpi
              label={t("ov.pendingTriage")}
              value={<Link to={withProject("/findings", project, { triage_status: "new" })} className="hover:underline">{k.pending_triage}</Link>}
              tone={k.pending_triage ? "warn" : undefined}
            />
            <Kpi label={t("ov.runs30d")} value={k.runs_30d} />
            <Kpi
              label={t("ov.passRate")}
              value={fmtPct(k.pass_rate_30d)}
              tone={k.pass_rate_30d === null ? undefined : k.pass_rate_30d >= 0.95 ? "ok" : k.pass_rate_30d >= 0.8 ? "warn" : "danger"}
            />
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t("ov.bySeverity")}>
          <ChartBox empty={!isLoading && sevData.every((d) => !d.value)}>
            <BarChart data={sevData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis dataKey="name" tick={ct.tick} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={ct.tick} axisLine={false} tickLine={false} />
              <Tooltip {...ct.tooltip} />
              <Bar isAnimationActive={false} dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={56}>
                {sevData.map((d) => (
                  <Cell key={d.sev} fill={SEVERITY_HEX[d.sev]} />
                ))}
              </Bar>
            </BarChart>
          </ChartBox>
        </Card>

        <Card title={t("ov.findingsTrend")}>
          <ChartBox empty={!isLoading && trend.length === 0}>
            <AreaChart data={trend} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis dataKey="label" tick={ct.tick} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={ct.tick} axisLine={false} tickLine={false} />
              <Tooltip {...ct.tooltip} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {(["low", "medium", "high", "critical"] as const).map((s) => (
                <Area
                  key={s}
                  type="monotone"
                  dataKey={s}
                  name={te(s)}
                  stackId="1"
                  stroke={SEVERITY_HEX[s]}
                  fill={SEVERITY_HEX[s]}
                  fillOpacity={0.55}
                />
              ))}
            </AreaChart>
          </ChartBox>
        </Card>

        <Card title={t("ov.defectFlow")}>
          <ChartBox empty={!isLoading && (data?.defect_flow ?? []).every((w) => !w.opened && !w.resolved)}>
            <BarChart data={data?.defect_flow ?? []} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis dataKey="week" tick={ct.tick} axisLine={false} tickLine={false} tickFormatter={(w: string) => w.slice(5)} />
              <YAxis allowDecimals={false} tick={ct.tick} axisLine={false} tickLine={false} />
              <Tooltip {...ct.tooltip} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar isAnimationActive={false} dataKey="opened" name={t("ov.opened")} fill={CHART.danger} radius={[3, 3, 0, 0]} maxBarSize={18} />
              <Bar isAnimationActive={false} dataKey="resolved" name={t("ov.resolved")} fill={CHART.ok} radius={[3, 3, 0, 0]} maxBarSize={18} />
            </BarChart>
          </ChartBox>
        </Card>

        <Card title={t("ov.perfTrend")}>
          <ChartBox empty={!isLoading && perf.length === 0}>
            <ComposedChart data={perf} margin={{ top: 8, right: 0, left: -12, bottom: 0 }}>
              <CartesianGrid stroke={ct.grid} vertical={false} />
              <XAxis dataKey="label" tick={ct.tick} axisLine={false} tickLine={false} />
              <YAxis yAxisId="ms" tick={ct.tick} axisLine={false} tickLine={false} unit="ms" />
              <YAxis yAxisId="err" orientation="right" tick={ct.tick} axisLine={false} tickLine={false} unit="%" />
              <Tooltip {...ct.tooltip} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar isAnimationActive={false} yAxisId="err" dataKey="err" name={t("ov.errorRate")} fill={CHART.danger} fillOpacity={0.35} maxBarSize={14} />
              <Line isAnimationActive={false} yAxisId="ms" type="monotone" dataKey="p95" name="p95" stroke={CHART.primary} strokeWidth={2} dot={{ r: 2 }} />
            </ComposedChart>
          </ChartBox>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title={t("ov.topCategories")}>
          {(data?.findings_by_category ?? []).length === 0 ? (
            <p className="muted py-6 text-center text-sm">{t("ov.noData")}</p>
          ) : (
            <ul className="space-y-2">
              {data?.findings_by_category.map((c) => (
                <li key={c.category}>
                  <Link to={withProject("/findings", project, { category: c.category })} className="group block">
                    <div className="mb-0.5 flex justify-between text-xs">
                      <span className="font-mono group-hover:underline">{c.category}</span>
                      <span className="tabular-nums">{c.count}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800">
                      <div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${(c.count / maxCat) * 100}%` }} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title={t("ov.recentRuns")} className="lg:col-span-2" bodyClass="overflow-x-auto">
          <RunsTable runs={data?.recent_runs ?? []} loading={isLoading} compact />
        </Card>
      </div>
    </>
  );
}
