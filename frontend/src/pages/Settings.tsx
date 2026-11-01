import { ExternalLink, Lock, Unlock } from "lucide-react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useMeta } from "../api/hooks";
import { Card, Field, PageHeader, Skeleton } from "../components/ui";
import type { Lang } from "../lib/i18n";
import { usePrefs, type Theme } from "../lib/prefs";
import { useToast } from "../lib/toast";

export default function SettingsPage() {
  const { t, actor, setActor, token, setToken, theme, setTheme, lang, setLang } = usePrefs();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: meta, isLoading } = useMeta();
  const [name, setName] = useState(actor);
  const [tok, setTok] = useState(token);

  return (
    <>
      <PageHeader title={t("st.title")} subtitle={t("st.subtitle")} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t("st.title")}>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setActor(name.trim() || "reviewer");
              setToken(tok.trim());
              void qc.invalidateQueries();
              toast.success(t("c.saved"));
            }}
          >
            <Field label={t("st.actor")} hint={t("st.actorHint")}>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
            </Field>
            <Field label={t("st.token")} hint={t("st.tokenHint")}>
              <input className="input font-mono" type="password" autoComplete="off" value={tok} onChange={(e) => setTok(e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("st.theme")}>
                <select className="input" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
                  <option value="system">{t("st.theme.system")}</option>
                  <option value="light">{t("st.theme.light")}</option>
                  <option value="dark">{t("st.theme.dark")}</option>
                </select>
              </Field>
              <Field label={t("st.language")}>
                <select className="input" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                  <option value="en">English</option>
                  <option value="es">Español</option>
                </select>
              </Field>
            </div>
            <button className="btn btn-primary" type="submit">{t("c.save")}</button>
          </form>
        </Card>

        <Card title={t("st.hub")}>
          {isLoading || !meta ? (
            <Skeleton className="h-24" />
          ) : (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="muted">{t("st.version")}</dt>
                <dd className="font-mono">{meta.version}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="muted">{t("st.authRequired")}</dt>
                <dd className="flex items-center gap-1">
                  {meta.auth_required ? <Lock className="h-4 w-4 text-emerald-500" /> : <Unlock className="h-4 w-4 text-amber-500" />}
                  {meta.auth_required ? t("c.yes") : t("c.no")}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="muted">{t("st.tolerance")}</dt>
                <dd className="tabular-nums">{(meta.perf_regression_tolerance * 100).toFixed(0)}%</dd>
              </div>
              <div>
                <dt className="muted mb-1">{t("st.sla")}</dt>
                <dd className="grid grid-cols-4 gap-2 text-center">
                  {Object.entries(meta.sla_days).map(([sev, days]) => (
                    <div key={sev} className="rounded-md bg-slate-50 p-2 dark:bg-slate-800/50">
                      <div className="text-lg font-semibold tabular-nums">{days ?? "—"}</div>
                      <div className="muted text-[11px] uppercase">{sev}</div>
                    </div>
                  ))}
                </dd>
              </div>
              <a className="mt-3 inline-flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400" href="/api/docs" target="_blank" rel="noreferrer">
                <ExternalLink className="h-4 w-4" /> {t("st.apiDocs")}
              </a>
            </dl>
          )}
        </Card>
      </div>
    </>
  );
}
