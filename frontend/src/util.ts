import type { AnalyzerResult, Category, FrameSample, Modality, Report, Series, Severity, TimelineEvent } from "./types";

export const SEVERITY_RANK: Record<Severity, number> = { info: 0, low: 1, medium: 2, high: 3, critical: 4 };

/** Display order of analyzers: strongest evidence types first, visual aids last. */
const ORDER = [
  "c2pa_provenance", "ai_generated", "frame_ai", "synthetic_voice", "trufor", "frame_trufor", "enf",
  "temporal_edits", "edit_discontinuity", "copy_move", "metadata", "video_metadata", "audio_metadata",
  "jpeg_structure", "bandwidth", "ela", "noise_inconsistency",
];

export function sortResults(results: AnalyzerResult[]): AnalyzerResult[] {
  const rank = (r: AnalyzerResult) => {
    const i = ORDER.indexOf(r.analyzer);
    return (r.status === "ok" ? 0 : 100) + (i < 0 ? 50 : i);
  };
  return [...results].sort((a, b) => rank(a) - rank(b));
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function formatBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

/** 75.4 -> "1:15.4"; 3725 -> "1:02:05" */
export function formatTime(seconds: number, precise = false): string {
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = s % 60;
  const sec = precise ? rest.toFixed(1).padStart(4, "0") : String(Math.floor(rest)).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

export function timeAgo(iso: string, now = Date.now()): string {
  const secs = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

/** Colour of a verdict: green when clear, amber when unsure, purple for AI, red for edits. */
export function verdictTone(probability: number, category: Category): "ok" | "warn" | "ai" | "bad" {
  if (probability < 0.45) return "ok";
  if (probability < 0.6 || category === "none") return "warn";
  return category === "synthesis" ? "ai" : "bad";
}

export interface TimelineData {
  duration: number;
  series: Series[];
  events: TimelineEvent[];
  frames: FrameSample[];
}

/** Everything a time-based viewer needs, gathered from all successful analyzers. */
export function timelineData(report: Report): TimelineData {
  const ok = report.results.filter((r) => r.status === "ok");
  const series = ok.flatMap((r) => r.data.series ?? []).filter((s) => s.points.length > 0);
  const events = ok.flatMap((r) => r.data.events ?? []);
  const frames = ok.flatMap((r) => r.data.frames ?? []);
  const declared = ok
    .map((r) => r.data.duration_s)
    .find((d): d is number => typeof d === "number" && d > 0);
  const latest = Math.max(
    0,
    ...series.flatMap((s) => s.points.map(([t]) => t)),
    ...events.map((e) => e.end ?? e.time),
    ...frames.map((f) => f.time),
  );
  return { duration: declared ?? latest, series, events, frames };
}

export const isTimeBased = (m: Modality) => m === "audio" || m === "video";

export function modalityOf(fileName: string, types: Record<Modality, string[]>): Modality | null {
  const dot = fileName.lastIndexOf(".");
  const ext = dot >= 0 ? fileName.slice(dot).toLowerCase() : "";
  return (Object.keys(types) as Modality[]).find((m) => types[m].includes(ext)) ?? null;
}

export const MODEL_LABELS: Record<string, string> = {
  ai_generated: "Image AI", trufor: "TruFor", synthetic_voice: "Voice AI",
};

export const EVENT_COLORS: Record<string, string> = {
  synthetic: "var(--ai)", enf: "var(--bad)", silence: "var(--warn)", noise: "var(--warn)",
  cut: "var(--accent)", duplicate: "var(--warn)",
};

export const SERIES_COLORS: Record<string, string> = {
  "AI frames": "var(--ai)", "AI voice": "#e070c0", TruFor: "var(--bad)",
};
