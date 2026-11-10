import { useCallback, useState } from "react";
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
  const { cases } = useCases(query, refresh);
  const { value: jobs } = useActiveJobs(refresh);
  // The just-finished result, so opening it does not need another request.
  const [fresh, setFresh] = useState<CasePayload | null>(null);

  const onStarted = useCallback((job: Job) => {
    setRefresh((n) => n + 1);
    navigate(`/job/${job.id}`);
  }, [navigate]);

  const onDone = useCallback((payload: CasePayload) => {
    setFresh(payload);
    setRefresh((n) => n + 1);
    navigate(`/case/${payload.report.evidence.case_id}`);
  }, [navigate]);

  const newAnalysis = useCallback(() => navigate("/"), [navigate]);

  return (
    <div className="app">
      <Header health={health} error={healthError} />
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
