import type { CasePayload, CaseSummary, Health, Job } from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (HTTP ${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

const get = <T>(url: string, signal?: AbortSignal) => fetch(url, { signal }).then((r) => parse<T>(r));

export const api = {
  health: (signal?: AbortSignal) => get<Health>("/api/health", signal),
  cases: (query = "", signal?: AbortSignal) =>
    get<CaseSummary[]>(`/api/cases?limit=200&q=${encodeURIComponent(query)}`, signal),
  case: (caseId: string, signal?: AbortSignal) =>
    get<{ case_id: string; items: CasePayload[] }>(`/api/cases/${encodeURIComponent(caseId)}`, signal),
  job: (jobId: string, signal?: AbortSignal) => get<Job>(`/api/jobs/${encodeURIComponent(jobId)}`, signal),
  activeJobs: (signal?: AbortSignal) => get<Job[]>("/api/jobs", signal),

  /** Upload with byte-level progress (fetch cannot report upload progress). */
  upload(file: File, deep: boolean, onProgress: (fraction: number) => void): Promise<Job> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", file);
      form.append("deep", String(deep));
      xhr.open("POST", "/api/jobs");
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
