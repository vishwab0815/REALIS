import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { CaseSummary, Health, Job } from "../types";
import { MODEL_LABELS, timeAgo, verdictTone } from "../util";

export function Header({ health, error }: { health: Health | null; error: string | null }) {
  const chips: { text: string; tone: "ok" | "warn" }[] = [];
  if (error && !health) chips.push({ text: "server unreachable", tone: "warn" });
  if (health) {
    const gpu = health.runtime.device === "cuda";
    chips.push({ text: gpu ? `GPU · ${health.runtime.gpu}` : "CPU mode (slower)", tone: gpu ? "ok" : "warn" });
    for (const [name, m] of Object.entries(health.models)) {
      const state = !m.enabled ? "off" : !m.installed ? "not installed" : m.loaded ? "ready" : "loading";
      chips.push({ text: `${MODEL_LABELS[name] ?? name} · ${state}`, tone: state === "ready" ? "ok" : "warn" });
    }
    if (!health.ffmpeg) chips.push({ text: "FFmpeg missing", tone: "warn" });
  }
  return (
    <header className="topbar">
      <a className="logo" href="#/" title="Real-media Evidence, Authenticity & Lineage Intelligence System">
        <span aria-hidden />REALIS
      </a>
      <span className="subtitle">Know what's real · image, audio &amp; video forensics</span>
      <div className="chips">
        {chips.map((c) => <span key={c.text} className={`chip ${c.tone}`}>{c.text}</span>)}
        {health && <span className="chip">v{health.version}</span>}
      </div>
    </header>
  );
}

const ICON = { image: "🖼", audio: "🎙", video: "🎬" } as const;

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
      <button className="btn wide" onClick={onNew}>+ New analysis</button>
      {jobs && jobs.length > 0 && (
        <div className="side-group">
          <div className="side-title">Running</div>
          {jobs.map((j) => (
            <a key={j.id} className="side-item" href={`#/job/${j.id}`}>
              <span className="side-name">{j.name}</span>
              <span className="side-meta">{j.status === "queued" ? "queued" : `${Math.round(j.progress * 100)}%`}</span>
              <span className="mini-progress"><span style={{ width: `${j.progress * 100}%` }} /></span>
            </a>
          ))}
        </div>
      )}
      <input className="search" type="search" placeholder="Search cases" value={query}
             onChange={(e) => onQuery(e.target.value)} aria-label="Search cases" />
      <div className="side-group scroll">
        <div className="side-title">History</div>
        {cases === null && <div className="muted side-empty">Loading…</div>}
        {cases?.length === 0 && <div className="muted side-empty">{query ? "No matching cases." : "No cases yet."}</div>}
        {cases?.map((c) => {
          const tone = verdictTone(Math.max(c.ai_generation_probability, c.editing_probability), c.category);
          return (
            <a key={c.case_id + c.sha256} href={`#/case/${c.case_id}`} className={`side-item ${c.case_id === activeCase ? "active" : ""}`}>
              <span className="side-thumb" aria-hidden>
                {c.thumbnail ? <img src={c.thumbnail} alt="" loading="lazy" /> : ICON[c.modality]}
              </span>
              <span className="side-body">
                <span className="side-name" title={c.name}>{c.name}</span>
                <span className="side-meta"><i className={`dot tone-${tone}`} />{c.label}</span>
                <span className="side-meta">{ICON[c.modality]} {timeAgo(c.generated_at)}</span>
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
            <button className="btn" onClick={() => { this.setState({ error: null }); window.location.hash = "#/"; }}>
              Back to start
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
