import { ExternalLink, FolderPlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateProject, useProjects } from "../api/hooks";
import { Empty, ErrorState, Field, Modal, PageHeader, Skeleton } from "../components/ui";
import { fmtRelative } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey } from "../lib/project";
import { useToast } from "../lib/toast";

const KEY_RE = /^[A-Z][A-Z0-9]{1,15}$/;

function NewProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const create = useCreateProject();
  const [, setProject] = useProjectKey();
  const [form, setForm] = useState({ key: "", name: "", description: "", repo_url: "" });
  const valid = KEY_RE.test(form.key) && form.name.trim().length > 0;

  const submit = () =>
    create.mutate(
      {
        key: form.key,
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        repo_url: form.repo_url.trim() || undefined,
      },
      {
        onSuccess: (p) => {
          toast.success(`${p.key} ✓`);
          setProject(p.key);
          setForm({ key: "", name: "", description: "", repo_url: "" });
          onClose();
        },
        onError: toast.error,
      },
    );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("pr.new")}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {t("c.cancel")}
          </button>
          <button className="btn btn-primary" disabled={!valid || create.isPending} onClick={submit}>
            {t("c.create")}
          </button>
        </>
      }
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) submit();
        }}
      >
        <Field label={t("c.key")} hint={t("pr.keyHint")}>
          <input
            className="input font-mono uppercase"
            value={form.key}
            maxLength={16}
            onChange={(e) => setForm({ ...form, key: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })}
            aria-invalid={form.key.length > 0 && !KEY_RE.test(form.key)}
          />
        </Field>
        <Field label={t("c.name")}>
          <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label={t("c.description")}>
          <textarea className="input" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label={t("pr.repo")}>
          <input className="input" type="url" value={form.repo_url} onChange={(e) => setForm({ ...form, repo_url: e.target.value })} />
        </Field>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

export default function ProjectsPage() {
  const { t, lang } = usePrefs();
  const { data, isLoading, error } = useProjects();
  const [open, setOpen] = useState(false);

  return (
    <>
      <PageHeader
        title={t("pr.title")}
        actions={
          <button className="btn btn-primary" onClick={() => setOpen(true)}>
            <FolderPlus className="h-4 w-4" /> {t("pr.new")}
          </button>
        }
      />
      {error && <ErrorState error={error} />}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : !data?.length ? (
        <div className="card">
          <Empty message={t("pr.empty")}>
            <button className="btn btn-primary" onClick={() => setOpen(true)}>
              {t("pr.new")}
            </button>
          </Empty>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((p) => (
            <div key={p.key} className="card flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link to={`/?project=${p.key}`} className="text-base font-semibold hover:underline">
                    {p.name}
                  </Link>
                  <div className="code mt-1 inline-block">{p.key}</div>
                </div>
                {p.repo_url && (
                  <a href={p.repo_url} target="_blank" rel="noreferrer noopener" className="btn btn-ghost btn-sm" aria-label={t("pr.repo")}>
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>
              {p.description && <p className="muted mt-2 line-clamp-2 text-sm">{p.description}</p>}
              <div className="mt-auto grid grid-cols-3 gap-2 pt-4 text-center">
                <Link to={`/defects?project=${p.key}`} className="rounded-md bg-slate-50 p-2 hover:bg-slate-100 dark:bg-slate-800/50 dark:hover:bg-slate-800">
                  <div className="text-lg font-semibold tabular-nums">{p.open_defects}</div>
                  <div className="muted text-[11px]">{t("ov.openDefects")}</div>
                </Link>
                <div className="rounded-md bg-slate-50 p-2 dark:bg-slate-800/50">
                  <div className={`text-lg font-semibold tabular-nums ${p.critical_open ? "text-red-600 dark:text-red-400" : ""}`}>{p.critical_open}</div>
                  <div className="muted text-[11px]">{t("ov.criticalOpen")}</div>
                </div>
                <Link to={`/runs?project=${p.key}`} className="rounded-md bg-slate-50 p-2 hover:bg-slate-100 dark:bg-slate-800/50 dark:hover:bg-slate-800">
                  <div className="text-lg font-semibold tabular-nums">{p.run_count}</div>
                  <div className="muted text-[11px]">{t("pr.runs")}</div>
                </Link>
              </div>
              <div className="muted mt-3 text-xs">
                {t("pr.lastRun")}: {p.last_run_at ? fmtRelative(p.last_run_at, lang) : t("pr.never")}
              </div>
            </div>
          ))}
        </div>
      )}
      <NewProjectModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
