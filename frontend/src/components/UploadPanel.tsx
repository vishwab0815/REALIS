import { useRef, useState } from "react";
import type { DragEvent } from "react";
import { api } from "../api";
import type { Health, Job } from "../types";
import { formatBytes, modalityOf } from "../util";

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
  return (
    <div className="upload">
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
            <div className="big">Uploading {upload.name}</div>
            <div className="progress"><span style={{ width: `${upload.fraction * 100}%` }} /></div>
            <div className="muted">{Math.round(upload.fraction * 100)}%</div>
          </div>
        ) : (
          <>
            <div className="icon" aria-hidden>⇪</div>
            <div className="big">{health ? "Drop an image, audio or video file" : "Connecting to the server…"}</div>
            <div className="muted">or click to browse · max {health?.limits.max_upload_mb ?? "…"} MB</div>
            <div className="types">
              <span>Images: JPEG PNG WebP HEIC TIFF</span>
              <span>Audio: WAV MP3 M4A OGG/Opus FLAC</span>
              <span>Video: MP4 MOV MKV WebM AVI</span>
            </div>
          </>
        )}
        <input ref={input} type="file" hidden accept={accept} onChange={(e) => e.target.files?.[0] && start(e.target.files[0])} />
      </div>

      <label className="switch">
        <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />
        <span className="track" aria-hidden><span className="thumb" /></span>
        <span>
          <b>Deep scan</b>
          <small>Adds TruFor manipulation localisation (images and video keyframes). Slower.</small>
        </span>
      </label>

      {error && <div className="card error-box" role="alert">{error}</div>}
      {health && !health.ffmpeg && (
        <div className="card error-box" role="alert">FFmpeg is not installed on the server: audio and video cannot be analysed.</div>
      )}
      <p className="privacy">
        Files are analysed on this machine and sealed as evidence: hashed (SHA-256), stored read-only and
        logged in a tamper-evident chain of custody.
      </p>
    </div>
  );
}
