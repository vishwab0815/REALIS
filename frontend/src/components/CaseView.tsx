import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { CasePayload } from "../types";
import { formatBytes, isTimeBased, sortResults } from "../util";
import { IconExternal, IconShield, MODALITY_ICON } from "./Icons";
import { MediaStage, type StageHandle } from "./MediaStage";
import { Modal } from "./Modal";
import { AnalyzerDetails, CheckList, EvidenceDetails, KeyFindings, VerdictDetails, VerdictSummary, modalityLabel } from "./Results";

type Dialog =
  | { kind: "analyzer"; name: string }
  | { kind: "verdict" }
  | { kind: "evidence" }
  | { kind: "figure"; label: string; url: string };

export function CaseView({ caseId, initial }: { caseId: string; initial?: CasePayload | null }) {
  const [payload, setPayload] = useState<CasePayload | null>(initial ?? null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const stage = useRef<StageHandle>(null);
  const close = useCallback(() => setDialog(null), []);

  useEffect(() => {
    setDialog(null);
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
  if (!payload) return <div className="center"><div className="spinner" aria-label="Loading case" /></div>;

  const { report, urls } = payload;
  const results = sortResults(report.results);
  const ModalityIcon = MODALITY_ICON[report.modality];
  // Seeking closes the dialog so the player is visible at the chosen moment.
  const seek = isTimeBased(report.modality) ? (t: number) => { setDialog(null); stage.current?.seek(t); } : undefined;
  const selected = dialog?.kind === "analyzer" ? results.find((r) => r.analyzer === dialog.name) : undefined;
  const intact = report.integrity_verified && report.custody_log_valid;

  return (
    <div className="case">
      <header className="case-head">
        <span className="case-icon"><ModalityIcon size={18} /></span>
        <div className="case-title">
          <h1 title={report.evidence.original_name}>{report.evidence.original_name}</h1>
          <p>{modalityLabel(report)} · {formatBytes(report.evidence.size_bytes)} · {new Date(report.generated_at).toLocaleString()}</p>
        </div>
        <div className="case-actions">
          <button className={`btn ghost ${intact ? "" : "danger"}`} onClick={() => setDialog({ kind: "evidence" })}>
            <IconShield size={15} /> {intact ? "Evidence sealed" : "Integrity problem"}
          </button>
          <a className="btn secondary" href={urls.html} target="_blank" rel="noreferrer">Report <IconExternal size={14} /></a>
        </div>
      </header>

      <div className="case-grid">
        <section className="panel case-media" aria-label="Media">
          <MediaStage ref={stage} payload={payload} onFigure={(label, url) => setDialog({ kind: "figure", label, url })} />
        </section>
        <section className="case-results" aria-label="Findings">
          <VerdictSummary verdict={report.verdict} onExplain={() => setDialog({ kind: "verdict" })} />
          {report.notes.length > 0 && <p className="notice">{report.notes[0]}{report.notes.length > 1 && ` (+${report.notes.length - 1} more)`}</p>}
          <KeyFindings results={results} onOpen={(name) => setDialog({ kind: "analyzer", name })} />
          <CheckList results={results} onOpen={(name) => setDialog({ kind: "analyzer", name })} />
        </section>
      </div>

      {dialog?.kind === "verdict" && (
        <Modal title="Why this verdict?" onClose={close}><VerdictDetails verdict={report.verdict} notes={report.notes} /></Modal>
      )}
      {dialog?.kind === "evidence" && (
        <Modal title="Evidence & chain of custody" onClose={close}><EvidenceDetails payload={payload} /></Modal>
      )}
      {dialog?.kind === "figure" && (
        <Modal title={dialog.label} size="lg" onClose={close}><img className="figure-full" src={dialog.url} alt={dialog.label} /></Modal>
      )}
      {selected && (
        <Modal title={selected.title || selected.analyzer} subtitle={selected.status === "ok" ? undefined : selected.status}
               size="lg" onClose={close}>
          <AnalyzerDetails result={selected} caseId={report.evidence.case_id} figures={urls.artifacts[selected.analyzer] ?? {}}
                           onSeek={seek} onFigure={(label, url) => setDialog({ kind: "figure", label, url })} />
        </Modal>
      )}
    </div>
  );
}
