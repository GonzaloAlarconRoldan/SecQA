import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, authHeaders, type Query } from "./client";
import type {
  Attachment,
  AttachmentUpload,
  AuditEntry,
  Comparison,
  Compliance,
  Defect,
  DefectCreate,
  DefectDetail,
  DefectUpdate,
  Finding,
  Meta,
  Overview,
  Page,
  PerfMetric,
  PerfPoint,
  Priority,
  Project,
  ProjectSummary,
  Run,
  TestCase,
  TestCaseInput,
  TestResult,
  ToolReport,
  TriageStatus,
} from "./types";

export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/meta"), staleTime: 60_000 });

export const useProjects = () =>
  useQuery({ queryKey: ["projects"], queryFn: () => api<ProjectSummary[]>("/projects") });

export const useOverview = (project?: string) =>
  useQuery({
    queryKey: ["overview", project],
    queryFn: () => api<Overview>("/stats/overview", { query: { project } }),
  });

export const useRuns = (query: Query) =>
  useQuery({
    queryKey: ["runs", query],
    queryFn: () => api<Page<Run>>("/runs", { query }),
    placeholderData: keepPreviousData,
  });

export const useRun = (id: number) =>
  useQuery({ queryKey: ["run", id], queryFn: () => api<Run>(`/runs/${id}`), enabled: Number.isFinite(id) });

export const useRunResults = (id: number) =>
  useQuery({ queryKey: ["run", id, "results"], queryFn: () => api<TestResult[]>(`/runs/${id}/results`) });

export const useRunPerf = (id: number) =>
  useQuery({ queryKey: ["run", id, "perf"], queryFn: () => api<PerfMetric[]>(`/runs/${id}/perf`) });

export const useRunCompare = (id: number, enabled: boolean) =>
  useQuery({ queryKey: ["run", id, "compare"], queryFn: () => api<Comparison>(`/runs/${id}/compare`), enabled });

export const useAudit = (projectKey: string | null | undefined, runId?: number) =>
  useQuery({
    queryKey: ["audit", projectKey, runId],
    queryFn: () => api<AuditEntry[]>(`/projects/${projectKey}/audit`, { query: { run_id: runId } }),
    enabled: !!projectKey,
  });

export const useFindings = (query: Query) =>
  useQuery({
    queryKey: ["findings", query],
    queryFn: () => api<Page<Finding>>("/findings", { query }),
    placeholderData: keepPreviousData,
  });

export const useDefects = (query: Query) =>
  useQuery({
    queryKey: ["defects", query],
    queryFn: () => api<Page<Defect>>("/defects", { query }),
    placeholderData: keepPreviousData,
  });

export const useDefect = (id: number) =>
  useQuery({ queryKey: ["defect", id], queryFn: () => api<DefectDetail>(`/defects/${id}`) });

export const useTestCases = (query: Query) =>
  useQuery({
    queryKey: ["testcases", query],
    queryFn: () => api<Page<TestCase>>("/testcases", { query }),
    placeholderData: keepPreviousData,
  });

export const useTestCaseHistory = (id: number | null) =>
  useQuery({
    queryKey: ["testcase", id, "history"],
    queryFn: () => api<TestResult[]>(`/testcases/${id}/history`),
    enabled: id !== null,
  });

export const usePerfScenarios = (project?: string) =>
  useQuery({
    queryKey: ["perf-scenarios", project],
    queryFn: () => api<Record<string, string[]>>("/perf/scenarios", { query: { project } }),
  });

export const usePerfTrend = (query: Query) =>
  useQuery({ queryKey: ["perf-trend", query], queryFn: () => api<PerfPoint[]>("/perf/trend", { query }) });

export const useCompliance = (project?: string) =>
  useQuery({ queryKey: ["compliance", project], queryFn: () => api<Compliance>("/compliance", { query: { project } }) });

// ---- mutations ---------------------------------------------------------------

function useInvalidate() {
  const qc = useQueryClient();
  return (...keys: string[]) => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export function useCreateProject() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { key: string; name: string; description?: string; repo_url?: string }) =>
      api<Project>("/projects", { method: "POST", body }),
    onSuccess: () => invalidate("projects"),
  });
}

export function useUpdateRun() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; is_baseline?: boolean; notes?: string }) =>
      api<Run>(`/runs/${id}`, { method: "PATCH", body }),
    onSuccess: () => invalidate("run", "runs", "perf-trend", "overview"),
  });
}

export function useTriage() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; triage_status?: TriageStatus; review_comment?: string }) =>
      api<Finding>(`/findings/${id}`, { method: "PATCH", body }),
    onSuccess: () => invalidate("findings", "overview", "compliance", "run"),
  });
}

