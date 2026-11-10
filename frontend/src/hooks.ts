import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { CaseSummary, Health, Job } from "./types";

export type Route = { name: "upload" } | { name: "job"; id: string } | { name: "case"; id: string };

function parseHash(hash: string): Route {
  const [, kind, id] = hash.replace(/^#/, "").split("/");
  if (kind === "job" && id) return { name: "job", id: decodeURIComponent(id) };
  if (kind === "case" && id) return { name: "case", id: decodeURIComponent(id) };
  return { name: "upload" };
}

/** Hash routing: survives reloads and works behind any static file server. */
export function useRoute(): [Route, (to: string) => void] {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((to: string) => {
    window.location.hash = to;
  }, []);
  return [route, navigate];
}

/** Poll a loader every `ms` while `active` returns true for the latest value. */
function usePolling<T>(load: (s: AbortSignal) => Promise<T>, ms: number, active: (v: T | null) => boolean, deps: unknown[]) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  useEffect(() => {
    const ctl = new AbortController();
    let timer: number | undefined;
    const tick = async () => {
      let latest: T | null = null;
      try {
        latest = await load(ctl.signal);
        setValue(latest);
        setError(null);
      } catch (e) {
        if (ctl.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      }
      if (!ctl.signal.aborted && activeRef.current(latest)) timer = window.setTimeout(tick, ms);
    };
    setValue(null);
    void tick();
    return () => {
      ctl.abort();
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { value, error };
}

/** Server health; keeps polling while models are still loading or the server is unreachable. */
export function useHealth() {
  return usePolling<Health>(
    (s) => api.health(s),
    2500,
    (h) => !h || Object.values(h.models).some((m) => m.enabled && m.installed && !m.loaded),
    [],
  );
}

export function useJob(jobId: string) {
  return usePolling<Job>((s) => api.job(jobId, s), 1000, (j) => !j || j.status === "queued" || j.status === "running", [jobId]);
}

export function useActiveJobs(refreshKey: number) {
  return usePolling<Job[]>((s) => api.activeJobs(s), 2000, (jobs) => !!jobs && jobs.length > 0, [refreshKey]);
}

export function useCases(query: string, refreshKey: number) {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const ctl = new AbortController();
    const timer = window.setTimeout(() => {
      api.cases(query, ctl.signal).then(
        (c) => {
          setCases(c);
          setError(null);
        },
        (e) => !ctl.signal.aborted && setError(e instanceof Error ? e.message : String(e)),
      );
    }, query ? 250 : 0); // debounce typing
    return () => {
      ctl.abort();
      window.clearTimeout(timer);
    };
  }, [query, refreshKey]);
  return { cases, error };
}
