import type { AnalyzerResult, CasePayload, Verdict } from "../types";
import { SEVERITY_RANK, formatBytes, formatTime, pct, verdictTone } from "../util";

// Bulky analyzer data the details panel should not dump.
const HIDDEN_DATA = new Set([
  "manifest_store", "exiftool", "quantization_tables", "traceback", "text_chunks", "timeline", "events",
  "series", "frames", "tags",
]);

export function Meter({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="meter-row" title={hint}>
      <div className="meter-head">
        <span>{label}</span>
        <b>{pct(value)}</b>
      </div>
      <div className="meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={Math.round(value * 100)}>
        <i style={{ left: `${Math.min(100, Math.max(0, value * 100))}%` }} />
      </div>
    </div>
  );
}

const CATEGORY_TEXT = { synthesis: "AI generation", manipulation: "Manipulation", none: "No strong signal" };

export function VerdictCard({ verdict, notes }: { verdict: Verdict; notes: string[] }) {
  const tone = verdictTone(verdict.manipulation_probability, verdict.category);
  return (
    <section className={`card verdict tone-${tone}`} aria-label="Verdict">
      <div className="kicker">
        Verdict
        <span className={`tag cat-${verdict.category}`}>{CATEGORY_TEXT[verdict.category]}</span>
        {verdict.decisive && <span className="tag provenance">provenance evidence</span>}
      </div>
      <h2 className={`verdict-label tone-${tone}`}>{verdict.label}</h2>
      <Meter label="AI generation" value={verdict.ai_generation_probability} hint="Was the whole file synthesised by AI?" />
      <Meter label="Editing / manipulation" value={verdict.editing_probability} hint="Was real media altered or re-processed?" />
      <div className="meter-scale"><span>authentic signals</span><span>inconclusive</span><span>suspicious</span></div>
      <ul className="rationale">{verdict.rationale.map((line) => <li key={line}>{line}</li>)}</ul>
      {notes.map((n) => <p key={n} className="note warn">Note: {n}</p>)}
      <p className="note">
        Scores are heuristic and not yet calibrated on a labelled benchmark. No detector catches every
        generator: absence of evidence is not proof of authenticity.
      </p>
    </section>
  );
}

export function EvidenceCard({ payload }: { payload: CasePayload }) {
  const { report, urls } = payload;
  const ev = report.evidence;
  return (
    <section className="card" aria-label="Evidence">
      <dl className="facts">
        <dt>Case</dt><dd><code>{ev.case_id}</code></dd>
        <dt>File</dt><dd>{ev.original_name}</dd>
        <dt>SHA-256</dt><dd><code className="hash">{ev.sha256}</code></dd>
        <dt>Size</dt><dd>{formatBytes(ev.size_bytes)}</dd>
        <dt>Integrity</dt>
        <dd className={report.integrity_verified ? "good" : "bad"}>
          {report.integrity_verified ? "✓ Hash re-verified after analysis" : "✗ Hash mismatch"}
        </dd>
        <dt>Custody log</dt>
        <dd className={report.custody_log_valid ? "good" : "bad"}>
          {report.custody_log_valid ? "✓ Hash chain intact" : "✗ Chain broken"}
        </dd>
      </dl>
      <div className="links">
        <a href={urls.html} target="_blank" rel="noreferrer">Full report ↗</a>
        <a href={urls.json} target="_blank" rel="noreferrer">JSON ↗</a>
        {urls.evidence && <a href={urls.evidence} target="_blank" rel="noreferrer">Evidence copy ↗</a>}
      </div>
    </section>
  );
}

export function AnalyzerCard({ result, onSeek }: { result: AnalyzerResult; onSeek?: (t: number) => void }) {
  const r = result;
  if (r.status !== "ok") {
    return (
      <article className={`card analyzer muted-card`}>
        <header><span className="an-title">{r.title || r.analyzer}</span><span className="an-meta">{r.status}</span></header>
        <p className="an-detail">{r.error}</p>
      </article>
    );
  }
  const score = r.score ?? 0.5;
  const tone = r.confidence === 0 ? "none" : score < 0.45 ? "ok" : score < 0.6 ? "warn" : r.evidence_kind === "synthesis" ? "ai" : "bad";
  const findings = [...r.findings].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity]);
  const events = r.data.events ?? [];
  const details = Object.fromEntries(Object.entries(r.data).filter(([k]) => !HIDDEN_DATA.has(k)));
  return (
    <article className="card analyzer">
      <header>
        <span className="an-title">{r.title || r.analyzer}</span>
        <span className="an-meta">{r.confidence === 0 ? "no signal" : `score ${pct(score)} · conf ${pct(r.confidence)}`}</span>
      </header>
      <div className="bar"><span className={`fill tone-${tone}`} style={{ width: `${Math.max(3, score * 100)}%` }} /></div>
      {findings.map((f, i) => (
        <div className="finding" key={i}>
          <span className={`sev sev-${f.severity}`}>{f.severity}</span>
          <span>{f.title}{f.detail && <span className="an-detail"> — {f.detail}</span>}</span>
        </div>
      ))}
      {onSeek && events.length > 0 && (
        <div className="chips-row">
          {events.slice(0, 12).map((e, i) => (
            <button key={i} className="seek-chip" onClick={() => onSeek(e.time)} title={`Jump to ${formatTime(e.time, true)}`}>
              ▶ {e.label ?? e.kind} · {formatTime(e.time, true)}
            </button>
          ))}
        </div>
      )}
      <details>
        <summary>Details · {r.elapsed_ms} ms</summary>
        {r.limitations.length > 0 && <ul className="limits">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>}
        <pre>{JSON.stringify(details, null, 2)}</pre>
      </details>
    </article>
  );
}
