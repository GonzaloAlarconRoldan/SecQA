import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Query } from "./client";
import type {
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

export function useUploadAttachment(defectId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api(`/defects/${defectId}/attachments`, { method: "POST", form });
    },
    onSuccess: () => invalidate("defect"),
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