export function useBulkTriage() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { ids: number[]; triage_status: TriageStatus; review_comment?: string }) =>
      api<{ updated: number }>("/findings/bulk-triage", { method: "POST", body }),
    onSuccess: () => invalidate("findings", "overview", "compliance", "run"),
  });
}

export function usePromoteFindings() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ project, ...body }: { project: string; finding_ids: number[]; title?: string; priority?: Priority }) =>
      api<Defect>(`/projects/${project}/defects/from-findings`, { method: "POST", body }),
    onSuccess: () => invalidate("findings", "defects", "overview", "compliance", "projects"),
  });
}

export function useCreateDefect() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ project, ...body }: DefectCreate & { project: string }) =>
      api<Defect>(`/projects/${project}/defects`, { method: "POST", body }),
    onSuccess: () => invalidate("defects", "overview", "projects", "compliance"),
  });
}

export function useUpdateDefect() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: DefectUpdate & { id: number }) =>
      api<Defect>(`/defects/${id}`, { method: "PATCH", body }),
    onSuccess: () => invalidate("defects", "defect", "overview", "projects", "compliance"),
  });
}

export function useDeleteDefect() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/defects/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate("defects", "overview", "projects", "findings"),
  });
}

export function useAddComment(defectId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: string) => api(`/defects/${defectId}/comments`, { method: "POST", body: { body } }),
    onSuccess: () => invalidate("defect"),
  });
}

function attachmentForm({ file, caption, kind }: AttachmentUpload): FormData {
  const form = new FormData();
  form.append("file", file);
  if (caption?.trim()) form.append("caption", caption.trim());
  if (kind) form.append("kind", kind);
  return form;
}

export function useUploadAttachment(defectId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (upload: AttachmentUpload) =>
      api<Attachment>(`/defects/${defectId}/attachments`, { method: "POST", form: attachmentForm(upload) }),
    onSuccess: () => invalidate("defect"),
  });
}

export const useFindingAttachments = (findingId: number | null) =>
  useQuery({
    queryKey: ["finding-attachments", findingId],
    queryFn: () => api<Attachment[]>(`/findings/${findingId}/attachments`),
    enabled: findingId !== null,
  });

export function useUploadFindingAttachment(findingId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (upload: AttachmentUpload) =>
      api<Attachment>(`/findings/${findingId}/attachments`, { method: "POST", form: attachmentForm(upload) }),
    onSuccess: () => invalidate("finding-attachments", "findings", "defect"),
  });
}

export function useDeleteAttachment() {
  const qc = useQueryClient();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/attachments/${id}`, { method: "DELETE" }),
    onSuccess: (_d, id) => {
      qc.removeQueries({ queryKey: ["attachment-blob", id] });
      return invalidate("finding-attachments", "findings", "defect");
    },
  });
}

/** Attachments need the auth header, so images are fetched as blobs and shown via object URLs. */
export function useAttachmentBlob(a: Attachment | null, enabled = true) {
  return useQuery({
    queryKey: ["attachment-blob", a?.id],
    queryFn: async () => {
      const res = await fetch(a!.url, { headers: authHeaders() });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.blob();
    },
    enabled: !!a && enabled,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
  });
}

export function useSaveTestCase() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, project, body }: { id?: number; project?: string; body: Partial<TestCaseInput> }) =>
      id
        ? api<TestCase>(`/testcases/${id}`, { method: "PATCH", body })
        : api<TestCase>(`/projects/${project}/testcases`, { method: "POST", body }),
    onSuccess: () => invalidate("testcases", "compliance"),
  });
}

export function useDeleteTestCase() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/testcases/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate("testcases", "compliance"),
  });
}

// ---- tool HTML reports (signed view links expire after 12 h, so keep them fresh) ----
const REPORT_STALE_MS = 5 * 60_000;

export const useRunReports = (runId: number) =>
  useQuery({
    queryKey: ["tool-reports", "run", runId],
    queryFn: () => api<ToolReport[]>(`/runs/${runId}/reports`),
    staleTime: REPORT_STALE_MS,
    refetchInterval: 10 * 60_000,
  });

export const useToolReports = (query: { project?: string; tool?: string; limit?: number }) =>
  useQuery({
    queryKey: ["tool-reports", "list", query],
    queryFn: () => api<ToolReport[]>("/tool-reports", { query }),
    staleTime: REPORT_STALE_MS,
    refetchInterval: 10 * 60_000,
  });

export function useUploadReport(runId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ file, tool, title }: { file: File; tool: string; title?: string }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("tool", tool);
      if (title) form.append("title", title);
      return api<ToolReport>(`/runs/${runId}/reports`, { method: "POST", form });
    },
    onSuccess: () => invalidate("tool-reports"),
  });
}

export function useDeleteReport() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/attachments/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate("tool-reports"),
  });
}
