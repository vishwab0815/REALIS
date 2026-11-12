import { Component, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { CaseSummary, Health, Job } from "../types";
import { MODEL_LABELS, timeAgo, verdictTone } from "../util";
import { IconPlus, IconSearch, LogoMark, MODALITY_ICON } from "./Icons";
import { Modal } from "./Modal";

type Status = { tone: "ok" | "warn" | "bad"; text: string };

function systemStatus(health: Health | null, error: string | null): Status {
  if (!health) return error ? { tone: "bad", text: "Server offline" } : { tone: "warn", text: "Connecting…" };
  const models = Object.values(health.models).filter((m) => m.enabled);
  if (!health.ffmpeg || models.some((m) => !m.installed)) return { tone: "warn", text: "Setup incomplete" };
  if (models.some((m) => !m.loaded)) return { tone: "warn", text: "Loading models…" };
  return { tone: "ok", text: health.runtime.device === "cuda" ? "Ready · GPU" : "Ready · CPU" };
}

function StatusDetails({ health, onSignOut }: { health: Health; onSignOut?: () => void }) {
  const rows: [string, string, boolean][] = [
    ["Compute", health.runtime.device === "cuda" ? `GPU · ${health.runtime.gpu}` : "CPU (slower)", true],
    ["FFmpeg (audio & video)", health.ffmpeg ? "Installed" : "Missing", health.ffmpeg],
    ...Object.entries(health.models).map(([name, m]): [string, string, boolean] => [
      `${MODEL_LABELS[name] ?? name} model`,
      !m.enabled ? "Disabled" : !m.installed ? "Not installed: run realis setup-models" : m.loaded ? "Ready" : "Loading",
      !m.enabled || (m.installed && m.loaded),
    ]),
  ];
  return (
    <div className="stack">
      <ul className="status-list">
        {rows.map(([label, value, ok]) => (
          <li key={label}><span className={`dot ${ok ? "tone-ok" : "tone-warn"}`} /><span>{label}</span><b>{value}</b></li>
        ))}
      </ul>
      <p className="fine-print">REALIS v{health.version} · uploads up to {health.limits.max_upload_mb} MB · audio and video
        analysed up to {Math.round(health.limits.max_analysis_seconds / 60)} minutes.</p>
      {onSignOut && <button className="btn secondary" onClick={onSignOut}>Sign out of this workspace</button>}
    </div>
  );
}

export function Header({ health, error, onSignOut }: { health: Health | null; error: string | null; onSignOut?: () => void }) {
  const [open, setOpen] = useState(false);
  const status = systemStatus(health, error);
  return (
    <header className="topbar">
      <a className="brand" href="#/" title="Real-media Evidence, Authenticity & Lineage Intelligence System">
        <LogoMark />
        <span className="wordmark">REALIS</span>
      </a>
      <span className="tagline">Know what's real</span>
      <button className={`status-pill tone-${status.tone}`} onClick={() => health && setOpen(true)} disabled={!health}
              aria-label={`System status: ${status.text}`}>
        <span className="dot" />{status.text}
      </button>
      {open && health && <Modal title="System status" onClose={() => setOpen(false)}>
        <StatusDetails health={health} onSignOut={onSignOut && (() => { setOpen(false); onSignOut(); })} />
      </Modal>}
    </header>
  );
}

const SHORT_VERDICT = { ok: "No issues found", warn: "Inconclusive", ai: "AI signals", bad: "Manipulation" } as const;

interface SidebarProps {
  cases: CaseSummary[] | null;
  jobs: Job[] | null;
  activeCase: string | null;
  query: string;
  onQuery: (q: string) => void;
  onNew: () => void;
}

export function Sidebar({ cases, jobs, activeCase, query, onQuery, onNew }: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="Cases">
      <button className="btn primary wide" onClick={onNew}><IconPlus size={16} /> New analysis</button>

      {jobs && jobs.length > 0 && (
        <div className="side-section">
          <div className="side-title">In progress</div>
          {jobs.map((j) => (
            <a key={j.id} className="job-chip" href={`#/job/${j.id}`}>
              <span className="side-name">{j.name}</span>
              <span className="side-meta">{j.status === "queued" ? "Queued" : `${Math.round(j.progress * 100)}%`}</span>
              <span className="mini-progress"><span style={{ width: `${j.progress * 100}%` }} /></span>
            </a>
          ))}
        </div>
      )}

      <label className="search">
        <IconSearch size={15} />
        <input type="search" placeholder="Search cases" value={query} onChange={(e) => onQuery(e.target.value)}
               aria-label="Search cases" />
      </label>

      <div className="side-section scroll">
        <div className="side-title">Recent cases {cases && cases.length > 0 && <span className="count">{cases.length}</span>}</div>
        {cases === null && <div className="side-empty">Loading…</div>}
        {cases?.length === 0 && <div className="side-empty">{query ? "No matching cases." : "Your analysed files will appear here."}</div>}
        {cases?.map((c) => {
          const tone = verdictTone(Math.max(c.ai_generation_probability, c.editing_probability), c.category);
          const Icon = MODALITY_ICON[c.modality];
          return (
            <a key={c.case_id + c.sha256} href={`#/case/${c.case_id}`} className={`case-item ${c.case_id === activeCase ? "active" : ""}`}>
              <span className="case-thumb" aria-hidden>
                {c.thumbnail ? <img src={c.thumbnail} alt="" loading="lazy" /> : <Icon size={18} />}
              </span>
              <span className="case-body">
                <span className="side-name" title={c.name}>{c.name}</span>
                <span className="case-meta">
                  <span className={`badge small tone-${tone}`} title={c.label}>{SHORT_VERDICT[tone]}</span>
                  <span className="when">{timeAgo(c.generated_at)}</span>
                </span>
              </span>
            </a>
          );
        })}
      </div>
    </aside>
  );
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="center">
          <div className="card error-box" role="alert">
            <b>Something went wrong displaying this view.</b>
            <p>{this.state.error.message}</p>
            <button className="btn primary" onClick={() => { this.setState({ error: null }); window.location.hash = "#/"; }}>
              Back to start
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
