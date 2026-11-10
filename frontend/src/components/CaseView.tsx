import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { CasePayload } from "../types";
import { isTimeBased, sortResults } from "../util";
import { MediaStage, type StageHandle } from "./MediaStage";
import { AnalyzerCard, EvidenceCard, VerdictCard } from "./Results";

export function CaseView({ caseId, initial }: { caseId: string; initial?: CasePayload | null }) {
  const [payload, setPayload] = useState<CasePayload | null>(initial ?? null);
  const [error, setError] = useState<string | null>(null);
  const stage = useRef<StageHandle>(null);

  useEffect(() => {
    if (initial && initial.report.evidence.case_id === caseId) {
      setPayload(initial);
      return;
    }
    const ctl = new AbortController();
    setPayload(null);
    setError(null);
    api.case(caseId, ctl.signal).then(
      (c) => setPayload(c.items[0] ?? null),
      (e) => !ctl.signal.aborted && setError(e instanceof Error ? e.message : String(e)),
    );
    return () => ctl.abort();
  }, [caseId, initial]);

  if (error) return <div className="center"><div className="card error-box"><b>Could not open case</b><p>{error}</p></div></div>;
  if (!payload) return <div className="center muted">Loading case…</div>;

  const { report } = payload;
  const seek = isTimeBased(report.modality) ? (t: number) => stage.current?.seek(t) : undefined;
  const results = sortResults(report.results);
  return (
    <div className="case">
      <section className="panel case-media" aria-label="Media">
        <MediaStage ref={stage} payload={payload} />
      </section>
      <section className="panel case-results" aria-label="Findings">
        <VerdictCard verdict={report.verdict} notes={report.notes} />
        <EvidenceCard payload={payload} />
        <div className="section-title">Analyzers ({results.length})</div>
        {results.map((r) => <AnalyzerCard key={r.analyzer} result={r} onSeek={seek} />)}
      </section>
    </div>
  );
}
