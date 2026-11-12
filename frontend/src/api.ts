import type { CasePayload, CaseSummary, Health, Job, Urls } from "./types";

/** Backend origin. Empty when the backend serves this app itself (local installs). */
const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
const CODE_KEY = "realis.accessCode";

let accessCode = (typeof localStorage !== "undefined" && localStorage.getItem(CODE_KEY)) || "";

export function getAccessCode(): string {
  return accessCode;
}

export function setAccessCode(code: string): void {
  accessCode = code;
  if (code) localStorage.setItem(CODE_KEY, code);
  else localStorage.removeItem(CODE_KEY);
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/**
 * Absolute URL for a server path. Media elements (img, video, audio, links)
 * cannot send headers, so files under /cases carry the access code as ?key=.
 */
export function asset<T extends string | null>(path: T): T {
  if (!path) return path;
  const url = /^https?:/.test(path) ? path : BASE + path;
  if (!accessCode || !path.startsWith("/cases/")) return url as T;
  return `${url}${url.includes("?") ? "&" : "?"}key=${encodeURIComponent(accessCode)}` as T;
}

const mapValues = (o: Record<string, string>) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, asset(v)]));

/** Point every URL in a result at the backend, with the access code. */
export function localize(payload: CasePayload): CasePayload {
  const u = payload.urls;
  const urls: Urls = {
    html: asset(u.html), json: asset(u.json), evidence: asset(u.evidence), overview: mapValues(u.overview),
    artifacts: Object.fromEntries(Object.entries(u.artifacts).map(([k, v]) => [k, mapValues(v)])),
  };
  return { ...payload, urls };
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (HTTP ${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

const get = <T>(path: string, signal?: AbortSignal) =>
  fetch(BASE + path, { signal, headers: accessCode ? { "X-Access-Code": accessCode } : {} }).then((r) => parse<T>(r));

export const api = {
  health: (signal?: AbortSignal) => get<Health>("/api/health", signal),
  cases: (query = "", signal?: AbortSignal) =>
    get<CaseSummary[]>(`/api/cases?limit=200&q=${encodeURIComponent(query)}`, signal)
      .then((cases) => cases.map((c) => ({ ...c, thumbnail: asset(c.thumbnail) }))),
  case: (caseId: string, signal?: AbortSignal) =>
    get<{ case_id: string; items: CasePayload[] }>(`/api/cases/${encodeURIComponent(caseId)}`, signal)
      .then((c) => ({ ...c, items: c.items.map(localize) })),
  job: (jobId: string, signal?: AbortSignal) =>
    get<Job>(`/api/jobs/${encodeURIComponent(jobId)}`, signal)
      .then((j) => (j.result ? { ...j, result: localize(j.result) } : j)),
  activeJobs: (signal?: AbortSignal) => get<Job[]>("/api/jobs", signal),

  /** Upload with byte-level progress (fetch cannot report upload progress). */
  upload(file: File, deep: boolean, onProgress: (fraction: number) => void): Promise<Job> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", file);
      form.append("deep", String(deep));
      xhr.open("POST", BASE + "/api/jobs");
      if (accessCode) xhr.setRequestHeader("X-Access-Code", accessCode);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onerror = () => reject(new ApiError("Network error while uploading", 0));
      xhr.onload = () => {
        let body: { detail?: unknown } & Partial<Job> = {};
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* non-JSON error page */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as Job);
        else reject(new ApiError(typeof body.detail === "string" ? body.detail : `Upload failed (HTTP ${xhr.status})`, xhr.status));
      };
      xhr.send(form);
    });
  },
};
