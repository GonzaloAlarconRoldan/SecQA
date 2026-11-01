import { AlertOctagon, CheckCircle2, ExternalLink, Layers, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { SEVERITIES, type IntelSource, type IntelSummary, type Severity, type StackDetected } from "../api/types";
import type { I18nKey } from "../lib/i18n";
import { fmtDate, fmtNum, fmtRelative } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { withProject } from "../lib/project";
import { Card, cx, Empty, Kpi, SeverityBadge } from "./ui";

const asSeverity = (s: string | null | undefined): Severity | null =>
  s && (SEVERITIES as string[]).includes(s.toLowerCase()) ? (s.toLowerCase() as Severity) : null;

function ExtLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  // Only http(s) links from the feeds are rendered as links.
  if (!/^https?:\/\//i.test(href)) return <span className={className}>{children}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cx("inline-flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400", className)}
    >
      {children}
      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
    </a>
  );
}

function SourceChip({ label, source }: { label: string; source?: IntelSource }) {
  const { t } = usePrefs();
  if (!source) return null;
  const ok = source.ok;
  return (
    <span
      className={cx(
        "pill gap-1",
        ok
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300"
          : "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
      )}
      title={ok ? t("in.sourceOk") : `${t("in.sourceFailed")}: ${source.error ?? "?"}`}
    >
      {ok ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> : <XCircle className="h-3.5 w-3.5" aria-hidden />}
      {label}
    </span>
  );
}

const WATCH_PREVIEW = 15;

