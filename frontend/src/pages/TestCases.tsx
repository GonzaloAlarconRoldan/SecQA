import { Bot, ChevronDown, ChevronRight, Hand, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDeleteTestCase, useSaveTestCase, useTestCaseHistory, useTestCases } from "../api/hooks";
import {
  PRIORITIES,
  TEST_CASE_STATUSES,
  TEST_TYPES,
  type TestCase,
  type TestCaseInput,
  type TestCaseStatus,
  type TestType,
} from "../api/types";
import { Drawer, Empty, EnumSelect, ErrorState, Field, PageHeader, Pill, PriorityPill, TableSkeleton } from "../components/ui";
import { fmtDate, fmtMs } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";
import { useToast } from "../lib/toast";

const blank: TestCaseInput = {
  title: "",
  type: "security",
  suite: "",
  priority: "P3",
  status: "active",
  description: "",
  preconditions: "",
  steps: [{ action: "", expected: "" }],
  expected_result: "",
  automated: false,
  automation_ref: "",
  cwe_id: "",
  owasp_id: "",
  iso_control: "",
  tags: [],
};

function toInput(tc: TestCase): TestCaseInput {
  const { title, type, suite, priority, status, description, preconditions, steps, expected_result, automated,
    automation_ref, cwe_id, owasp_id, iso_control, tags } = tc;
  return { title, type, suite, priority, status, description, preconditions, steps, expected_result, automated,
    automation_ref, cwe_id, owasp_id, iso_control, tags };
}

