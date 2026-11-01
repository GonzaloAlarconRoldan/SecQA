import { AlertTriangle, Columns3, List, Plus, Search } from "lucide-react";
import { useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCreateDefect, useDefects, useUpdateDefect } from "../api/hooks";
import {
  DEFECT_KINDS,
  DEFECT_STATUSES,
  KANBAN_COLUMNS,
  PRIORITIES,
  SEVERITIES,
  type Defect,
  type DefectCreate,
  type DefectKind,
  type DefectStatus,
  type Priority,
  type Severity,
} from "../api/types";
import {
  ChipToggle,
  cx,
  Empty,
  EnumSelect,
  ErrorState,
  Field,
  Modal,
  PageHeader,
  Pagination,
  Pill,
  PriorityPill,
  SeverityBadge,
  TableSkeleton,
} from "../components/ui";
import { SEVERITY_HEX } from "../lib/colors";
import { fmtDate, fmtRelative } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";
import { storage } from "../lib/storage";
import { useToast } from "../lib/toast";

const LIMIT = 50;

function SlaBadge({ d }: { d: Defect }) {
  const { t, lang } = usePrefs();
  if (!d.due_at) return <span className="muted">—</span>;
  return d.sla_breached ? (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-600 dark:text-red-400" title={fmtDate(d.due_at, lang)}>
      <AlertTriangle className="h-3.5 w-3.5" /> {t("df.breached")}
    </span>
  ) : (
    <span className="muted text-xs" title={fmtDate(d.due_at, lang)}>
      {fmtRelative(d.due_at, lang)}
    </span>
  );
}