export function IntelTab({ intel, projectKey }: { intel: IntelSummary; projectKey: string | null | undefined }) {
  const { t, lang } = usePrefs();
  const s = intel.stats ?? {};
  const src = intel.sources ?? {};
  const kev = intel.kev ?? [];
  const watch = intel.watchlist ?? [];
  const days = intel.window_days ?? src.nvd?.window_days ?? 30;
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? watch : watch.slice(0, WATCH_PREVIEW);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="muted">
          {t("in.checked").replace("{when}", fmtRelative(intel.generated_at, lang))}
        </span>
        <SourceChip label="OSV.dev" source={src.osv} />
        <SourceChip
          label={src.kev?.catalog_version ? `${t("in.kevCatalog")} ${src.kev.catalog_version}` : t("in.kevCatalog")}
          source={src.kev}
        />
        <SourceChip label="FIRST EPSS" source={src.epss} />
        <SourceChip label={t("in.nvdDays").replace("{n}", String(days))} source={src.nvd} />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label={t("in.vulns")} value={fmtNum(s.vulns ?? 0)} hint={t("in.ofComponents").replace("{n}", fmtNum(s.components ?? 0))} />
        <Kpi label={t("in.affected")} value={fmtNum(s.affected_components ?? 0)} />
        <Kpi label={t("in.kev")} value={fmtNum(s.kev ?? 0)} tone={(s.kev ?? 0) > 0 ? "danger" : "ok"} />
        <Kpi label={t("in.epssHigh")} value={fmtNum(s.epss_high ?? 0)} tone={(s.epss_high ?? 0) > 0 ? "warn" : undefined} />
        <Kpi label={t("in.watchlist")} value={fmtNum(s.watchlist ?? watch.length)} />
      </div>

      {kev.length > 0 && (
        <Card
          title={
            <span className="inline-flex items-center gap-2 text-red-700 dark:text-red-400">
              <AlertOctagon className="h-4 w-4" aria-hidden /> {t("in.kevTitle")}
            </span>
          }
          actions={
            <Link className="btn btn-sm" to={withProject("/findings", projectKey ?? undefined, { q: "CISA KEV" })}>
              {t("in.viewFindings")}
            </Link>
          }
          bodyClass="overflow-x-auto"
        >
          <table className="tbl">
            <thead>
              <tr>
                <th>CVE</th>
                <th>{t("in.component")}</th>
                <th>{t("in.dueDate")}</th>
                <th>{t("in.ransomware")}</th>
              </tr>
            </thead>
            <tbody>
              {kev.map((k, i) => (
                <tr key={`${k.cve ?? k.id}-${i}`} className="bg-red-50/60 dark:bg-red-500/5">
                  <td className="whitespace-nowrap font-mono text-xs">
                    {k.cve ? <ExtLink href={`https://nvd.nist.gov/vuln/detail/${encodeURIComponent(k.cve)}`}>{k.cve}</ExtLink> : (k.id ?? "—")}
                  </td>
                  <td className="font-mono text-xs">{k.component}</td>
                  <td className="whitespace-nowrap text-xs">{k.due_date ?? "—"}</td>
                  <td className="text-xs">
                    {k.ransomware === "Known" ? (
                      <span className="pill bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300">{t("in.ransomwareKnown")}</span>
                    ) : (
                      (k.ransomware ?? "—")
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Card title={t("in.watchTitle").replace("{n}", String(days))} bodyClass="overflow-x-auto">
        {watch.length === 0 ? (
          <Empty message={src.nvd && !src.nvd.ok ? `${t("in.sourceFailed")}: ${src.nvd.error ?? ""}` : t("in.watchEmpty")} />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("c.severity")}</th>
                <th>CVE</th>
                <th>{t("in.keyword")}</th>
                <th>{t("in.match")}</th>
                <th>{t("in.published")}</th>
                <th>{t("c.description")}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((w, i) => {
                const sev = asSeverity(w.severity);
                return (
                  <tr key={`${w.id}-${i}`}>
                    <td className="whitespace-nowrap">
                      {sev ? <SeverityBadge severity={sev} /> : <span className="muted text-xs">—</span>}
                      {w.score != null && <span className="muted ml-1 text-xs tabular-nums">{w.score.toFixed(1)}</span>}
                    </td>
                    <td className="whitespace-nowrap font-mono text-xs">
                      <ExtLink href={w.url}>{w.id}</ExtLink>
                      {w.kev && (
                        <span className="pill ml-1 bg-red-600 px-1.5 text-[10px] text-white" title={t("in.kev")}>
                          KEV
                        </span>
                      )}
                    </td>
                    <td className="text-xs">{w.keyword}</td>
                    <td>
                      {w.match === "cpe" ? (
                        <span className="pill bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300">{t("in.matchCpe")}</span>
                      ) : w.match === "text" ? (
                        <span className="pill bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">{t("in.matchText")}</span>
                      ) : (
                        <span className="muted text-xs">—</span>
                      )}
                    </td>
                    <td className="muted whitespace-nowrap text-xs">{w.published ? fmtDate(w.published, lang, false) : "—"}</td>
                    <td className="max-w-[460px] truncate text-xs" title={w.summary}>
                      {w.summary}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {watch.length > WATCH_PREVIEW && (
          <div className="border-t border-slate-200 px-4 py-2 text-center dark:border-slate-800">
            <button className="btn btn-ghost btn-sm" onClick={() => setShowAll((v) => !v)}>
              {showAll ? t("in.showLess") : t("in.showAll").replace("{n}", String(watch.length))}
            </button>
          </div>
        )}
      </Card>
      <p className="muted text-xs">{t("in.watchNote")}</p>
    </div>
  );
}

function ChipGroup({ label, items }: { label: I18nKey; items: ReactNode[] }) {
  const { t } = usePrefs();
  if (!items.length) return null;
  return (
    <div className="min-w-0">
      <div className="label mb-1">{t(label)}</div>
      <div className="flex flex-wrap gap-1.5">{items}</div>
    </div>
  );
}

const chip = (key: string, text: ReactNode, mono = false) => (
  <span
    key={key}
    className={cx(
      "inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200",
      mono && "font-mono",
    )}
  >
    {text}
  </span>
);

export function StackCard({ stack }: { stack: StackDetected }) {
  const { t } = usePrefs();
  const langs = Object.entries(stack.languages ?? {});
  const list = (xs?: string[]) => (xs ?? []).map((x) => chip(x, x));
  return (
    <Card
      title={
        <span className="inline-flex items-center gap-2">
          <Layers className="h-4 w-4" aria-hidden /> {t("rn.stack")}
        </span>
      }
      actions={
        <span className="muted text-xs font-normal">
          {t("st.components").replace("{n}", fmtNum(stack.component_count ?? 0)).replace("{m}", fmtNum(stack.pinned_count ?? 0))}
        </span>
      }
      className="mb-5"
    >
      <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        <ChipGroup
          label="st.languages"
          items={langs.map(([name, n]) =>
            chip(name, (
              <>
                {name}
                <span className="muted tabular-nums">{n}</span>
              </>
            )),
          )}
        />
        <ChipGroup label="st.frameworks" items={list(stack.frameworks)} />
        <ChipGroup label="st.databases" items={list(stack.databases)} />
        <ChipGroup label="st.auth" items={list(stack.auth)} />
        <ChipGroup label="st.api" items={list(stack.api_kind)} />
        <ChipGroup label="st.packageManagers" items={list(stack.package_managers)} />
        <ChipGroup label="st.images" items={(stack.docker_images ?? []).map((x) => chip(x, x, true))} />
        <ChipGroup label="st.ports" items={(stack.exposed_ports ?? []).map((p) => chip(String(p), p, true))} />
      </div>
    </Card>
  );
}
