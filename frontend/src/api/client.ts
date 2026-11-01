import { storage } from "../lib/storage";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type QueryValue = string | number | boolean | null | undefined | (string | number)[];
export type Query = Record<string, QueryValue>;

const unauthorizedListeners = new Set<() => void>();
export function onUnauthorized(cb: () => void): () => void {
  unauthorizedListeners.add(cb);
  return () => unauthorizedListeners.delete(cb);
}

export function buildQuery(query?: Query): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.forEach((item) => params.append(k, String(item)));
    else params.append(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "X-SecQA-Actor": `human:${storage.get("secqa.actor") || "reviewer"}` };
  const token = storage.get("secqa.token");
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

interface RequestOpts {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Query;
  body?: unknown;
  form?: FormData;
}

async function raw(path: string, opts: RequestOpts = {}): Promise<Response> {
  const headers = authHeaders();
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`/api${path}${buildQuery(opts.query)}`, { method: opts.method ?? "GET", headers, body });
  if (!res.ok) {
    if (res.status === 401) unauthorizedListeners.forEach((cb) => cb());
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail))
        message = data.detail.map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return res;
}

export async function api<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const res = await raw(path, opts);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch with auth headers and trigger a browser download (links can't carry the token). */
export async function download(path: string, query: Query, fallbackName: string): Promise<void> {
  const res = await raw(path, { query });
  const blob = await res.blob();
  const match = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Open an authenticated HTML response in a new tab. */
export async function openHtml(path: string, query: Query): Promise<void> {
  const win = window.open("", "_blank");
  const res = await raw(path, { query });
  const blob = new Blob([await res.text()], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  if (win) win.location.href = url;
  else window.location.href = url;
}
