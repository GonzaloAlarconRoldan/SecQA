import { Download, ExternalLink, FileBarChart, FileSpreadsheet, FileText, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useState } from "react";
import { download, openHtml } from "../api/client";
import { useProjects, useRuns, useToolReports } from "../api/hooks";
import { SEVERITIES, TOOL_REPORT_TOOLS, type Severity } from "../api/types";
import { ReportLink, ToolBadge, toolMeta } from "../components/ToolReports";
import { Card, ChipToggle, Empty, Field, PageHeader, TableSkeleton } from "../components/ui";
import { fmtBytes, fmtRelative } from "../lib/format";
import type { Lang } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";
import { useToast } from "../lib/toast";

export default function ReportsPage() {
  const { t, lang: uiLang } = usePrefs();
  const toast = useToast();
  const [selected] = useProjectKey();
  const { data: projects } = useProjects();
  const [projectSel, setProject] = useState<string>("");
  const project = projectSel || selected || "";
  const { data: runs } = useRuns({ project: project || undefined, limit: 50 });
  const [runId, setRunId] = useState<string>("");
  const [severity, setSeverity] = useState<Severity[]>([]);
  const [lang, setLang] = useState<Lang>(uiLang);
  const [includeClosed, setIncludeClosed] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title={t("rp.title")} subtitle={t("rp.subtitle")} />
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <Card title={<span className="flex items-center gap-2"><FileText className="h-4 w-4" /> {t("rp.htmlReport")}</span>}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("c.project")}>
              <select className="input" value={project} onChange={(e) => { setProject(e.target.value); setRunId(""); }}>
                <option value="">—</option>
                {projects?.map((p) => (
                  <option key={p.key} value={p.key}>{p.key} — {p.name}</option>
                ))}
              </select>
            </Field>
            <Field label={t("rp.runOptional")}>
              <select className="input" value={runId} onChange={(e) => setRunId(e.target.value)} disabled={!project}>
                <option value="">{t("rp.allRuns")}</option>
                {runs?.items.map((r) => (
                  <option key={r.id} value={r.id}>#{r.id} · {r.kind} · {r.name || r.target || r.started_at.slice(0, 10)}</option>
                ))}
              </select>
            </Field>
            <Field label={t("c.severity")} className="sm:col-span-2">
              <ChipToggle options={SEVERITIES} value={severity} onChange={setSeverity} />
            </Field>
            <Field label={t("rp.language")}>
              <select className="input" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                <option value="en">English</option>
                <option value="es">Español</option>
              </select>
            </Field>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input type="checkbox" checked={includeClosed} onChange={(e) => setIncludeClosed(e.target.checked)} /> {t("rp.includeClosed")}
            </label>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              className="btn btn-primary"
              disabled={!project || busy}
              onClick={() => run(() => openHtml("/reports/html", { project, run_id: runId || undefined, severity, lang, include_closed: includeClosed }))}
            >
              <FileText className="h-4 w-4" /> {t("rp.generate")}
            </button>
            <span className="muted text-xs">{t("rp.htmlHint")}</span>
          </div>
        </Card>

        <Card title={t("rp.exports")}>
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <FileSpreadsheet className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" />
              <div className="flex-1">
                <div className="text-sm font-medium">{t("rp.csv")}</div>
                <div className="muted text-xs">{t("rp.csvHint")}</div>
              </div>
              <button className="btn btn-sm" disabled={!project || busy} onClick={() => run(() => download("/export/defects.csv", { project }, `${project}-defects.csv`))}>
                <Download className="h-3.5 w-3.5" /> {t("rp.download")}
              </button>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-indigo-500" />
              <div className="flex-1">
                <div className="text-sm font-medium">{t("rp.sarif")}</div>
                <div className="muted text-xs">{t("rp.sarifHint")}</div>
              </div>
              <button
                className="btn btn-sm"
                disabled={!project || busy}
                onClick={() => run(() => download("/export/findings.sarif", { project, run_id: runId || undefined }, `${project}-findings.sarif`))}
              >
                <Download className="h-3.5 w-3.5" /> {t("rp.download")}
              </button>
            </div>
            {!project && <p className="text-xs text-amber-600">{t("c.selectProject")}</p>}
          </div>
        </Card>
      </div>
      <ToolReportsSection project={project || undefined} />
    </>
  );
}

function ToolReportsSection({ project }: { project?: string }) {
  const { t, lang } = usePrefs();
  const [tool, setTool] = useState("");
  const { data, isLoading } = useToolReports({ project, tool: tool || undefined, limit: 100 });
  return (
    <Card
      className="mt-4"
      bodyClass="overflow-x-auto"
      title={<span className="flex items-center gap-2"><FileBarChart className="h-4 w-4" /> {t("tr.title")}</span>}
      actions={
        <select className="input h-8 w-44 py-1 text-sm" value={tool} onChange={(e) => setTool(e.target.value)} aria-label={t("tr.tool")}>
          <option value="">{t("tr.allTools")}</option>
          {TOOL_REPORT_TOOLS.map((x) => (
            <option key={x} value={x}>{toolMeta(x).label}</option>
          ))}
        </select>
      }
    >
      <p className="muted px-4 pb-2 pt-3 text-xs">{t("tr.subtitle")}</p>
      {isLoading ? (
        <TableSkeleton rows={4} />
      ) : !data?.length ? (
        <Empty message={t("tr.empty")}>
          <p className="muted text-xs">{t("tr.hint")}</p>
        </Empty>
      ) : (
        <table className="tbl">
          <thead>
            <tr>
              <th>{t("tr.tool")}</th>
              <th>{t("c.title")}</th>
              <th>{t("tr.run")}</th>
              {!project && <th>{t("c.project")}</th>}
              <th className="num">{t("tr.size")}</th>
              <th>{t("c.started")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.id}>
                <td><ToolBadge tool={r.tool} /></td>
                <td className="max-w-[320px] truncate" title={r.title ?? r.filename}>{r.title ?? r.filename}</td>
                <td className="whitespace-nowrap text-xs">
                  <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/runs/${r.run_id}`, r.project_key)}>
                    #{r.run_id}
                  </Link>{" "}
                  <span className="muted">{r.run_name ?? r.run_kind}</span>
                </td>
                {!project && <td className="font-mono text-xs">{r.project_key}</td>}
                <td className="num text-xs">{fmtBytes(r.size)}</td>
                <td className="muted whitespace-nowrap text-xs">{fmtRelative(r.created_at, lang)}</td>
                <td className="text-right">
                  <ReportLink report={r} className="btn btn-sm">
                    {t("tr.open")} <ExternalLink className="h-3.5 w-3.5" />
                  </ReportLink>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted px-4 py-3 text-xs">{t("tr.sandbox")}</p>
    </Card>
  );
}