export function NewDefectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = usePrefs();
  const [project] = useProjectKey();
  const toast = useToast();
  const navigate = useNavigate();
  const create = useCreateDefect();
  const blank: DefectCreate = { kind: "bug", title: "", severity: "medium", priority: "P3", description: "", steps_to_reproduce: "", expected_result: "", actual_result: "", environment: "", assignee: "" };
  const [form, setForm] = useState<DefectCreate>(blank);
  const set = <K extends keyof DefectCreate>(k: K, v: DefectCreate[K]) => setForm((f) => ({ ...f, [k]: v }));
  const clean = (s: string | null | undefined) => (s && s.trim() ? s.trim() : null);

  const submit = () => {
    if (!project) return toast.error(t("c.selectProject"));
    create.mutate(
      {
        project,
        ...form,
        title: form.title.trim(),
        description: clean(form.description),
        steps_to_reproduce: clean(form.steps_to_reproduce),
        expected_result: clean(form.expected_result),
        actual_result: clean(form.actual_result),
        environment: clean(form.environment),
        assignee: clean(form.assignee),
      },
      {
        onSuccess: (d) => {
          toast.success(`${t("df.created")}: ${d.key}`);
          setForm(blank);
          onClose();
          navigate(withProject(`/defects/${d.id}`, project));
        },
        onError: toast.error,
      },
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("df.new")}
      wide
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {t("c.cancel")}
          </button>
          <button className="btn btn-primary" disabled={!form.title.trim() || !project || create.isPending} onClick={submit}>
            {t("c.create")}
          </button>
        </>
      }
    >
      {!project && <p className="mb-3 text-sm text-amber-600">{t("c.selectProject")}</p>}
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label={t("c.title")} className="sm:col-span-4">
          <input className="input" value={form.title} onChange={(e) => set("title", e.target.value)} />
        </Field>
        <Field label={t("c.kind")}>
          <EnumSelect value={form.kind} options={DEFECT_KINDS} onChange={(v) => v && set("kind", v)} />
        </Field>
        <Field label={t("c.severity")}>
          <EnumSelect value={form.severity} options={SEVERITIES} onChange={(v) => v && set("severity", v)} />
        </Field>
        <Field label={t("c.priority")}>
          <EnumSelect value={form.priority} options={PRIORITIES} onChange={(v) => v && set("priority", v)} />
        </Field>
        <Field label={t("c.assignee")}>
          <input className="input" value={form.assignee ?? ""} onChange={(e) => set("assignee", e.target.value)} />
        </Field>
        <Field label={t("c.environment")} className="sm:col-span-4">
          <input className="input" value={form.environment ?? ""} onChange={(e) => set("environment", e.target.value)} />
        </Field>
        <Field label={t("c.description")} className="sm:col-span-4">
          <textarea className="input" rows={3} value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <Field label={t("df.steps")} className="sm:col-span-4">
          <textarea className="input font-mono text-xs" rows={3} value={form.steps_to_reproduce ?? ""} onChange={(e) => set("steps_to_reproduce", e.target.value)} />
        </Field>
        <Field label={t("df.expected")} className="sm:col-span-2">
          <textarea className="input" rows={2} value={form.expected_result ?? ""} onChange={(e) => set("expected_result", e.target.value)} />
        </Field>
        <Field label={t("df.actual")} className="sm:col-span-2">
          <textarea className="input" rows={2} value={form.actual_result ?? ""} onChange={(e) => set("actual_result", e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

function Board({ defects }: { defects: Defect[] }) {
  const { t, te } = usePrefs();
  const [project] = useProjectKey();
  const toast = useToast();
  const update = useUpdateDefect();
  const [dragOver, setDragOver] = useState<DefectStatus | null>(null);

  const drop = (status: DefectStatus, e: DragEvent) => {
    e.preventDefault();
    setDragOver(null);
    const id = Number(e.dataTransfer.getData("text/plain"));
    const d = defects.find((x) => x.id === id);
    if (!d || d.status === status) return;
    update.mutate({ id, status }, { onSuccess: () => toast.success(`${d.key} → ${te(status)}`), onError: toast.error });
  };

  return (
    <div className="grid auto-cols-[minmax(240px,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2">
      {KANBAN_COLUMNS.map((col) => {
        const items = defects.filter((d) => d.status === col);
        return (
          <div
            key={col}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(col);
            }}
            onDragLeave={() => setDragOver((c) => (c === col ? null : c))}
            onDrop={(e) => drop(col, e)}
            className={cx(
              "flex min-h-[300px] flex-col rounded-lg border bg-slate-100/60 p-2 dark:bg-slate-900/50",
              dragOver === col ? "border-indigo-400 ring-2 ring-indigo-300 dark:ring-indigo-600" : "border-slate-200 dark:border-slate-800",
            )}
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <Pill value={col} />
              <span className="muted text-xs tabular-nums">{items.length}</span>
            </div>
            <div className="flex flex-col gap-2">
              {items.map((d) => (
                <Link
                  key={d.id}
                  to={withProject(`/defects/${d.id}`, project)}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/plain", String(d.id));
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className="card block cursor-grab border-l-4 p-2.5 text-sm shadow-sm hover:shadow-md active:cursor-grabbing"
                  style={{ borderLeftColor: SEVERITY_HEX[d.severity] }}
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-slate-500">{d.key}</span>
                    <PriorityPill value={d.priority} />
                  </div>
                  <div className="line-clamp-3 font-medium">{d.title}</div>
                  <div className="mt-2 flex items-center justify-between gap-2 text-xs">
                    <span className="muted truncate">{d.assignee ?? t("c.unassigned")}</span>
                    <SlaBadge d={d} />
                  </div>
                </Link>
              ))}
              {items.length === 0 && <div className="muted rounded border border-dashed border-slate-300 p-4 text-center text-xs dark:border-slate-700">{t("df.dropHere")}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function DefectsPage() {
  const { t, te, lang } = usePrefs();
  const [project] = useProjectKey();
  const navigate = useNavigate();
  const [view, setView] = useState<"table" | "board">(() => (storage.get("secqa.defects.view") === "board" ? "board" : "table"));
  const [q, setQ] = useState("");
  const [severity, setSeverity] = useState<Severity[]>([]);
  const [status, setStatus] = useState<DefectStatus | "">("");
  const [kind, setKind] = useState<DefectKind | "">("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [openOnly, setOpenOnly] = useState(false);
  const [slaOnly, setSlaOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);

  const board = view === "board";
  const { data, isLoading, error } = useDefects({
    project, q, severity, kind, priority,
    status: board ? undefined : status,
    open_only: openOnly,
    sla_breached: slaOnly,
    limit: board ? 1000 : LIMIT,
    offset: board ? 0 : offset,
  });

  const switchView = (v: "table" | "board") => {
    storage.set("secqa.defects.view", v);
    setView(v);
  };
  const reset = () => setOffset(0);

  return (
    <>
      <PageHeader
        title={t("df.title")}
        subtitle={t("df.subtitle")}
        actions={
          <>
            <div className="inline-flex rounded-md border border-slate-300 p-0.5 dark:border-slate-700" role="group">
              <button className={cx("btn btn-ghost btn-sm", !board && "bg-slate-100 dark:bg-slate-800")} onClick={() => switchView("table")} aria-pressed={!board}>
                <List className="h-4 w-4" /> {t("df.table")}
              </button>
              <button className={cx("btn btn-ghost btn-sm", board && "bg-slate-100 dark:bg-slate-800")} onClick={() => switchView("board")} aria-pressed={board}>
                <Columns3 className="h-4 w-4" /> {t("df.kanban")}
              </button>
            </div>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> {t("df.new")}
            </button>
          </>
        }
      />

      <div className="card mb-3 space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="muted pointer-events-none absolute left-2.5 top-2 h-4 w-4" />
            <input className="input pl-8" placeholder={t("c.search")} value={q} onChange={(e) => { setQ(e.target.value); reset(); }} aria-label={t("c.search")} />
          </div>
          {!board && (
            <EnumSelect ariaLabel={t("c.status")} className="w-40" value={status} options={DEFECT_STATUSES} allLabel={`${t("c.status")}: ${t("c.all")}`} onChange={(v) => { setStatus(v); reset(); }} />
          )}
          <EnumSelect ariaLabel={t("c.kind")} className="w-40" value={kind} options={DEFECT_KINDS} allLabel={`${t("c.kind")}: ${t("c.all")}`} onChange={(v) => { setKind(v); reset(); }} />
          <EnumSelect ariaLabel={t("c.priority")} className="w-32" value={priority} options={PRIORITIES} allLabel={`${t("c.priority")}: ${t("c.all")}`} onChange={(v) => { setPriority(v); reset(); }} />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <ChipToggle options={SEVERITIES} value={severity} onChange={(v) => { setSeverity(v); reset(); }} />
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={openOnly} onChange={(e) => { setOpenOnly(e.target.checked); reset(); }} /> {t("df.openOnly")}
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={slaOnly} onChange={(e) => { setSlaOnly(e.target.checked); reset(); }} /> {t("df.slaOnly")}
          </label>
        </div>
      </div>

      {error && <ErrorState error={error} />}
      {board ? (
        isLoading ? <TableSkeleton /> : <Board defects={data?.items ?? []} />
      ) : (
        <div className="card overflow-x-auto">
          {isLoading ? (
            <TableSkeleton />
          ) : !data?.items.length ? (
            <Empty message={t("df.empty")} />
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t("c.key")}</th>
                  <th>{t("c.severity")}</th>
                  <th>{t("c.priority")}</th>
                  <th>{t("c.title")}</th>
                  <th>{t("c.kind")}</th>
                  <th>{t("c.status")}</th>
                  <th>{t("c.assignee")}</th>
                  <th>SLA</th>
                  <th>{t("c.created")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((d) => {
                  const href = withProject(`/defects/${d.id}`, project);
                  return (
                    <tr key={d.id} className="cursor-pointer" tabIndex={0} onClick={() => navigate(href)} onKeyDown={(e) => e.key === "Enter" && navigate(href)}>
                      <td className="whitespace-nowrap font-mono text-xs">{d.key}</td>
                      <td><SeverityBadge severity={d.severity} /></td>
                      <td><PriorityPill value={d.priority} /></td>
                      <td className="max-w-[420px]">
                        <div className="truncate font-medium">{d.title}</div>
                        {d.finding_count > 0 && <div className="muted text-xs">{d.finding_count} {t("rn.findings").toLowerCase()}</div>}
                      </td>
                      <td className="text-xs">{te(d.kind)}</td>
                      <td><Pill value={d.status} /></td>
                      <td className="text-xs">{d.assignee ?? <span className="muted">{t("c.unassigned")}</span>}</td>
                      <td><SlaBadge d={d} /></td>
                      <td className="muted whitespace-nowrap text-xs">{fmtRelative(d.created_at, lang)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {data && <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
        </div>
      )}
      <NewDefectModal open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

