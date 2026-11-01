import { Code2, ExternalLink, FileBarChart, Gauge, Package, PlayCircle, Plus, Radar, ShieldAlert, Trash2 } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useDeleteReport, useRunReports, useToolReports, useUploadReport } from "../api/hooks";
import { TOOL_REPORT_TOOLS, type ReportTool, type ToolReport } from "../api/types";
import { fmtBytes, fmtRelative } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useToast } from "../lib/toast";
import { Card, cx, Field, Modal } from "./ui";

const TOOL_META: Record<ReportTool, { label: string; icon: ReactNode; cls: string }> = {
  k6: { label: "k6", icon: <Gauge className="h-4 w-4" />, cls: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300" },
  jmeter: { label: "JMeter", icon: <Gauge className="h-4 w-4" />, cls: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300" },
  gatling: { label: "Gatling", icon: <Gauge className="h-4 w-4" />, cls: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300" },
  locust: { label: "Locust", icon: <Gauge className="h-4 w-4" />, cls: "bg-lime-100 text-lime-700 dark:bg-lime-500/15 dark:text-lime-300" },
  zap: { label: "OWASP ZAP", icon: <ShieldAlert className="h-4 w-4" />, cls: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300" },
  nuclei: { label: "Nuclei", icon: <Radar className="h-4 w-4" />, cls: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300" },
  "osv-scanner": { label: "osv-scanner", icon: <Package className="h-4 w-4" />, cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" },
  trivy: { label: "Trivy", icon: <Package className="h-4 w-4" />, cls: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300" },
  semgrep: { label: "Semgrep", icon: <Code2 className="h-4 w-4" />, cls: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300" },
  playwright: { label: "Playwright", icon: <PlayCircle className="h-4 w-4" />, cls: "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300" },
  lighthouse: { label: "Lighthouse", icon: <Gauge className="h-4 w-4" />, cls: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300" },
  allure: { label: "Allure", icon: <FileBarChart className="h-4 w-4" />, cls: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-500/15 dark:text-fuchsia-300" },
  other: { label: "Report", icon: <FileBarChart className="h-4 w-4" />, cls: "bg-slate-100 text-slate-700 dark:bg-slate-700/40 dark:text-slate-300" },
};

export function toolMeta(tool: string) {
  return TOOL_META[(tool in TOOL_META ? tool : "other") as ReportTool];
}

export function ToolBadge({ tool }: { tool: string }) {
  const m = toolMeta(tool);
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium", m.cls)}>
      {m.icon}
      {m.label}
    </span>
  );
}

/** Plain link: the signed URL works without the API token and the report runs sandboxed in its own tab. */
export function ReportLink({ report, children, className, title }: { report: ToolReport; children: ReactNode; className?: string; title?: string }) {
  return (
    <a
      href={report.view_url}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      title={title}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      {children}
    </a>
  );
}

/** run_id → reports, from the project-wide (or global) list. */
export function useReportsByRun(project?: string) {
  const { data } = useToolReports({ project: project || undefined, limit: 500 });
  return useMemo(() => {
    const map = new Map<number, ToolReport[]>();
    for (const r of data ?? []) map.set(r.run_id, [...(map.get(r.run_id) ?? []), r]);
    return map;
  }, [data]);
}

/** Compact icon links for table rows. */
export function ReportIcons({ reports }: { reports: ToolReport[] | undefined }) {
  const { t } = usePrefs();
  if (!reports?.length) return null;
  return (
    <span className="inline-flex items-center gap-1">
      {reports.map((r) => (
        <ReportLink
          key={r.id}
          report={r}
          className={cx("inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] font-medium hover:underline", toolMeta(r.tool).cls)}
          title={`${t("tr.open")}: ${toolMeta(r.tool).label}${r.title ? ` — ${r.title}` : ""}`}
        >
          {toolMeta(r.tool).label}
          <ExternalLink className="h-3 w-3" />
        </ReportLink>
      ))}
    </span>
  );
}

function UploadReportModal({ runId, open, onClose, defaultTool }: { runId: number; open: boolean; onClose: () => void; defaultTool: ReportTool }) {
  const { t } = usePrefs();
  const toast = useToast();
  const upload = useUploadReport(runId);
  const [file, setFile] = useState<File | null>(null);
  const [tool, setTool] = useState<ReportTool>(defaultTool);
  const [title, setTitle] = useState("");
  const submit = () => {
    if (!file) return;
    upload.mutate(
      { file, tool, title: title.trim() || undefined },
      {
        onSuccess: () => {
          toast.success(t("tr.uploaded"));
          setFile(null);
          setTitle("");
          onClose();
        },
        onError: toast.error,
      },
    );
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("tr.attach")}
      footer={
        <>
          <button className="btn" onClick={onClose}>{t("c.cancel")}</button>
          <button className="btn btn-primary" disabled={!file || upload.isPending} onClick={submit}>{t("tr.upload")}</button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label={t("tr.tool")}>
          <select className="input" value={tool} onChange={(e) => setTool(e.target.value as ReportTool)}>
            {TOOL_REPORT_TOOLS.map((x) => (
              <option key={x} value={x}>{toolMeta(x).label}</option>
            ))}
          </select>
        </Field>
        <Field label={t("tr.file")}>
          <input className="input" type="file" accept=".html,.htm,.zip,text/html,application/zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        <Field label={t("tr.reportTitle")}>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} />
        </Field>
        <p className="muted text-xs">{t("tr.sandbox")}</p>
      </div>
    </Modal>
  );
}

/** Prominent card on the run page. */
export function ToolReportsCard({ runId, runKind }: { runId: number; runKind: string }) {
  const { t, lang } = usePrefs();
  const toast = useToast();
  const { data: reports } = useRunReports(runId);
  const del = useDeleteReport();
  const [open, setOpen] = useState(false);
  const list = reports ?? [];
  const defaultTool: ReportTool = runKind === "performance" ? "k6" : "zap";

  return (
    <Card
      className="mb-4"
      title={
        <span className="flex items-center gap-2">
          <FileBarChart className="h-4 w-4" /> {t("tr.title")}
          {list.length > 0 && <span className="muted text-xs font-normal">({list.length})</span>}
        </span>
      }
      actions={
        <button className="btn btn-sm" onClick={() => setOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> {t("tr.attach")}
        </button>
      }
    >
      {list.length === 0 ? (
        <p className="muted text-sm">
          {t("tr.empty")} <span className="text-xs">{t("tr.hint")}</span>
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((r) => (
            <div key={r.id} className="flex flex-col gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <div className="flex items-start justify-between gap-2">
                <ToolBadge tool={r.tool} />
                <button
                  className="btn btn-ghost btn-sm"
                  aria-label={`Delete ${r.filename}`}
                  onClick={() => {
                    if (window.confirm(t("tr.confirmDelete")))
                      del.mutate(r.id, { onSuccess: () => toast.success(t("tr.deleted")), onError: toast.error });
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium" title={r.title ?? r.filename}>{r.title ?? r.filename}</div>
                <div className="muted truncate text-xs">
                  {r.filename} · {fmtBytes(r.size)} · {r.created_by ?? "—"} · {fmtRelative(r.created_at, lang)}
                </div>
              </div>
              <ReportLink report={r} className="btn btn-primary btn-sm mt-auto justify-center">
                {t("tr.open")} <ExternalLink className="h-3.5 w-3.5" />
              </ReportLink>
            </div>
          ))}
        </div>
      )}
      {list.length > 0 && <p className="muted mt-3 text-xs">{t("tr.sandbox")}</p>}
      {open && <UploadReportModal runId={runId} open={open} onClose={() => setOpen(false)} defaultTool={defaultTool} />}
    </Card>
  );
}
