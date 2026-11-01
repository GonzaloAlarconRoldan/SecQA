import { useState } from "react";
import { useRuns } from "../api/hooks";
import { RUN_KINDS, RUN_STATUSES, type RunKind, type RunStatus } from "../api/types";
import { RunsTable } from "../components/RunsTable";
import { EnumSelect, ErrorState, PageHeader, Pagination } from "../components/ui";
import { usePrefs } from "../lib/prefs";
import { useProjectKey } from "../lib/project";

const LIMIT = 25;

export default function RunsPage() {
  const { t } = usePrefs();
  const [project] = useProjectKey();
  const [kind, setKind] = useState<RunKind | "">("");
  const [status, setStatus] = useState<RunStatus | "">("");
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error } = useRuns({ project, kind, status, limit: LIMIT, offset });

  return (
    <>
      <PageHeader
        title={t("rn.title")}
        subtitle={t("rn.subtitle")}
        actions={
          <>
            <EnumSelect ariaLabel={t("c.kind")} className="w-40" value={kind} options={RUN_KINDS} allLabel={`${t("c.kind")}: ${t("c.all")}`} onChange={(v) => { setKind(v); setOffset(0); }} />
            <EnumSelect ariaLabel={t("c.status")} className="w-40" value={status} options={RUN_STATUSES} allLabel={`${t("c.status")}: ${t("c.all")}`} onChange={(v) => { setStatus(v); setOffset(0); }} />
          </>
        }
      />
      {error && <ErrorState error={error} />}
      <div className="card overflow-x-auto">
        <RunsTable runs={data?.items ?? []} loading={isLoading} />
        {data && <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
    </>
  );
}
