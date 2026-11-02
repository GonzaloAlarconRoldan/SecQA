import { Bug, Camera, CheckCircle2, Search, ShieldOff, ShieldQuestion } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  useBulkTriage,
  useFindingAttachments,
  useFindings,
  useProjects,
  usePromoteFindings,
  useTriage,
  useUploadFindingAttachment,
} from "../api/hooks";
import { EvidenceGallery } from "./EvidenceGallery";
import { SEVERITIES, TRIAGE_STATUSES, type Finding, type Severity, type TriageStatus } from "../api/types";
import { fmtDate } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";
import { useToast } from "../lib/toast";
import {
  ChipToggle,
  cx,
  Drawer,
  Empty,
  EnumSelect,
  ErrorState,
  Pagination,
  Pill,
  PlainText,
  SeverityBadge,
  TableSkeleton,
} from "./ui";

const LIMIT = 50;
const SOURCES = ["recon", "sast", "sca", "secrets", "api", "dast", "perf", "manual"] as const;

export interface FindingFilters {
  severity: Severity[];
  triage_status: TriageStatus | "";
  source: string;
  category: string;
  owasp_id: string;
  iso_control: string;
  q: string;
  new_only: boolean;
  untracked: boolean;
}

export const emptyFilters: FindingFilters = {
  severity: [],
  triage_status: "",
  source: "",
  category: "",
  owasp_id: "",
  iso_control: "",
  q: "",
  new_only: false,
  untracked: false,
};

function location(f: Finding): string | null {
  if (f.endpoint) return f.endpoint;
  if (f.file_path) return f.line_start ? `${f.file_path}:${f.line_start}` : f.file_path;
  return null;
}

function FindingDrawer({ finding, onClose }: { finding: Finding | null; onClose: () => void }) {
  const { t, te, lang } = usePrefs();
  const [project] = useProjectKey();
  const toast = useToast();
  const triage = useTriage();
  const [comment, setComment] = useState("");
  // fetched only while the drawer is open (the drawer unmounts when closed)
  const evidence = useFindingAttachments(finding?.id ?? null);
  const upload = useUploadFindingAttachment(finding?.id ?? 0);

  if (!finding) return null;
  const act = (status: TriageStatus) =>
    triage.mutate(
      { id: finding.id, triage_status: status, review_comment: comment || undefined },
      {
        onSuccess: () => {
          toast.success(t("fd.triaged"));
          setComment("");
          onClose();
        },
        onError: toast.error,
      },
    );

  const row = (label: string, value: ReactNode) => (
    <div className="grid grid-cols-[140px_1fr] gap-2 py-1.5 text-sm">
      <dt className="muted">{label}</dt>
      <dd className="min-w-0 wrap-break-word">{value ?? "—"}</dd>
    </div>
  );

  return (
    <Drawer
      open
      onClose={onClose}
      title={
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <SeverityBadge severity={finding.severity} />
            <Pill value={finding.triage_status} />
            <span className="muted font-mono text-xs">#{finding.id}</span>
          </div>
          <div className="wrap-break-word text-base">{finding.title}</div>
        </div>
      }
      footer={
        <div className="w-full space-y-2">
          <textarea
            className="input"
            rows={2}
            placeholder={t("fd.comment")}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-danger" disabled={triage.isPending} onClick={() => act("confirmed")}>
              <CheckCircle2 className="h-4 w-4" /> {t("fd.confirm")}
            </button>
            <button className="btn" disabled={triage.isPending} onClick={() => act("false_positive")}>
              <ShieldOff className="h-4 w-4" /> {t("fd.falsePositive")}
            </button>
            <button className="btn" disabled={triage.isPending} onClick={() => act("accepted_risk")}>
              <ShieldQuestion className="h-4 w-4" /> {t("fd.acceptRisk")}
            </button>
          </div>
        </div>
      }
    >
      <dl className="divide-y divide-slate-100 dark:divide-slate-800">
        {row(t("c.source"), `${te(finding.source)}${finding.tool ? ` · ${finding.tool}` : ""}`)}
        {row(t("fd.rule"), finding.rule_id && <span className="code">{finding.rule_id}</span>)}
        {row(t("c.category"), <span className="font-mono text-xs">{finding.category}</span>)}
        {row(t("c.location"), location(finding) && <span className="code break-all">{location(finding)}</span>)}
        {row(
          t("df.reference"),
          [finding.owasp_id, finding.cwe_id, finding.iso_control && `ISO ${finding.iso_control}`].filter(Boolean).join(" · ") || null,
        )}
        {row(t("fd.cvss"), finding.cvss_score !== null ? `${finding.cvss_score}${finding.cvss_vector ? ` (${finding.cvss_vector})` : ""}` : null)}
        {row(
          t("c.run"),
          <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/runs/${finding.run_id}`, project)}>
            #{finding.run_id}
          </Link>,
        )}
        {row(
          t("fd.firstSeen"),
          finding.first_seen_run_id && (
            <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/runs/${finding.first_seen_run_id}`, project)}>
              #{finding.first_seen_run_id}
            </Link>
          ),
        )}
        {row(
          t("fd.linkedDefect"),
          finding.defect_id && (
            <Link className="font-mono text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/defects/${finding.defect_id}`, project)}>
              {finding.defect_key ?? `#${finding.defect_id}`}
            </Link>
          ),
        )}
        {row(t("fd.reviewedBy"), finding.reviewed_by && `${finding.reviewed_by} · ${fmtDate(finding.reviewed_at, lang)}`)}
        {row(t("fd.comment"), finding.review_comment)}
        {row(t("fd.fingerprint"), <span className="font-mono text-[11px]">{finding.fingerprint}</span>)}
      </dl>
      <h3 className="label mt-5">{t("c.description")}</h3>
      <PlainText text={finding.description} />
      <h3 className="label mt-5">{t("fd.evidence")}</h3>
      <PlainText text={finding.evidence} mono />
      <h3 className="label mt-5">
        {t("ev.title")}
        {evidence.data && evidence.data.length > 0 ? ` (${evidence.data.length})` : ""}
      </h3>
      <EvidenceGallery
        compact
        items={evidence.data ?? []}
        loading={evidence.isLoading}
        uploading={upload.isPending}
        onUpload={(u) => upload.mutateAsync(u)}
      />
      <h3 className="label mt-5">{t("fd.remediation")}</h3>
      <PlainText text={finding.remediation} />
    </Drawer>
  );
}

