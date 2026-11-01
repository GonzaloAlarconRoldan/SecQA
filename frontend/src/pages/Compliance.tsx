import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCompliance } from "../api/hooks";
import type { ComplianceRow, ComplianceState } from "../api/types";
import { cx, Empty, ErrorState, PageHeader, TableSkeleton, Tabs } from "../components/ui";
import { toneClass, STATUS_TONE } from "../lib/colors";
import type { I18nKey } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";

type Fw = "owasp-top10-2021" | "owasp-api-top10-2023" | "iso27001-2022-annex-a";
const FRAMEWORKS: { id: Fw; label: I18nKey }[] = [
  { id: "owasp-top10-2021", label: "cp.owasp" },
  { id: "owasp-api-top10-2023", label: "cp.api" },
  { id: "iso27001-2022-annex-a", label: "cp.iso" },
];
const STATES: ComplianceState[] = ["fail", "warn", "pass", "untested"];

export default function CompliancePage() {
  const { t } = usePrefs();
  const [project] = useProjectKey();
  const navigate = useNavigate();
  const { data, isLoading, error } = useCompliance(project);
  const [fw, setFw] = useState<Fw>("owasp-top10-2021");
  const rows: ComplianceRow[] = data?.[fw] ?? [];

  const counts = STATES.map((s) => ({ s, n: rows.filter((r) => r.state === s).length }));

  return (
    <>
      <PageHeader title={t("cp.title")} subtitle={t("cp.subtitle")} />
      <Tabs<Fw> value={fw} onChange={setFw} tabs={FRAMEWORKS.map((f) => ({ id: f.id, label: t(f.label) }))} />
      {error && <ErrorState error={error} />}

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {counts.map(({ s, n }) => (
          <div key={s} className={cx("rounded-lg px-4 py-3", toneClass(STATUS_TONE[s]))}>
            <div className="text-2xl font-semibold tabular-nums">{n}</div>
            <div className="text-xs font-medium uppercase tracking-wide">{t(`cp.state.${s}` as I18nKey)}</div>
          </div>
        ))}
      </div>

      <div className="card overflow-x-auto">
        {isLoading ? (
          <TableSkeleton />
        ) : rows.length === 0 ? (
          <Empty />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("cp.item")}</th>
                <th>{t("c.title")}</th>
                <th>{t("cp.state")}</th>
                <th className="num">{t("cp.openFindings")}</th>
                <th className="num">{t("cp.openDefects")}</th>
                <th className="num">{t("cp.testCases")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const linkable = r.open_findings > 0;
                const filter: Record<string, string> = { [fw.startsWith("iso") ? "iso_control" : "owasp_id"]: r.id };
                const go = () => linkable && navigate(withProject("/findings", project, filter));
                return (
                  <tr
                    key={r.id}
                    className={cx(linkable && "cursor-pointer")}
                    tabIndex={linkable ? 0 : -1}
                    onClick={go}
                    onKeyDown={(e) => e.key === "Enter" && go()}
                    title={linkable ? t("cp.hint") : undefined}
                  >
                    <td className="whitespace-nowrap font-mono text-xs">{r.id}</td>
                    <td className="font-medium">{r.title}</td>
                    <td>
                      <span className={cx("pill", toneClass(STATUS_TONE[r.state]))}>{t(`cp.state.${r.state}` as I18nKey)}</span>
                    </td>
                    <td className={cx("num", r.open_findings > 0 && "font-semibold text-amber-600 dark:text-amber-400")}>{r.open_findings}</td>
                    <td className={cx("num", r.open_defects > 0 && "font-semibold text-red-600 dark:text-red-400")}>{r.open_defects}</td>
                    <td className="num">{r.test_cases}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <p className="muted mt-2 text-xs">{t("cp.hint")}</p>
    </>
  );
}
