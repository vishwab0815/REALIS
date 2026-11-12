import { useCallback, useEffect, useState } from "react";
import { ApiError, api, getAccessCode, setAccessCode } from "./api";
import { AccessGate } from "./components/AccessGate";
import { CaseView } from "./components/CaseView";
import { ErrorBoundary, Header, Sidebar } from "./components/Chrome";
import { JobView } from "./components/JobView";
import { UploadPanel } from "./components/UploadPanel";
import { useActiveJobs, useCases, useHealth, useRoute } from "./hooks";
import type { CasePayload, Job } from "./types";

export function App() {
  const [route, navigate] = useRoute();
  const { value: health, error: healthError } = useHealth();
  const [query, setQuery] = useState("");
  const [refresh, setRefresh] = useState(0);
  // The just-finished result, so opening it does not need another request.
  const [fresh, setFresh] = useState<CasePayload | null>(null);
  // null while unknown; servers without an access code are always unlocked.
  const [unlocked, setUnlocked] = useState<boolean | null>(null);
  const healthKnown = !!health;
  const authRequired = !!health?.auth_required;
  // Protected servers answer 401 until the user has entered the access code: wait for it.
  const canFetch = healthKnown && (!authRequired || unlocked === true);
  const { cases } = useCases(query, refresh, canFetch);
  const { value: jobs } = useActiveJobs(refresh, canFetch);

  useEffect(() => {
    if (!healthKnown) return;
    if (!authRequired) return setUnlocked(true);
    if (!getAccessCode()) return setUnlocked(false);
    api.cases().then(
      () => setUnlocked(true),
      (e) => {
        const rejected = e instanceof ApiError && e.status === 401;
        if (rejected) setAccessCode("");
        setUnlocked(!rejected);
      },
    );
  }, [healthKnown, authRequired]);

  const onStarted = useCallback((job: Job) => {
    setRefresh((n) => n + 1);
    navigate(`/job/${job.id}`);
  }, [navigate]);

  const onDone = useCallback((payload: CasePayload) => {
    setFresh(payload);
    setRefresh((n) => n + 1);
    navigate(`/case/${payload.report.evidence.case_id}`);
  }, [navigate]);

  const onUnlock = useCallback(() => {
    setUnlocked(true);
    setRefresh((n) => n + 1);
  }, []);

  const signOut = useCallback(() => {
    setAccessCode("");
    setUnlocked(false);
  }, []);

  const newAnalysis = useCallback(() => navigate("/"), [navigate]);

  if (healthKnown && authRequired && unlocked !== true) {
    return (
      <div className="app">
        <Header health={health} error={healthError} />
        {unlocked === false ? <AccessGate onUnlock={onUnlock} /> : <div className="center"><div className="spinner" /></div>}
      </div>
    );
  }

  return (
    <div className="app">
      <Header health={health} error={healthError} onSignOut={authRequired ? signOut : undefined} />
      <div className="body">
        <Sidebar cases={cases} jobs={jobs} activeCase={route.name === "case" ? route.id : null}
                 query={query} onQuery={setQuery} onNew={newAnalysis} />
        <main className="main">
          <ErrorBoundary key={route.name === "upload" ? "upload" : route.id}>
            {route.name === "upload" && <UploadPanel health={health} onStarted={onStarted} />}
            {route.name === "job" && <JobView jobId={route.id} onDone={onDone} onNew={newAnalysis} />}
            {route.name === "case" && <CaseView caseId={route.id} initial={fresh} />}
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
