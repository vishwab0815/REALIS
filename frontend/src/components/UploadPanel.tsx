import { useRef, useState } from "react";
import type { DragEvent } from "react";
import { api } from "../api";
import type { Health, Job } from "../types";
import { formatBytes, modalityOf } from "../util";
import { IconAudio, IconImage, IconShield, IconUpload, IconVideo } from "./Icons";

interface Props {
  health: Health | null;
  onStarted: (job: Job) => void;
}

/** Validates a file against the server's limits; returns an error message or null. */
export function validateFile(file: File, health: Health | null): string | null {
  // Without the server's limits we cannot validate, so we do not upload either.
  if (!health) return "Still connecting to the server; try again in a moment.";
  if (!modalityOf(file.name, health.supported_types)) {
    const all = Object.values(health.supported_types).flat().join(" ");
    return `"${file.name}" is not a supported type. Supported: ${all}`;
  }
  if (file.size > health.limits.max_upload_mb * 1024 * 1024) {
    return `"${file.name}" is ${formatBytes(file.size)}; the limit is ${health.limits.max_upload_mb} MB.`;
  }
  if (file.size === 0) return `"${file.name}" is empty.`;
  return null;
}

export function UploadPanel({ health, onStarted }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [deep, setDeep] = useState(false);
  const [over, setOver] = useState(false);
  const [upload, setUpload] = useState<{ name: string; fraction: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = async (file: File) => {
    const problem = validateFile(file, health);
    setError(problem);
    if (problem) return;
    setUpload({ name: file.name, fraction: 0 });
    try {
      const job = await api.upload(file, deep, (fraction) => setUpload({ name: file.name, fraction }));
      onStarted(job);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUpload(null);
      if (input.current) input.current.value = "";
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const file = e.dataTransfer.files[0];
    if (file && !upload) void start(file);
  };

  const accept = health ? Object.values(health.supported_types).flat().join(",") + ",image/*,audio/*,video/*" : undefined;
  const ready = !!health && !upload;
  // Servers may disable TruFor (e.g. hosted quick-scan deployments): then there is no deep scan to offer.
  const deepAvailable = !!health && health.models.trufor?.enabled !== false && health.models.trufor?.installed !== false;
  return (
    <div className="upload">
      <div className="hero">
        <span className="eyebrow">Media authenticity analysis</span>
        <h1>Know what's real.</h1>
        <p>Check any image, recording or video for AI generation and editing traces. Every file is sealed as evidence.</p>
      </div>

      <div
        className={`dropzone ${over ? "over" : ""} ${upload ? "busy" : ""} ${health ? "" : "waiting"}`}
        role="button"
        tabIndex={0}
        aria-label="Upload a file to analyse"
        aria-disabled={!ready}
        onClick={() => ready && input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && ready && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        {upload ? (
          <div className="upload-progress" aria-live="polite">
            <b>Uploading {upload.name}</b>
            <div className="progress"><span style={{ width: `${upload.fraction * 100}%` }} /></div>
            <span className="muted">{Math.round(upload.fraction * 100)}%</span>
          </div>
        ) : (
          <>
            <span className="drop-icon"><IconUpload size={26} /></span>
            <b className="drop-title">{health ? "Drop a file here, or click to browse" : "Connecting to the server…"}</b>
            <div className="drop-types">
              <span><IconImage size={14} /> Image</span>
              <span><IconAudio size={14} /> Audio</span>
              <span><IconVideo size={14} /> Video</span>
              <span className="muted">· up to {health?.limits.max_upload_mb ?? "…"} MB</span>
            </div>
          </>
        )}
        <input ref={input} type="file" hidden accept={accept} onChange={(e) => e.target.files?.[0] && start(e.target.files[0])} />
      </div>

      {deepAvailable && <div className="segmented" role="radiogroup" aria-label="Scan mode">
        <button role="radio" aria-checked={!deep} className={!deep ? "active" : ""} onClick={() => setDeep(false)}>
          <b>Quick scan</b><span>Fast · recommended</span>
        </button>
        <button role="radio" aria-checked={deep} className={deep ? "active" : ""} onClick={() => setDeep(true)}>
          <b>Deep scan</b><span>Adds manipulation maps · slower</span>
        </button>
      </div>}

      {error && <div className="card error-box" role="alert">{error}</div>}
      {health && !health.ffmpeg && (
        <div className="card error-box" role="alert">FFmpeg is not installed on the server: audio and video cannot be analysed.</div>
      )}
      <p className="privacy">
        <IconShield size={14} />
        {health?.auth_required
          ? "Private workspace · files are hashed, sealed as evidence and deleted automatically"
          : "Analysed on this machine · hashed, stored read-only and logged in a chain of custody"}
      </p>
    </div>
  );
}
