import { useEffect, useState } from "react";
import { useJob } from "../hooks";
import type { CasePayload } from "../types";
import { formatBytes, formatTime } from "../util";

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
        <div className="card error-box"><b>Job unavailable</b><p>{error}</p>
          <button className="btn" onClick={onNew}>New analysis</button></div>
      </div>
    );
  }
  if (!job) return <div className="center muted">Connecting…</div>;

  const started = job.started_at ? new Date(job.started_at).getTime() : null;
  const elapsed = started ? (now - started) / 1000 : 0;
  return (
    <div className="center">
      <div className="card job" aria-live="polite">
        <div className="kicker">{job.deep ? "Deep scan" : "Quick scan"} · {formatBytes(job.size_bytes)}</div>
        <h2 className="job-name">{job.name}</h2>
        {job.status === "error" ? (
          <>
            <div className="error-box card" role="alert"><b>Analysis failed</b><p>{job.error}</p></div>
            <button className="btn" onClick={onNew}>Analyse another file</button>
          </>
        ) : (
          <>
            <div className="progress big-progress"><span style={{ width: `${Math.max(2, job.progress * 100)}%` }} /></div>
            <div className="job-stage">
              <span>{job.status === "queued" ? `Queued${job.queue_position ? ` · ${job.queue_position} ahead` : ""}` : job.stage}</span>
              <span>{Math.round(job.progress * 100)}%{started ? ` · ${formatTime(elapsed)}` : ""}</span>
            </div>
            <p className="muted small-text">
              The first analysis after start-up also loads the AI models. You can leave this page: the job keeps
              running and appears in the history when it is done.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
