import { asset } from "../api";
import type { AnalyzerResult, CasePayload, Finding, Report, Verdict } from "../types";
import { SEVERITY_RANK, formatBytes, formatTime, pct, verdictTone } from "../util";
import { IconAlert, IconCheck, IconChevron, IconExternal, IconInfo, IconPlay, IconShield } from "./Icons";

// Bulky analyzer data that the technical-details panel should not dump.
const HIDDEN_DATA = new Set([
  "manifest_store", "exiftool", "quantization_tables", "traceback", "text_chunks", "timeline", "events",
  "series", "frames", "tags",
]);

const CATEGORY_TEXT = { synthesis: "AI generation", manipulation: "Manipulation", none: "No strong signal" };

export type Tone = "ok" | "warn" | "ai" | "bad" | "none";

export function resultTone(r: AnalyzerResult): Tone {
  if (r.status !== "ok" || r.confidence === 0) return "none";
  const s = r.score ?? 0.5;
  if (s < 0.45) return "ok";
  if (s < 0.6) return "warn";
  return r.evidence_kind === "synthesis" ? "ai" : "bad";
}

export function topFinding(r: AnalyzerResult): Finding | null {
  return [...r.findings].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity])[0] ?? null;
}

/** Significant findings (medium and above) across all checks, most severe first. */
export function keyFindings(results: AnalyzerResult[], limit = 3) {
  return results
    .filter((r) => r.status === "ok")
    .flatMap((r) => r.findings.map((f) => ({ result: r, finding: f })))
    .filter(({ finding }) => SEVERITY_RANK[finding.severity] >= SEVERITY_RANK.medium)
    .sort((a, b) => SEVERITY_RANK[b.finding.severity] - SEVERITY_RANK[a.finding.severity])
    .slice(0, limit);
}

function ToneIcon({ tone }: { tone: Tone }) {
  if (tone === "ok") return <IconCheck size={15} />;
  if (tone === "none") return <IconInfo size={15} />;
  return <IconAlert size={15} />;
}

/* ------------------------------------------------------------------ summary */

function ScoreRing({ value, tone }: { value: number; tone: Tone }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  return (
    <div className={`ring tone-${tone}`} role="img" aria-label={`Risk ${pct(value)}`}>
      <svg width="84" height="84" viewBox="0 0 84 84">
        <circle cx="42" cy="42" r={r} className="ring-track" />
        <circle cx="42" cy="42" r={r} className="ring-value" strokeDasharray={`${value * c} ${c}`} transform="rotate(-90 42 42)" />
      </svg>
      <div className="ring-text"><b>{Math.round(value * 100)}</b><span>risk</span></div>
    </div>
  );
}

export function Meter({ label, value }: { label: string; value: number }) {
  const tone: Tone = value < 0.45 ? "ok" : value < 0.6 ? "warn" : "bad";
  return (
    <div className="meter-row">
      <div className="meter-head"><span>{label}</span><b>{pct(value)}</b></div>
      <div className="meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={Math.round(value * 100)}>
        <span className={`meter-fill tone-${tone}`} style={{ width: `${Math.max(2, value * 100)}%` }} />
      </div>
    </div>
  );
}

export function VerdictSummary({ verdict, notes = [], onExplain }: { verdict: Verdict; notes?: string[]; onExplain: () => void }) {
  const tone = verdictTone(verdict.manipulation_probability, verdict.category);
  return (
    <section className={`card verdict tone-${tone}`} aria-label="Verdict">
      <div className="verdict-top">
        <ScoreRing value={verdict.manipulation_probability} tone={tone} />
        <div className="verdict-text">
          <div className="badges">
            <span className={`badge tone-${tone}`}>{CATEGORY_TEXT[verdict.category]}</span>
            {verdict.decisive && <span className="badge tone-info">Provenance evidence</span>}
          </div>
          <h2 className="verdict-label">{verdict.label}</h2>
          <button className="link-btn" onClick={onExplain}>Why this verdict? <IconChevron size={14} /></button>
        </div>
      </div>
      <div className="meters">
        <Meter label="AI generation" value={verdict.ai_generation_probability} />
        <Meter label="Editing / manipulation" value={verdict.editing_probability} />
      </div>
      {notes.length > 0 && (
        <ul className="verdict-notes">
          {notes.map((n) => <li key={n}><IconInfo size={13} /> {n}</li>)}
        </ul>
      )}
    </section>
  );
}

