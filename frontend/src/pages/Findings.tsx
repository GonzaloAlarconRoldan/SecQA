import { useSearchParams } from "react-router-dom";
import { SEVERITIES, TRIAGE_STATUSES, type Severity, type TriageStatus } from "../api/types";
import { FindingsExplorer } from "../components/FindingsExplorer";
import { PageHeader } from "../components/ui";
import { usePrefs } from "../lib/prefs";

export default function FindingsPage() {
  const { t } = usePrefs();
  const [params] = useSearchParams();
  const triage = params.get("triage_status");
  const initial = {
    category: params.get("category") ?? "",
    owasp_id: params.get("owasp_id") ?? "",
    iso_control: params.get("iso_control") ?? "",
    q: params.get("q") ?? "",
    source: params.get("source") ?? "",
    triage_status: TRIAGE_STATUSES.includes(triage as TriageStatus) ? (triage as TriageStatus) : ("" as const),
    severity: params.getAll("severity").filter((s): s is Severity => SEVERITIES.includes(s as Severity)),
  };
  // Remount when the deep-link filters change (e.g. navigating from Compliance or Overview).
  const key = [initial.category, initial.owasp_id, initial.iso_control, initial.q, initial.source, initial.triage_status, params.get("project")].join("|");
  return (
    <>
      <PageHeader title={t("fd.title")} subtitle={t("fd.subtitle")} />
      <FindingsExplorer key={key} initial={initial} />
    </>
  );
}
