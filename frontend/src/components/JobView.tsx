import { useEffect, useState } from "react";
import { useJob } from "../hooks";
import type { CasePayload } from "../types";
import { formatBytes, formatTime } from "../util";
import { IconAlert, IconFile } from "./Icons";

interface Props {
  jobId: string;
  onDone: (payload: CasePayload) => void;
  onNew: () => void;
}

export function JobView({ jobId, onDone, onNew }: Props) {
  const { value: job, error } = useJob(jobId);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, []);
  useEffect(() => {
    if (job?.status === "done" && job.result) onDone(job.result);
  }, [job, onDone]);

  if (error && !job) {
    return (
      <div className="center">
        <div className="card job">
          <span className="job-icon bad"><IconAlert size={22} /></span>
          <h2>Job unavailable</h2>
          <p className="muted">{error}</p>
          <button className="btn primary" onClick={onNew}>New analysis</button>
        </div>
      </div>
    );
  }
  if (!job) return <div className="center"><div className="spinner" aria-label="Connecting" /></div>;

  const started = job.started_at ? new Date(job.started_at).getTime() : null;
  const elapsed = started ? (now - started) / 1000 : 0;
  // Stages read "Analyzer · detail"; show the analyzer as the step and the rest as detail.
  const [step, detail] = job.stage.split(" · ");
  return (
    <div className="center">
      <div className="card job" aria-live="polite">
        {job.status === "error" ? (
          <>
            <span className="job-icon bad"><IconAlert size={22} /></span>
            <h2>Analysis failed</h2>
            <p className="muted job-name">{job.name}</p>
            <div className="card error-box" role="alert">{job.error}</div>
            <button className="btn primary" onClick={onNew}>Analyse another file</button>
          </>
        ) : (
          <>
            <span className="job-icon"><IconFile size={22} /></span>
            <h2>{job.status === "queued" ? "Waiting in queue" : "Analysing"}</h2>
            <p className="muted job-name">{job.name} · {formatBytes(job.size_bytes)} · {job.deep ? "Deep scan" : "Quick scan"}</p>
            <div className="progress big"><span style={{ width: `${Math.max(2, job.progress * 100)}%` }} /></div>
            <div className="job-stage">
              <span>
                {job.status === "queued" ? `${job.queue_position || "No"} job${job.queue_position === 1 ? "" : "s"} ahead` : step}
                {detail && <small> · {detail}</small>}
              </span>
              <span className="tabular">{Math.round(job.progress * 100)}%{started ? ` · ${formatTime(elapsed)}` : ""}</span>
            </div>
            <p className="fine-print">You can leave this page; the result appears in Recent cases when it is ready.</p>
          </>
        )}
      </div>
    </div>
  );
}