/** The significant findings; renders nothing when there are none (the check list says so instead). */
export function KeyFindings({ results, onOpen }: { results: AnalyzerResult[]; onOpen: (name: string) => void }) {
  const items = keyFindings(results);
  if (items.length === 0) return null;
  return (
    <section className="card" aria-label="Key findings">
      <h3 className="card-title">Key findings</h3>
      <ul className="key-list">
        {items.map(({ result, finding }, i) => (
          <li key={i}>
            <button className="key-item" onClick={() => onOpen(result.analyzer)}>
              <span className={`sev-dot sev-${finding.severity}`} />
              <span className="key-text"><b>{finding.title}</b><small>{result.title}</small></span>
              <IconChevron size={15} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CheckList({ results, onOpen }: { results: AnalyzerResult[]; onOpen: (name: string) => void }) {
  const clear = keyFindings(results).length === 0;
  return (
    <section className="card checks" aria-label="Checks">
      <h3 className="card-title">Checks <span className="count">{results.length}</span></h3>
      {clear && <p className="empty-line"><IconCheck size={15} /> No significant findings across {results.length} checks.</p>}
      <ul>
        {results.map((r) => {
          const tone = resultTone(r);
          const top = topFinding(r);
          return (
            <li key={r.analyzer}>
              <button className={`check-row ${r.status !== "ok" ? "dim" : ""}`} onClick={() => onOpen(r.analyzer)}
                      aria-label={`${r.title}: details`}>
                <span className={`check-icon tone-${tone}`}><ToneIcon tone={tone} /></span>
                <span className="check-body">
                  <span className="check-title">{r.title || r.analyzer}</span>
                  <span className="check-sub">{r.status === "ok" ? top?.title ?? "No findings" : r.status === "skipped" ? `Skipped · ${r.error}` : "Error"}</span>
                </span>
                {r.status === "ok" && r.confidence > 0 && (
                  <span className="check-score">
                    <span className="mini-bar"><span className={`tone-${tone}`} style={{ width: `${Math.max(4, (r.score ?? 0) * 100)}%` }} /></span>
                  </span>
                )}
                <IconChevron size={15} />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------- modal bodies */

export function VerdictDetails({ verdict, notes }: { verdict: Verdict; notes: string[] }) {
  return (
    <div className="stack">
      <p className="lead">{verdict.label}</p>
      <div>
        <h4 className="sub-title">What drove this verdict</h4>
        <ul className="plain-list">{verdict.rationale.map((line) => <li key={line}>{line}</li>)}</ul>
      </div>
      {notes.length > 0 && (
        <div>
          <h4 className="sub-title">Notes</h4>
          <ul className="plain-list">{notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      )}
      <p className="fine-print">
        Scores are heuristic and not yet calibrated on a labelled benchmark. No detector catches every generator:
        absence of evidence is not proof of authenticity. A "strong" verdict needs two independent checks or signed provenance.
      </p>
    </div>
  );
}

interface AnalyzerDetailsProps {
  result: AnalyzerResult;
  caseId: string;
  figures: Record<string, string>;
  onSeek?: (t: number) => void;
  onFigure: (label: string, url: string) => void;
}

export function AnalyzerDetails({ result: r, caseId, figures, onSeek, onFigure }: AnalyzerDetailsProps) {
  if (r.status !== "ok") {
    return <p className="lead">{r.status === "skipped" ? `This check did not run: ${r.error}.` : `This check failed: ${r.error}`}</p>;
  }
  const tone = resultTone(r);
  const findings = [...r.findings].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity]);
  const events = r.data.events ?? [];
  const frames = r.data.frames ?? [];
  const details = Object.fromEntries(Object.entries(r.data).filter(([k]) => !HIDDEN_DATA.has(k)));
  return (
    <div className="stack">
      {r.confidence > 0 && (
        <div className="stat-row">
          <div className="stat"><span>Score</span><b className={`tone-text-${tone}`}>{pct(r.score ?? 0)}</b></div>
          <div className="stat"><span>Confidence</span><b>{pct(r.confidence)}</b></div>
          <div className="stat"><span>Weight</span><b>{r.weight}</b></div>
          <div className="stat"><span>Time</span><b>{r.elapsed_ms < 1000 ? `${Math.round(r.elapsed_ms)} ms` : `${(r.elapsed_ms / 1000).toFixed(1)} s`}</b></div>
        </div>
      )}
      <ul className="finding-list">
        {findings.map((f, i) => (
          <li key={i}>
            <span className={`sev sev-${f.severity}`}>{f.severity}</span>
            <div><b>{f.title}</b>{f.detail && <p>{f.detail}</p>}</div>
          </li>
        ))}
      </ul>
      {onSeek && events.length > 0 && (
        <div>
          <h4 className="sub-title">Jump to moment</h4>
          <div className="chip-row">
            {events.slice(0, 16).map((e, i) => (
              <button key={i} className="seek-chip" onClick={() => onSeek(e.time)}>
                <IconPlay size={11} /> {e.label ?? e.kind} · {formatTime(e.time, true)}
              </button>
            ))}
          </div>
        </div>
      )}
      {Object.keys(figures).length > 0 && (
        <div>
          <h4 className="sub-title">Figures</h4>
          <div className="figure-grid">
            {Object.entries(figures).map(([label, url]) => (
              <button key={url} className="figure-tile" onClick={() => onFigure(label, url)}>
                <img src={url} alt={label} loading="lazy" /><span>{label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {frames.length > 0 && onSeek && (
        <div>
          <h4 className="sub-title">Sampled frames</h4>
          <div className="figure-grid small">
            {frames.map((f) => (
              <button key={f.path} className="figure-tile" onClick={() => onSeek(f.time)}>
                <img src={asset(`/cases/${caseId}/${f.path}`)} alt="" loading="lazy" />
                <span>{formatTime(f.time)} · {pct(f.probability)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {r.limitations.length > 0 && (
        <div>
          <h4 className="sub-title">Limitations</h4>
          <ul className="plain-list muted">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}
      <details className="tech">
        <summary>Technical data</summary>
        <pre>{JSON.stringify(details, null, 2)}</pre>
      </details>
    </div>
  );
}

export function EvidenceDetails({ payload }: { payload: CasePayload }) {
  const { report, urls } = payload;
  const ev = report.evidence;
  return (
    <div className="stack">
      <div className={`integrity ${report.integrity_verified && report.custody_log_valid ? "ok" : "bad"}`}>
        <IconShield size={20} />
        <div>
          <b>{report.integrity_verified && report.custody_log_valid ? "Evidence intact" : "Integrity problem"}</b>
          <p>{report.integrity_verified ? "SHA-256 re-verified after analysis." : "Hash mismatch after analysis."}{" "}
            {report.custody_log_valid ? "Custody log hash chain intact." : "Custody log chain broken."}</p>
        </div>
      </div>
      <dl className="facts">
        <dt>Case</dt><dd><code>{ev.case_id}</code></dd>
        <dt>File</dt><dd>{ev.original_name}</dd>
        <dt>Size</dt><dd>{formatBytes(ev.size_bytes)}</dd>
        <dt>SHA-256</dt><dd><code className="hash">{ev.sha256}</code></dd>
        <dt>Ingested</dt><dd>{new Date(ev.ingested_at).toLocaleString()}</dd>
        <dt>Analysed by</dt><dd>{report.tool.toUpperCase()} v{report.tool_version}</dd>
      </dl>
      <div className="btn-row">
        <a className="btn secondary" href={urls.html} target="_blank" rel="noreferrer">Full report <IconExternal size={14} /></a>
        <a className="btn secondary" href={urls.json} target="_blank" rel="noreferrer">JSON <IconExternal size={14} /></a>
        {urls.evidence && <a className="btn secondary" href={urls.evidence} target="_blank" rel="noreferrer">Evidence copy <IconExternal size={14} /></a>}
      </div>
    </div>
  );
}

export const modalityLabel = (r: Report) => ({ image: "Image", audio: "Audio", video: "Video" })[r.modality];