function History({ id }: { id: number }) {
  const { t, lang } = usePrefs();
  const [project] = useProjectKey();
  const { data, isLoading } = useTestCaseHistory(id);
  if (isLoading) return <TableSkeleton rows={3} cols={3} />;
  if (!data?.length) return <p className="muted text-sm">{t("tc.noHistory")}</p>;
  return (
    <table className="tbl">
      <tbody>
        {data.map((r) => (
          <tr key={r.id}>
            <td><Pill value={r.status} /></td>
            <td className="font-mono text-xs">
              <Link className="hover:underline" to={withProject(`/runs/${r.run_id}`, project)}>#{r.run_id}</Link>
            </td>
            <td className="num text-xs">{fmtMs(r.duration_ms)}</td>
            <td className="muted text-xs">{fmtDate(r.created_at, lang)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Editor({ tc, onClose }: { tc: TestCase | null; onClose: () => void }) {
  const { t } = usePrefs();
  const [project] = useProjectKey();
  const toast = useToast();
  const save = useSaveTestCase();
  const del = useDeleteTestCase();
  const [form, setForm] = useState<TestCaseInput>(() => (tc ? toInput(tc) : blank));
  const [tags, setTags] = useState(() => (tc?.tags ?? []).join(", "));
  const set = <K extends keyof TestCaseInput>(k: K, v: TestCaseInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const nullable = (s: string | null) => (s && s.trim() ? s.trim() : null);

  const submit = () => {
    if (!tc && !project) return toast.error(t("c.selectProject"));
    const body: Partial<TestCaseInput> = {
      ...form,
      title: form.title.trim(),
      suite: nullable(form.suite),
      description: nullable(form.description),
      preconditions: nullable(form.preconditions),
      expected_result: nullable(form.expected_result),
      automation_ref: nullable(form.automation_ref),
      cwe_id: nullable(form.cwe_id),
      owasp_id: nullable(form.owasp_id),
      iso_control: nullable(form.iso_control),
      steps: form.steps.filter((s) => s.action.trim()).map((s) => ({ action: s.action.trim(), expected: nullable(s.expected) })),
      tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
    };
    save.mutate(
      { id: tc?.id, project, body },
      { onSuccess: (r) => { toast.success(`${r.key} ✓`); onClose(); }, onError: toast.error },
    );
  };

  return (
    <Drawer
      open
      onClose={onClose}
      title={tc ? <><span className="font-mono text-slate-500">{tc.key}</span> {tc.title}</> : t("tc.new")}
      footer={
        <>
          <button className="btn btn-primary" disabled={!form.title.trim() || save.isPending} onClick={submit}>{t("c.save")}</button>
          <button className="btn" onClick={onClose}>{t("c.cancel")}</button>
          {tc && (
            <button
              className="btn ml-auto"
              onClick={() => window.confirm(t("tc.deleteConfirm")) && del.mutate(tc.id, { onSuccess: onClose, onError: toast.error })}
            >
              <Trash2 className="h-4 w-4 text-red-500" /> {t("c.delete")}
            </button>
          )}
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={t("c.title")} className="sm:col-span-3">
          <input className="input" value={form.title} onChange={(e) => set("title", e.target.value)} />
        </Field>
        <Field label={t("c.type")}>
          <EnumSelect value={form.type} options={TEST_TYPES} onChange={(v) => v && set("type", v)} />
        </Field>
        <Field label={t("c.priority")}>
          <EnumSelect value={form.priority} options={PRIORITIES} onChange={(v) => v && set("priority", v)} />
        </Field>
        <Field label={t("c.status")}>
          <EnumSelect value={form.status} options={TEST_CASE_STATUSES} onChange={(v) => v && set("status", v)} />
        </Field>
        <Field label={t("tc.suite")} className="sm:col-span-2">
          <input className="input" value={form.suite ?? ""} onChange={(e) => set("suite", e.target.value)} />
        </Field>
        <Field label={t("tc.automated")}>
          <label className="flex h-[34px] items-center gap-2 text-sm">
            <input type="checkbox" checked={form.automated} onChange={(e) => set("automated", e.target.checked)} /> {t("tc.automated")}
          </label>
        </Field>
        {form.automated && (
          <Field label={t("tc.automationRef")} className="sm:col-span-3">
            <input className="input font-mono text-xs" value={form.automation_ref ?? ""} onChange={(e) => set("automation_ref", e.target.value)} placeholder="perf/k6/load.js · semgrep:rule-id" />
          </Field>
        )}
        <Field label={t("c.description")} className="sm:col-span-3">
          <textarea className="input" rows={2} value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <Field label={t("tc.preconditions")} className="sm:col-span-3">
          <textarea className="input" rows={2} value={form.preconditions ?? ""} onChange={(e) => set("preconditions", e.target.value)} />
        </Field>
      </div>

      <div className="mt-4">
        <div className="label">{t("tc.steps")}</div>
        <ol className="space-y-2">
          {form.steps.map((s, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="muted mt-2 w-5 text-right text-xs tabular-nums">{i + 1}.</span>
              <textarea
                className="input flex-1"
                rows={1}
                placeholder={t("tc.action")}
                value={s.action}
                onChange={(e) => set("steps", form.steps.map((x, j) => (j === i ? { ...x, action: e.target.value } : x)))}
              />
              <textarea
                className="input flex-1"
                rows={1}
                placeholder={t("tc.expected")}
                value={s.expected ?? ""}
                onChange={(e) => set("steps", form.steps.map((x, j) => (j === i ? { ...x, expected: e.target.value } : x)))}
              />
              <button className="btn btn-ghost btn-sm mt-1" aria-label={`${t("c.delete")} ${t("tc.step")} ${i + 1}`} onClick={() => set("steps", form.steps.filter((_, j) => j !== i))}>
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ol>
        <button className="btn btn-sm mt-2" onClick={() => set("steps", [...form.steps, { action: "", expected: "" }])}>
          <Plus className="h-3.5 w-3.5" /> {t("tc.addStep")}
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Field label={t("tc.expectedResult")} className="sm:col-span-3">
          <textarea className="input" rows={2} value={form.expected_result ?? ""} onChange={(e) => set("expected_result", e.target.value)} />
        </Field>
        <Field label="OWASP">
          <input className="input font-mono text-xs" placeholder="A03:2021" value={form.owasp_id ?? ""} onChange={(e) => set("owasp_id", e.target.value)} />
        </Field>
        <Field label="CWE">
          <input className="input font-mono text-xs" placeholder="CWE-89" value={form.cwe_id ?? ""} onChange={(e) => set("cwe_id", e.target.value)} />
        </Field>
        <Field label="ISO 27001">
          <input className="input font-mono text-xs" placeholder="A.8.28" value={form.iso_control ?? ""} onChange={(e) => set("iso_control", e.target.value)} />
        </Field>
        <Field label={t("c.tags")} className="sm:col-span-3">
          <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} />
        </Field>
      </div>

      {tc && (
        <div className="mt-6">
          <div className="label">{t("tc.history")}</div>
          <History id={tc.id} />
        </div>
      )}
    </Drawer>
  );
}

export default function TestCasesPage() {
  const { t, te } = usePrefs();
  const [project] = useProjectKey();
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [type, setType] = useState<TestType | "">("");
  const [status, setStatus] = useState<TestCaseStatus | "">("");
  const [editing, setEditing] = useState<TestCase | "new" | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const { data, isLoading, error } = useTestCases({ project, q, type, status, limit: 1000 });

  const groups = useMemo(() => {
    const m = new Map<string, TestCase[]>();
    for (const tc of data?.items ?? []) {
      const k = tc.suite ?? "";
      m.set(k, [...(m.get(k) ?? []), tc]);
    }
    return [...m.entries()].sort(([a], [b]) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)));
  }, [data]);

  return (
    <>
      <PageHeader
        title={t("tc.title")}
        subtitle={t("tc.subtitle")}
        actions={
          <button className="btn btn-primary" onClick={() => setEditing("new")} disabled={!project} title={project ? undefined : t("c.selectProject")}>
            <Plus className="h-4 w-4" /> {t("tc.new")}
          </button>
        }
      />
      <div className="card mb-3 flex flex-wrap items-center gap-2 p-3">
        <div className="relative min-w-[220px] flex-1">
          <Search className="muted pointer-events-none absolute left-2.5 top-2 h-4 w-4" />
          <input className="input pl-8" placeholder={t("c.search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("c.search")} />
        </div>
        <EnumSelect ariaLabel={t("c.type")} className="w-40" value={type} options={TEST_TYPES} allLabel={`${t("c.type")}: ${t("c.all")}`} onChange={setType} />
        <EnumSelect ariaLabel={t("c.status")} className="w-40" value={status} options={TEST_CASE_STATUSES} allLabel={`${t("c.status")}: ${t("c.all")}`} onChange={setStatus} />
      </div>
      {error && <ErrorState error={error} />}
      {isLoading ? (
        <div className="card"><TableSkeleton /></div>
      ) : groups.length === 0 ? (
        <div className="card"><Empty message={t("tc.empty")} /></div>
      ) : (
        <div className="space-y-3">
          {groups.map(([suite, cases]) => {
            const isCollapsed = collapsed.has(suite);
            const passed = cases.filter((c) => c.last_status === "passed").length;
            const failed = cases.filter((c) => c.last_status === "failed" || c.last_status === "error").length;
            return (
              <section key={suite} className="card overflow-x-auto">
                <button
                  className="card-h w-full text-left hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  aria-expanded={!isCollapsed}
                  onClick={() => setCollapsed((s) => { const n = new Set(s); if (n.has(suite)) n.delete(suite); else n.add(suite); return n; })}
                >
                  <span className="flex items-center gap-2">
                    {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    {suite || t("tc.noSuite")}
                    <span className="muted text-xs font-normal">({cases.length})</span>
                  </span>
                  <span className="flex gap-2 text-xs font-normal">
                    <span className="text-emerald-600 dark:text-emerald-400">✓ {passed}</span>
                    <span className="text-red-600 dark:text-red-400">✗ {failed}</span>
                  </span>
                </button>
                {!isCollapsed && (
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>{t("c.key")}</th>
                        <th>{t("c.title")}</th>
                        <th>{t("c.type")}</th>
                        <th>{t("c.priority")}</th>
                        <th>{t("c.status")}</th>
                        <th />
                        <th>{t("df.reference")}</th>
                        <th>{t("tc.lastResult")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cases.map((tc) => (
                        <tr key={tc.id} className="cursor-pointer" tabIndex={0} onClick={() => setEditing(tc)} onKeyDown={(e) => e.key === "Enter" && setEditing(tc)}>
                          <td className="whitespace-nowrap font-mono text-xs">{tc.key}</td>
                          <td className="max-w-[420px] truncate font-medium">{tc.title}</td>
                          <td><Pill value={tc.type} /></td>
                          <td><PriorityPill value={tc.priority} /></td>
                          <td className="text-xs">{te(tc.status)}</td>
                          <td title={tc.automated ? t("tc.automated") : t("tc.manual")}>
                            {tc.automated ? <Bot className="h-4 w-4 text-indigo-500" /> : <Hand className="muted h-4 w-4" />}
                          </td>
                          <td className="whitespace-nowrap font-mono text-xs">{[tc.owasp_id, tc.cwe_id].filter(Boolean).join(" · ") || "—"}</td>
                          <td>{tc.last_status ? <Pill value={tc.last_status} /> : <span className="muted text-xs">—</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            );
          })}
        </div>
      )}
      {editing && <Editor key={editing === "new" ? "new" : editing.id} tc={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}