export function FindingsExplorer({ runId, initial }: { runId?: number; initial?: Partial<FindingFilters> }) {
  const { t } = usePrefs();
  const [project] = useProjectKey();
  const toast = useToast();
  const { data: projects } = useProjects();
  const [filters, setFilters] = useState<FindingFilters>({ ...emptyFilters, ...initial });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [openId, setOpenId] = useState<number | null>(null);
  const bulk = useBulkTriage();
  const promote = usePromoteFindings();

  const query = { project, run_id: runId, ...filters, limit: LIMIT, offset };
  const { data, isLoading, error } = useFindings(query);
  const items = useMemo(() => data?.items ?? [], [data]);
  const open = items.find((f) => f.id === openId) ?? null;

  const update = (patch: Partial<FindingFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setOffset(0);
    setSelected(new Set());
  };
  const toggle = (id: number) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const allOnPage = items.length > 0 && items.every((f) => selected.has(f.id));

  const bulkTriage = (status: TriageStatus) =>
    bulk.mutate(
      { ids: [...selected], triage_status: status },
      {
        onSuccess: (r) => {
          toast.success(`${t("fd.triaged")} (${r.updated})`);
          setSelected(new Set());
        },
        onError: toast.error,
      },
    );

  const createDefect = () => {
    const chosen = items.filter((f) => selected.has(f.id));
    const projectIds = new Set(chosen.map((f) => f.project_id));
    if (projectIds.size !== 1) return toast.error(t("fd.oneProject"));
    const key = project ?? projects?.find((p) => p.id === chosen[0].project_id)?.key;
    if (!key) return toast.error(t("c.selectProject"));
    promote.mutate(
      { project: key, finding_ids: [...selected] },
      {
        onSuccess: (d) => {
          toast.success(`${t("fd.defectCreated")}: ${d.key}`);
          setSelected(new Set());
        },
        onError: toast.error,
      },
    );
  };

  return (
    <>
      <div className="card mb-3 space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="muted pointer-events-none absolute left-2.5 top-2 h-4 w-4" />
            <input
              className="input pl-8"
              placeholder={t("c.search")}
              value={filters.q}
              onChange={(e) => update({ q: e.target.value })}
              aria-label={t("c.search")}
            />
          </div>
          <EnumSelect
            ariaLabel={t("c.status")}
            className="w-44"
            value={filters.triage_status}
            options={TRIAGE_STATUSES}
            allLabel={`${t("c.status")}: ${t("c.all")}`}
            onChange={(v) => update({ triage_status: v })}
          />
          <EnumSelect
            ariaLabel={t("c.source")}
            className="w-36"
            value={filters.source as (typeof SOURCES)[number] | ""}
            options={SOURCES}
            allLabel={`${t("c.source")}: ${t("c.all")}`}
            onChange={(v) => update({ source: v })}
          />
          <input
            className="input w-44 font-mono text-xs"
            placeholder={t("c.category")}
            value={filters.category}
            onChange={(e) => update({ category: e.target.value.trim() })}
            aria-label={t("c.category")}
          />
          {(["owasp_id", "iso_control"] as const).map((k) =>
            filters[k] ? (
              <button key={k} type="button" className="btn btn-sm" onClick={() => update({ [k]: "" })}>
                <span className="font-mono text-xs">{filters[k]}</span> ×
              </button>
            ) : null,
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <ChipToggle options={SEVERITIES} value={filters.severity} onChange={(v) => update({ severity: v })} />
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={filters.new_only} onChange={(e) => update({ new_only: e.target.checked })} />
            {t("fd.newOnly")}
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={filters.untracked} onChange={(e) => update({ untracked: e.target.checked })} />
            {t("fd.untracked")}
          </label>
          <button className="btn btn-ghost btn-sm ml-auto" onClick={() => update(emptyFilters)}>
            {t("c.clear")}
          </button>
        </div>
      </div>

      {selected.size > 0 && (
        <div className="sticky top-16 z-20 mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm shadow-xs dark:border-indigo-500/30 dark:bg-indigo-950">
          <b className="tabular-nums">{selected.size}</b> {t("c.selected")}
          <div className="ml-auto flex flex-wrap gap-2">
            <button className="btn btn-sm" disabled={bulk.isPending} onClick={() => bulkTriage("confirmed")}>
              <CheckCircle2 className="h-3.5 w-3.5" /> {t("fd.confirm")}
            </button>
            <button className="btn btn-sm" disabled={bulk.isPending} onClick={() => bulkTriage("false_positive")}>
              <ShieldOff className="h-3.5 w-3.5" /> {t("fd.falsePositive")}
            </button>
            <button className="btn btn-sm" disabled={bulk.isPending} onClick={() => bulkTriage("accepted_risk")}>
              <ShieldQuestion className="h-3.5 w-3.5" /> {t("fd.acceptRisk")}
            </button>
            <button className="btn btn-primary btn-sm" disabled={promote.isPending} onClick={createDefect}>
              <Bug className="h-3.5 w-3.5" /> {t("fd.createDefect")}
            </button>
          </div>
        </div>
      )}

      {error && <ErrorState error={error} />}
      <div className="card overflow-x-auto">
        {isLoading ? (
          <TableSkeleton />
        ) : items.length === 0 ? (
          <Empty message={t("fd.empty")} />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th className="w-8">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={allOnPage}
                    onChange={() => setSelected(allOnPage ? new Set() : new Set(items.map((f) => f.id)))}
                  />
                </th>
                <th>{t("c.severity")}</th>
                <th>{t("c.title")}</th>
                <th>{t("c.location")}</th>
                <th>{t("c.source")}</th>
                <th>{t("c.status")}</th>
                <th>{t("fd.linkedDefect")}</th>
                {!runId && <th>{t("c.run")}</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((f) => (
                <tr key={f.id} className={cx("cursor-pointer", selected.has(f.id) && "bg-indigo-50/60 dark:bg-indigo-500/10")}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" aria-label={`Select ${f.id}`} checked={selected.has(f.id)} onChange={() => toggle(f.id)} />
                  </td>
                  <td onClick={() => setOpenId(f.id)}>
                    <SeverityBadge severity={f.severity} />
                  </td>
                  <td className="max-w-[420px]" onClick={() => setOpenId(f.id)}>
                    <button className="flex w-full items-center gap-1.5 text-left font-medium hover:underline" onClick={() => setOpenId(f.id)}>
                      {f.description?.includes("CISA KEV") && (
                        <span className="pill shrink-0 bg-red-600 px-1.5 text-[10px] text-white no-underline" title={t("fd.kevBadge")}>
                          KEV
                        </span>
                      )}
                      <span className="truncate">{f.title}</span>
                    </button>
                    <div className="muted flex gap-2 text-xs">
                      <span className="font-mono">{f.category}</span>
                      {f.attachment_count > 0 && (
                        <span className="inline-flex items-center gap-0.5" title={t("ev.count").replace("{n}", String(f.attachment_count))}>
                          <Camera className="h-3.5 w-3.5" aria-hidden />
                          {f.attachment_count}
                        </span>
                      )}
                      {f.first_seen_run_id === f.run_id && (
                        <span className="pill bg-sky-100 py-0 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300">{t("fd.newBadge")}</span>
                      )}
                    </div>
                  </td>
                  <td className="max-w-[260px] truncate font-mono text-xs" onClick={() => setOpenId(f.id)} title={location(f) ?? ""}>
                    {location(f) ?? "—"}
                  </td>
                  <td className="text-xs" onClick={() => setOpenId(f.id)}>
                    {f.source}
                    {f.tool && <span className="muted"> · {f.tool}</span>}
                  </td>
                  <td onClick={() => setOpenId(f.id)}>
                    <Pill value={f.triage_status} />
                  </td>
                  <td className="font-mono text-xs">
                    {f.defect_id ? (
                      <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/defects/${f.defect_id}`, project)}>
                        {f.defect_key ?? `#${f.defect_id}`}
                      </Link>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  {!runId && (
                    <td className="font-mono text-xs">
                      <Link className="hover:underline" to={withProject(`/runs/${f.run_id}`, project)}>
                        #{f.run_id}
                      </Link>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data && <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
      <FindingDrawer finding={open} onClose={() => setOpenId(null)} />
    </>
  );
}
