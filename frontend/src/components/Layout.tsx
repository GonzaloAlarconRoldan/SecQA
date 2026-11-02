import {
  Activity,
  Bug,
  ClipboardList,
  FileText,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  Languages,
  Moon,
  PlayCircle,
  Settings as SettingsIcon,
  ShieldCheck,
  ShieldAlert,
  Sun,
} from "lucide-react";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { onUnauthorized } from "../api/client";
import { useMeta, useProjects } from "../api/hooks";
import type { I18nKey } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import { PROJECT_STORAGE_KEY, useProjectKey, withProject } from "../lib/project";
import { storage } from "../lib/storage";
import { useQueryClient } from "@tanstack/react-query";
import { cx, Modal, TableSkeleton } from "./ui";

const NAV: { group: I18nKey; items: { to: string; key: I18nKey; icon: ReactNode; end?: boolean }[] }[] = [
  {
    group: "nav.group.quality",
    items: [
      { to: "/", key: "nav.overview", icon: <LayoutDashboard className="h-4 w-4" />, end: true },
      { to: "/runs", key: "nav.runs", icon: <PlayCircle className="h-4 w-4" /> },
      { to: "/findings", key: "nav.findings", icon: <ShieldAlert className="h-4 w-4" /> },
      { to: "/defects", key: "nav.defects", icon: <Bug className="h-4 w-4" /> },
      { to: "/testcases", key: "nav.testcases", icon: <ClipboardList className="h-4 w-4" /> },
    ],
  },
  {
    group: "nav.group.analysis",
    items: [
      { to: "/performance", key: "nav.performance", icon: <Gauge className="h-4 w-4" /> },
      { to: "/compliance", key: "nav.compliance", icon: <ShieldCheck className="h-4 w-4" /> },
      { to: "/reports", key: "nav.reports", icon: <FileText className="h-4 w-4" /> },
    ],
  },
  {
    group: "nav.group.workspace",
    items: [
      { to: "/projects", key: "nav.projects", icon: <FolderKanban className="h-4 w-4" /> },
      { to: "/settings", key: "nav.settings", icon: <SettingsIcon className="h-4 w-4" /> },
    ],
  },
];

function ProjectSwitcher() {
  const { t } = usePrefs();
  const [project, setProject] = useProjectKey();
  const { data: projects } = useProjects();
  return (
    <select
      aria-label={t("c.project")}
      className="input h-8 w-auto min-w-56 max-w-xs py-1 pr-8"
      value={project ?? ""}
      onChange={(e) => setProject(e.target.value || undefined)}
    >
      <option value="">{t("top.allProjects")}</option>
      {projects?.map((p) => (
        <option key={p.key} value={p.key}>
          {p.key} — {p.name}
        </option>
      ))}
    </select>
  );
}

function TokenPrompt() {
  const { t, setToken } = usePrefs();
  const qc = useQueryClient();
  const { data: meta } = useMeta();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  useEffect(() => onUnauthorized(() => setOpen(true)), []);
  const show = open && (meta?.auth_required ?? true);
  return (
    <Modal
      open={show}
      onClose={() => setOpen(false)}
      title={t("auth.title")}
      footer={
        <button
          className="btn btn-primary"
          disabled={!value.trim()}
          onClick={() => {
            setToken(value.trim());
            setOpen(false);
            void qc.invalidateQueries();
          }}
        >
          {t("auth.submit")}
        </button>
      }
    >
      <p className="mb-3 text-sm">{t("auth.body")}</p>
      <input
        className="input font-mono"
        type="password"
        autoComplete="off"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label={t("st.token")}
      />
    </Modal>
  );
}

export function Layout() {
  const { t, isDark, setTheme, lang, setLang } = usePrefs();
  const [project, setProject] = useProjectKey();
  const location = useLocation();
  const { data: meta } = useMeta();

  // Restore the last selected project when the URL doesn't carry one.
  useEffect(() => {
    if (!project) {
      const saved = storage.get(PROJECT_STORAGE_KEY);
      if (saved) setProject(saved);
    }
    // only on first mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 md:flex">
        <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4 dark:border-slate-800">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600 text-white">
            <Activity className="h-4 w-4" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">SecQA Hub</div>
            <div className="muted text-[10px]">v{meta?.version ?? "…"}</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV.map((g) => (
            <div key={g.group} className="mb-4">
              <div className="muted px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider">{t(g.group)}</div>
              {g.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={withProject(item.to, project)}
                  end={item.end}
                  className={({ isActive }) =>
                    cx(
                      "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm font-medium transition",
                      isActive
                        ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white",
                    )
                  }
                >
                  {item.icon}
                  {t(item.key)}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur-sm dark:border-slate-800 dark:bg-slate-900/90">
          <nav className="flex gap-1 overflow-x-auto md:hidden" aria-label="Mobile">
            {NAV.flatMap((g) => g.items).map((item) => (
              <NavLink
                key={item.to}
                to={withProject(item.to, project)}
                end={item.end}
                title={t(item.key)}
                className={({ isActive }) => cx("btn btn-ghost btn-sm", isActive && "text-indigo-600")}
              >
                {item.icon}
              </NavLink>
            ))}
          </nav>
          <ProjectSwitcher />
          <div className="ml-auto flex items-center gap-1">
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setLang(lang === "en" ? "es" : "en")}
              title={t("top.language")}
              aria-label={t("top.language")}
            >
              <Languages className="h-4 w-4" />
              <span className="font-mono text-xs uppercase">{lang}</span>
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setTheme(isDark ? "light" : "dark")}
              title={t("top.theme")}
              aria-label={t("top.theme")}
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-6">
          <Suspense fallback={<TableSkeleton />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <TokenPrompt />
    </div>
  );
}
