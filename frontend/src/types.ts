// Mirrors realis.core.models and the server's JSON payloads.

export type Modality = "image" | "audio" | "video";
export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type Category = "synthesis" | "manipulation" | "none";
export type EvidenceKind = "provenance" | "synthesis" | "manipulation" | "processing";

export interface Finding {
  severity: Severity;
  title: string;
  detail: string;
}

/** A probability curve over time, emitted by time-based analyzers. */
export interface Series {
  name: string;
  points: [number, number][];
}

/** A marked moment or span on the timeline (cut, ENF break, AI segment...). */
export interface TimelineEvent {
  time: number;
  end?: number | null;
  kind: string;
  label?: string;
}

export interface FrameSample {
  time: number;
  path: string;
  probability: number;
}

export interface AnalyzerResult {
  analyzer: string;
  title: string;
  version: string;
  status: "ok" | "skipped" | "error";
  evidence_kind: EvidenceKind;
  score: number | null;
  confidence: number;
  weight: number;
  decisive_label: string | null;
  findings: Finding[];
  artifacts: Record<string, string>;
  data: Record<string, unknown> & { series?: Series[]; events?: TimelineEvent[]; frames?: FrameSample[] };
  limitations: string[];
  elapsed_ms: number;
  error: string | null;
}

export interface Verdict {
  label: string;
  manipulation_probability: number;
  ai_generation_probability: number;
  editing_probability: number;
  category: Category;
  decisive: boolean;
  rationale: string[];
}

export interface Evidence {
  case_id: string;
  original_name: string;
  sha256: string;
  size_bytes: number;
  ingested_at: string;
}

export interface Report {
  tool: string;
  tool_version: string;
  generated_at: string;
  modality: Modality;
  evidence: Evidence;
  integrity_verified: boolean;
  custody_log_valid: boolean;
  results: AnalyzerResult[];
  verdict: Verdict;
  overview: Record<string, string>;
  notes: string[];
}

export interface Urls {
  html: string;
  json: string;
  evidence: string | null;
  overview: Record<string, string>;
  artifacts: Record<string, Record<string, string>>;
}

export interface CasePayload {
  report: Report;
  urls: Urls;
}

export interface Job {
  id: string;
  name: string;
  size_bytes: number;
  deep: boolean;
  status: "queued" | "running" | "done" | "error";
  stage: string;
  progress: number;
  queue_position: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  result?: CasePayload | null;
}

export interface CaseSummary {
  case_id: string;
  sha256: string;
  name: string;
  modality: Modality;
  size_bytes: number;
  generated_at: string;
  label: string;
  category: Category;
  decisive: boolean;
  ai_generation_probability: number;
  editing_probability: number;
  thumbnail: string | null;
}

export interface ModelState {
  installed: boolean;
  loaded: boolean;
  enabled: boolean;
}

export interface Health {
  auth_required?: boolean;
  tool: string;
  version: string;
  runtime: { device: string; gpu?: string; vram_gb?: number };
  ffmpeg: boolean;
  models: Record<string, ModelState>;
  supported_types: Record<Modality, string[]>;
  limits: { max_upload_mb: number; max_analysis_seconds: number };
}
