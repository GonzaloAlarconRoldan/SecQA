import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { storage } from "./storage";

export const PROJECT_STORAGE_KEY = "secqa.project";

/** Selected project, kept in `?project=KEY` (shareable) and mirrored to localStorage. */
export function useProjectKey(): [string | undefined, (key: string | undefined) => void] {
  const [params, setParams] = useSearchParams();
  const key = params.get("project") || undefined;
  const setKey = useCallback(
    (next: string | undefined) => {
      storage.set(PROJECT_STORAGE_KEY, next ?? null);
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          if (next) p.set("project", next);
          else p.delete("project");
          return p;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return [key, setKey];
}

/** Build an in-app link that keeps the current project selection. */
export function withProject(path: string, project: string | undefined, extra?: Record<string, string>): string {
  const p = new URLSearchParams(extra);
  if (project) p.set("project", project);
  const s = p.toString();
  return s ? `${path}?${s}` : path;
}
