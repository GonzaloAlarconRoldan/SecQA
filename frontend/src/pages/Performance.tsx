import { Star } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { usePerfScenarios, usePerfTrend } from "../api/hooks";
import { ChartBox, useChartTheme } from "../components/charts";
import { Card, cx, Empty, ErrorState, PageHeader, Pill, TableSkeleton } from "../components/ui";
import { CHART } from "../lib/colors";
import { fmtDate, fmtMs, fmtNum, fmtPct } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";

export default function PerformancePage() {
  const { t, lang } = usePrefs();
  const [project] = useProjectKey();
  const navigate = useNavigate();
  const ct = useChartTheme();
  const scenarios = usePerfScenarios(project);
  const [scenarioSel, setScenario] = useState("");
  const [name, setName] = useState("__total__");
  const names = Object.keys(scenarios.data ?? {});
  const scenario = scenarioSel && names.includes(scenarioSel) ? scenarioSel : "";
  const endpoints = scenario ? scenarios.data?.[scenario] ?? [] : [...new Set(Object.values(scenarios.data ?? {}).flat())];
  const { data, isLoading, error } = usePerfTrend({ project, scenario, name, limit: 60 });

  const points = (data ?? []).map((p) => ({
    ...p,
    label: `#${p.run_id}`,
    err: +(p.error_rate * 100).toFixed(3),
  }));
  const baseline = points.find((p) => p.is_baseline);

  return (
    <>
      <PageHeader
        title={t("pf.title")}
        subtitle={t("pf.subtitle")}
        actions={
          <>
            <select className="input w-44" aria-label={t("pf.scenario")} value={scenario} onChange={(e) => setScenario(e.target.value)}>
              <option value="">{`${t("pf.scenario")}: ${t("c.all")}`}</option>
              {names.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select className="input w-72" aria-label={t("pf.endpoint")} value={name} onChange={(e) => setName(e.target.value)}>
              {endpoints.map((n) => (
                <option key={n} value={n}>{n === "__total__" ? t("pf.total") : n}</option>
              ))}
              {!endpoints.includes("__total__") && <option value="__total__">{t("pf.total")}</option>}
            </select>
          </>
        }
      />
      {error && <ErrorState error={error} />}
      {!isLoading && points.length === 0 ? (
        <div className="card"><Empty message={t("pf.empty")} /></div>
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-3">
            <Card title={t("pf.latency")} className="xl:col-span-3">
              <ChartBox height={280}>
                <LineChart data={points} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                  <CartesianGrid stroke={ct.grid} vertical={false} />
                  <XAxis dataKey="label" tick={ct.tick} axisLine={false} tickLine={false} />
                  <YAxis tick={ct.tick} axisLine={false} tickLine={false} unit="ms" />
                  <Tooltip {...ct.tooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {baseline && <ReferenceLine x={baseline.label} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: t("rn.baseline"), fill: "#f59e0b", fontSize: 11, position: "top" }} />}
                  <Line isAnimationActive={false} type="monotone" dataKey="avg_ms" name="avg" stroke={CHART.secondary} strokeWidth={1.5} dot={false} />
                  <Line isAnimationActive={false} type="monotone" dataKey="p95_ms" name="p95" stroke={CHART.primary} strokeWidth={2.5} dot={{ r: 2.5 }} />
                  <Line isAnimationActive={false} type="monotone" dataKey="p99_ms" name="p99" stroke="#a855f7" strokeWidth={1.5} strokeDasharray="5 3" dot={false} />
                </LineChart>
              </ChartBox>
            </Card>
            <Card title={t("pf.throughput")} className="xl:col-span-2">
              <ChartBox>
                <LineChart data={points} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                  <CartesianGrid stroke={ct.grid} vertical={false} />
                  <XAxis dataKey="label" tick={ct.tick} axisLine={false} tickLine={false} />
                  <YAxis tick={ct.tick} axisLine={false} tickLine={false} />
                  <Tooltip {...ct.tooltip} />
                  {baseline && <ReferenceLine x={baseline.label} stroke="#f59e0b" strokeDasharray="4 4" />}
                  <Line isAnimationActive={false} type="monotone" dataKey="rps" name="req/s" stroke={CHART.ok} strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ChartBox>
            </Card>
            <Card title={t("pf.errorRate")}>
              <ChartBox>
                <BarChart data={points} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid stroke={ct.grid} vertical={false} />
                  <XAxis dataKey="label" tick={ct.tick} axisLine={false} tickLine={false} />
                  <YAxis tick={ct.tick} axisLine={false} tickLine={false} unit="%" />
                  <Tooltip {...ct.tooltip} />
                  <Bar isAnimationActive={false} dataKey="err" name="%" fill={CHART.danger} radius={[3, 3, 0, 0]} maxBarSize={20} />
                </BarChart>
              </ChartBox>
            </Card>
          </div>

          <Card title={t("pf.runs")} className="mt-4" bodyClass="overflow-x-auto">
            {isLoading ? (
              <TableSkeleton />
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>{t("c.run")}</th>
                    <th>{t("pf.scenario")}</th>
                    <th>{t("c.status")}</th>
                    <th className="num">p95</th>
                    <th className="num">p99</th>
                    <th className="num">avg</th>
                    <th className="num">RPS</th>
                    <th className="num">{t("ov.errorRate")}</th>
                    <th className="num">{t("rn.requests")}</th>
                    <th className="num">VUs</th>
                    <th>{t("c.started")}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...points].reverse().map((p) => (
                    <tr key={`${p.run_id}-${p.scenario}`} className="cursor-pointer" onClick={() => navigate(withProject(`/runs/${p.run_id}`, project))}>
                      <td className="whitespace-nowrap font-mono text-xs">
                        {p.is_baseline && <Star className="mr-1 inline h-3.5 w-3.5 fill-amber-400 text-amber-400" />}#{p.run_id} {p.run_name && <span className="font-sans text-slate-500">{p.run_name}</span>}
                      </td>
                      <td className="text-xs">{p.scenario}</td>
                      <td><Pill value={p.status} /></td>
                      <td className="num font-semibold">{fmtMs(p.p95_ms)}</td>
                      <td className="num">{fmtMs(p.p99_ms)}</td>
                      <td className="num">{fmtMs(p.avg_ms)}</td>
                      <td className="num">{fmtNum(p.rps, 1)}</td>
                      <td className={cx("num", p.error_rate > 0.01 && "text-red-600 dark:text-red-400")}>{fmtPct(p.error_rate, 2)}</td>
                      <td className="num">{fmtNum(p.requests)}</td>
                      <td className="num">{p.vus_max ?? "—"}</td>
                      <td className="muted whitespace-nowrap text-xs">{fmtDate(p.started_at, lang)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}
    </>
  );
}
