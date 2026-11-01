import { AlertTriangle, ArrowLeft, Download, Paperclip, Pencil, Send, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { authHeaders } from "../api/client";
import {
  useAddComment,
  useDefect,
  useDefects,
  useDeleteDefect,
  useUpdateDefect,
  useUploadAttachment,
} from "../api/hooks";
import {
  DEFECT_KINDS,
  DEFECT_STATUSES,
  PRIORITIES,
  SEVERITIES,
  type Attachment,
  type DefectDetail,
  type DefectStatus,
  type DefectUpdate,
} from "../api/types";
import { Card, Empty, EnumSelect, ErrorState, Field, Modal, Pill, PlainText, SeverityBadge, Skeleton } from "../components/ui";
import { fmtBytes, fmtDate, fmtRelative } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";
import { useToast } from "../lib/toast";

async function downloadAttachment(a: Attachment) {
  const res = await fetch(a.url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = a.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function DuplicateModal({ defect, onClose }: { defect: DefectDetail; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const update = useUpdateDefect();
  const { data } = useDefects({ project: undefined, limit: 1000 });
  const [target, setTarget] = useState<number | "">("");
  const candidates = (data?.items ?? []).filter((d) => d.project_id === defect.project_id && d.id !== defect.id);
  return (
    <Modal
      open
      onClose={onClose}
      title={t("df.duplicateOf")}
      footer={
        <>
          <button className="btn" onClick={onClose}>{t("c.cancel")}</button>
          <button
            className="btn btn-primary"
            disabled={target === "" || update.isPending}
            onClick={() =>
              update.mutate(
                { id: defect.id, status: "duplicate", duplicate_of_id: Number(target) },
                { onSuccess: () => { toast.success(t("c.saved")); onClose(); }, onError: toast.error },
              )
            }
          >
            {t("c.save")}
          </button>
        </>
      }
    >
      <p className="muted mb-3 text-sm">{t("df.duplicateRequired")}</p>
      <select className="input" value={target} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")} aria-label={t("df.duplicateOf")}>
        <option value="">—</option>
        {candidates.map((d) => (
          <option key={d.id} value={d.id}>
            {d.key} — {d.title}
          </option>
        ))}
      </select>
    </Modal>
  );
}

function TextEditModal({ defect, onClose }: { defect: DefectDetail; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const update = useUpdateDefect();
  const [form, setForm] = useState({
    title: defect.title,
    description: defect.description ?? "",
    steps_to_reproduce: defect.steps_to_reproduce ?? "",
    expected_result: defect.expected_result ?? "",
    actual_result: defect.actual_result ?? "",
    tags: defect.tags.join(", "),
  });
  const save = () =>
    update.mutate(
      {
        id: defect.id,
        title: form.title.trim(),
        description: form.description || null,
        steps_to_reproduce: form.steps_to_reproduce || null,
        expected_result: form.expected_result || null,
        actual_result: form.actual_result || null,
        tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean),
      },
      { onSuccess: () => { toast.success(t("c.saved")); onClose(); }, onError: toast.error },
    );
  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={`${t("c.edit")} ${defect.key}`}
      footer={
        <>
          <button className="btn" onClick={onClose}>{t("c.cancel")}</button>
          <button className="btn btn-primary" disabled={!form.title.trim() || update.isPending} onClick={save}>{t("c.save")}</button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label={t("c.title")}>
          <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <Field label={t("c.description")}>
          <textarea className="input" rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label={t("df.steps")}>
          <textarea className="input font-mono text-xs" rows={4} value={form.steps_to_reproduce} onChange={(e) => setForm({ ...form, steps_to_reproduce: e.target.value })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("df.expected")}>
            <textarea className="input" rows={3} value={form.expected_result} onChange={(e) => setForm({ ...form, expected_result: e.target.value })} />
          </Field>
          <Field label={t("df.actual")}>
            <textarea className="input" rows={3} value={form.actual_result} onChange={(e) => setForm({ ...form, actual_result: e.target.value })} />
          </Field>
        </div>
        <Field label={t("c.tags")}>
          <input className="input" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}

export default function DefectDetailPage() {
  const { t, te, lang } = usePrefs();
  const toast = useToast();
  const navigate = useNavigate();
  const [project] = useProjectKey();
  const id = Number(useParams().id);
  const { data: d, isLoading, error } = useDefect(id);
  const update = useUpdateDefect();
  const del = useDeleteDefect();
  const addComment = useAddComment(id);
  const upload = useUploadAttachment(id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [comment, setComment] = useState("");
  const [dupOpen, setDupOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  if (error) return <ErrorState error={error} />;
  if (isLoading || !d)
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-64" />
      </div>
    );

  const patch = (body: DefectUpdate) => update.mutate({ id: d.id, ...body }, { onSuccess: () => toast.success(t("c.saved")), onError: toast.error });
  const setStatus = (s: DefectStatus) => (s === "duplicate" ? setDupOpen(true) : patch({ status: s }));

  return (
    <>
      <Link to={withProject("/defects", project)} className="muted mb-3 inline-flex items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="h-4 w-4" /> {t("df.title")}
      </Link>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-slate-500">{d.key}</span>
            <SeverityBadge severity={d.severity} />
            <Pill value={d.status} />
            <Pill value={d.kind} />
            {d.sla_breached && (
              <span className="pill bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300">
                <AlertTriangle className="h-3 w-3" /> {t("df.breached")}
              </span>
            )}
          </div>
          <h1 className="page-title break-words">{d.title}</h1>
        </div>
        <div className="flex gap-2">
          <button className="btn" onClick={() => setEditOpen(true)}>
            <Pencil className="h-4 w-4" /> {t("c.edit")}
          </button>
          <button
            className="btn"
            aria-label={t("c.delete")}
            onClick={() => {
              if (window.confirm(t("df.deleteConfirm")))
                del.mutate(d.id, { onSuccess: () => navigate(withProject("/defects", project)), onError: toast.error });
            }}
          >
            <Trash2 className="h-4 w-4 text-red-500" />
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-4">
          <Card title={t("c.description")}>
            <PlainText text={d.description} />
            {(d.steps_to_reproduce || d.expected_result || d.actual_result) && (
              <div className="mt-4 space-y-4">
                {d.steps_to_reproduce && (
                  <div>
                    <h3 className="label">{t("df.steps")}</h3>
                    <PlainText text={d.steps_to_reproduce} mono />
                  </div>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  {d.expected_result && (
                    <div>
                      <h3 className="label">{t("df.expected")}</h3>
                      <PlainText text={d.expected_result} />
                    </div>
                  )}
                  {d.actual_result && (
                    <div>
                      <h3 className="label">{t("df.actual")}</h3>
                      <PlainText text={d.actual_result} />
                    </div>
                  )}
                </div>
              </div>
            )}
          </Card>

          <Card title={`${t("df.findings")} (${d.findings.length})`} bodyClass="overflow-x-auto">
            {d.findings.length === 0 ? (
              <Empty />
            ) : (
              <table className="tbl">
                <tbody>
                  {d.findings.map((f) => (
                    <tr key={f.id}>
                      <td><SeverityBadge severity={f.severity} /></td>
                      <td className="max-w-[360px]">
                        <div className="truncate font-medium">{f.title}</div>
                        <div className="muted truncate font-mono text-xs">
                          {f.endpoint ?? (f.file_path ? `${f.file_path}${f.line_start ? `:${f.line_start}` : ""}` : f.category)}
                        </div>
                      </td>
                      <td className="text-xs">{f.tool ?? f.source}</td>
                      <td className="font-mono text-xs">
                        <Link className="hover:underline" to={withProject(`/runs/${f.run_id}`, project)}>#{f.run_id}</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card title={`${t("df.comments")} (${d.comments.length})`}>
            <ol className="space-y-3">
              {d.comments.map((c) => (
                <li key={c.id} className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
                  <div className="muted mb-1 flex justify-between text-xs">
                    <span className="font-medium text-slate-700 dark:text-slate-300">{c.author}</span>
                    <span title={fmtDate(c.created_at, lang)}>{fmtRelative(c.created_at, lang)}</span>
                  </div>
                  <PlainText text={c.body} />
                </li>
              ))}
            </ol>
            <form
              className="mt-3 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (!comment.trim()) return;
                addComment.mutate(comment.trim(), { onSuccess: () => setComment(""), onError: toast.error });
              }}
            >
              <textarea
                className="input"
                rows={2}
                placeholder={t("df.commentPlaceholder")}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
                }}
              />
              <button className="btn btn-primary self-end" disabled={!comment.trim() || addComment.isPending} type="submit" aria-label={t("df.addComment")}>
                <Send className="h-4 w-4" />
              </button>
            </form>
          </Card>

          <Card title={t("df.history")}>
            <ol className="relative ml-2 border-l border-slate-200 dark:border-slate-800">
              {d.events.map((e) => (
                <li key={e.id} className="mb-3 ml-4">
                  <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-indigo-500 dark:border-slate-900" />
                  <div className="text-sm">
                    <span className="font-medium">{e.actor}</span>{" "}
                    {e.field === "created" ? (
                      <span className="muted">created {e.new_value}</span>
                    ) : (
                      <>
                        <span className="muted">changed</span> <span className="font-mono text-xs">{e.field}</span>{" "}
                        <span className="muted line-through">{e.old_value ?? "—"}</span> → <b>{e.new_value ?? "—"}</b>
                      </>
                    )}
                  </div>
                  <div className="muted text-xs">{fmtDate(e.at, lang)}</div>
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <aside className="space-y-4">
          <Card title={t("df.details")}>
            <div className="space-y-3">
              <Field label={t("c.status")}>
                <EnumSelect value={d.status} options={DEFECT_STATUSES} onChange={(v) => v && setStatus(v)} />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label={t("c.severity")}>
                  <EnumSelect value={d.severity} options={SEVERITIES} onChange={(v) => v && patch({ severity: v })} />
                </Field>
                <Field label={t("c.priority")}>
                  <EnumSelect value={d.priority} options={PRIORITIES} onChange={(v) => v && patch({ priority: v })} />
                </Field>
              </div>
              <Field label={t("c.kind")}>
                <EnumSelect value={d.kind} options={DEFECT_KINDS} onChange={(v) => v && patch({ kind: v })} />
              </Field>
              <Field label={t("c.assignee")}>
                <input
                  key={`a-${d.assignee}`}
                  className="input"
                  defaultValue={d.assignee ?? ""}
                  placeholder={t("c.unassigned")}
                  onBlur={(e) => e.target.value.trim() !== (d.assignee ?? "") && patch({ assignee: e.target.value.trim() || null })}
                />
              </Field>
              <Field label={t("c.environment")}>
                <input
                  key={`e-${d.environment}`}
                  className="input"
                  defaultValue={d.environment ?? ""}
                  onBlur={(e) => e.target.value.trim() !== (d.environment ?? "") && patch({ environment: e.target.value.trim() || null })}
                />
              </Field>
            </div>
            <dl className="mt-4 space-y-1.5 border-t border-slate-200 pt-3 text-sm dark:border-slate-800">
              {([
                [t("c.due"), d.due_at ? <span className={d.sla_breached ? "font-semibold text-red-600 dark:text-red-400" : ""}>{fmtDate(d.due_at, lang, false)}</span> : "—"],
                [t("c.reporter"), d.reporter ?? "—"],
                [t("c.created"), fmtDate(d.created_at, lang)],
                [t("c.updated"), fmtRelative(d.updated_at, lang)],
                [t("df.resolved"), fmtDate(d.resolved_at, lang)],
                [t("df.closed"), fmtDate(d.closed_at, lang)],
                [t("df.foundIn"), d.found_in_run_id ? <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/runs/${d.found_in_run_id}`, project)}>#{d.found_in_run_id}</Link> : "—"],
                [t("df.duplicateOf"), d.duplicate_of_id ? <Link className="text-indigo-600 hover:underline dark:text-indigo-400" to={withProject(`/defects/${d.duplicate_of_id}`, project)}>#{d.duplicate_of_id}</Link> : null],
                [t("df.reference"), [d.owasp_id, d.cwe_id, d.iso_control && `ISO ${d.iso_control}`].filter(Boolean).join(" · ") || "—"],
              ] as const)
                .filter(([, v]) => v !== null)
                .map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-2">
                    <dt className="muted">{label}</dt>
                    <dd className="text-right">{value}</dd>
                  </div>
                ))}
            </dl>
            {d.tags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1">
                {d.tags.map((tag) => (
                  <span key={tag} className="code">{tag}</span>
                ))}
              </div>
            )}
          </Card>

          <Card
            title={`${t("df.attachments")} (${d.attachments.length})`}
            actions={
              <>
                <button className="btn btn-sm" disabled={upload.isPending} onClick={() => fileRef.current?.click()}>
                  <Paperclip className="h-3.5 w-3.5" /> {t("df.upload")}
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) upload.mutate(file, { onSuccess: () => toast.success(file.name), onError: toast.error });
                    e.target.value = "";
                  }}
                />
              </>
            }
          >
            {d.attachments.length === 0 ? (
              <p className="muted text-sm">{t("c.none")}</p>
            ) : (
              <ul className="space-y-1.5">
                {d.attachments.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="min-w-0 truncate" title={a.filename}>{a.filename}</span>
                    <span className="muted shrink-0 text-xs">{fmtBytes(a.size)}</span>
                    <button className="btn btn-ghost btn-sm" aria-label={`Download ${a.filename}`} onClick={() => downloadAttachment(a).catch(toast.error)}>
                      <Download className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <p className="muted text-xs">{te(d.kind)} · #{d.id}</p>
        </aside>
      </div>

      {dupOpen && <DuplicateModal defect={d} onClose={() => setDupOpen(false)} />}
      {editOpen && <TextEditModal defect={d} onClose={() => setEditOpen(false)} />}
    </>
  );
}
