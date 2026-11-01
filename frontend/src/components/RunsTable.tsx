import { Star } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { Run } from "../api/types";
import { fmtDuration, fmtRelative } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useProjectKey, withProject } from "../lib/project";
import { Empty, Pill, SeverityBar, TableSkeleton } from "./ui";

export function RunsTable({ runs, loading, compact }: { runs: Run[]; loading?: boolean; compact?: boolean }) {
  const { t, lang } = usePrefs();
  const [project] = useProjectKey();
  const navigate = useNavigate();
  if (loading) return <TableSkeleton rows={compact ? 5 : 10} />;
  if (!runs.length) return <Empty />;
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>#</th>
          {!project && <th>{t("c.project")}</th>}
          <th>{t("c.kind")}</th>
          <th>{t("c.status")}</th>
          <th>{t("c.title")}</th>
          <th>{t("rn.findings")}</th>
          {!compact && <th>{t("c.branch")}</th>}
          <th className="num">{t("c.duration")}</th>
          <th>{t("c.started")}</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => {
          const href = withProject(`/runs/${r.id}`, project);
          return (
            <tr
              key={r.id}
              className="cursor-pointer"
              tabIndex={0}
              onClick={() => navigate(href)}
              onKeyDown={(e) => e.key === "Enter" && navigate(href)}
            >
              <td className="font-mono text-xs">#{r.id}</td>
              {!project && <td className="font-mono text-xs">{r.project_key}</td>}
              <td>
                <Pill value={r.kind} />
              </td>
              <td>
                <Pill value={r.status} />
              </td>
              <td className="max-w-[280px] truncate">
                {r.is_baseline && <Star className="mr-1 inline h-3.5 w-3.5 fill-amber-400 text-amber-400" aria-label={t("rn.baseline")} />}
                {r.name || r.target || <span className="muted">—</span>}
              </td>
              <td>
                {r.kind === "performance" ? (
                  <span className="muted text-xs">—</span>
                ) : (
                  <SeverityBar counts={r.findings_by_severity} />
                )}
              </td>
              {!compact && (
                <td className="text-xs">
                  {r.branch ?? "—"} {r.commit_sha && <span className="code">{r.commit_sha.slice(0, 7)}</span>}
                </td>
              )}
              <td className="num text-xs">{fmtDuration(r.duration_s)}</td>
              <td className="muted whitespace-nowrap text-xs" title={r.started_at}>
                {fmtRelative(r.started_at, lang)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
