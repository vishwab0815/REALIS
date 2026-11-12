import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { asset } from "../api";
import type { CasePayload } from "../types";
import { formatTime, timelineData } from "../util";
import { IconExpand, IconLayers } from "./Icons";
import { Timeline } from "./Timeline";

export interface StageHandle {
  seek: (seconds: number) => void;
}

interface Layer {
  label: string;
  url: string;
}

interface Props {
  payload: CasePayload;
  onFigure: (label: string, url: string) => void;
}

// Short button names and a one-line explanation for the image layers the analyzers produce.
const LAYER_INFO: Record<string, { short: string; hint: string }> = {
  Original: { short: "Original", hint: "The evidence copy, as uploaded." },
  "ELA (amplified)": { short: "ELA", hint: "Error level analysis: areas that recompress differently look brighter." },
  "ELA anomaly map (texture-normalised)": { short: "ELA anomalies", hint: "Hot areas react to recompression unusually for their texture." },
  "Noise level map": { short: "Noise level", hint: "Strength of the camera's sensor noise across the image." },
  "Noise inconsistency map": { short: "Noise anomalies", hint: "Hot areas have noise that does not match the rest of the image." },
  "Copy-move matches": { short: "Copy-move", hint: "Regions that appear to be duplicated within the image." },
  "TruFor localization map": { short: "TruFor map", hint: "Where the TruFor model suspects tampering." },
  "TruFor reliability map": { short: "TruFor reliability", hint: "How far the TruFor map can be trusted in each area." },
};

/** Button name and explanation for a layer; unknown labels lose "(…)" and a trailing "map". */
export function layerInfo(label: string) {
  return LAYER_INFO[label] ?? {
    short: label.replace(/\s*\([^)]*\)/g, "").replace(/\s+map$/i, "").trim() || label,
    hint: "",
  };
}

/** Media viewer: image with switchable layers, or an audio/video player with filmstrip and timeline. */
export const MediaStage = forwardRef<StageHandle, Props>(function MediaStage({ payload, onFigure }, ref) {
  const { report, urls } = payload;
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const [time, setTime] = useState(0);
  const [mediaDuration, setMediaDuration] = useState(0);
  const timeline = useMemo(() => timelineData(report), [report]);
  const duration = mediaDuration || timeline.duration;
  const isImage = report.modality === "image";

  const figures: Layer[] = useMemo(() => [
    ...Object.entries(urls.overview).map(([label, url]) => ({ label, url })),
    ...Object.values(urls.artifacts).flatMap((a) => Object.entries(a).map(([label, url]) => ({ label, url }))),
  ], [urls]);
  const imageLayers = useMemo(
    () => (isImage && urls.evidence ? [{ label: "Original", url: urls.evidence }, ...figures] : []),
    [isImage, urls.evidence, figures],
  );
  const [layer, setLayer] = useState<Layer | null>(imageLayers[0] ?? null);
  useEffect(() => setLayer(imageLayers[0] ?? null), [imageLayers]);
  const audioOverview: Layer | null = report.modality === "audio"
    ? { label: "Evidence timeline", url: urls.overview["Evidence timeline"] ?? figures[0]?.url }
    : null;
  // The picture on the stage that "View full size" opens.
  const shown = isImage ? layer : audioOverview?.url ? audioOverview : null;
  const caption = isImage && layer && layer.label !== "Original" ? layerInfo(layer.label) : null;

  const seek = (t: number) => {
    const m = mediaRef.current;
    if (m) {
      m.currentTime = t;
      setTime(t);
    }
  };
  useImperativeHandle(ref, () => ({ seek }));

  const mediaEvents = {
    onTimeUpdate: (e: { currentTarget: HTMLMediaElement }) => setTime(e.currentTarget.currentTime),
    onLoadedMetadata: (e: { currentTarget: HTMLMediaElement }) => setMediaDuration(e.currentTarget.duration || 0),
  };

  return (
    <div className={`stage stage-${report.modality}`}>
      <div className="stage-main">
        {isImage && layer && <img src={layer.url} alt={layer.label} className="stage-img" />}
        {report.modality === "video" && urls.evidence && (
          <video ref={mediaRef} src={urls.evidence} controls preload="metadata" className="player-video" {...mediaEvents} />
        )}
        {audioOverview?.url && <img src={audioOverview.url} alt={audioOverview.label} className="stage-img" />}
        {caption && (
          <div className="stage-caption" role="note">
            <b>{layer!.label}</b>
            {caption.hint && <span>{caption.hint}</span>}
          </div>
        )}
        {shown && (
          <button className="stage-expand" onClick={() => onFigure(shown.label, shown.url)} title="View full size"
                  aria-label="View full size">
            <IconExpand size={15} />
          </button>
        )}
      </div>

      {report.modality === "audio" && urls.evidence && (
        <audio ref={mediaRef} src={urls.evidence} controls preload="metadata" className="player-audio" {...mediaEvents} />
      )}

      {timeline.frames.length > 0 && (
        <div className="filmstrip" aria-label="Sampled frames">
          {timeline.frames.map((f) => {
            const tone = f.probability >= 0.9 ? "ai" : f.probability >= 0.6 ? "warn" : "ok";
            const active = Math.abs(time - f.time) < Math.max(0.5, duration / timeline.frames.length / 2);
            return (
              <button key={f.path} className={`frame tone-${tone} ${active ? "active" : ""}`} onClick={() => seek(f.time)}
                      title={`${formatTime(f.time, true)} · AI ${Math.round(f.probability * 100)}%`}>
                <img src={asset(`/cases/${report.evidence.case_id}/${f.path}`)} alt={`Frame at ${formatTime(f.time, true)}`} loading="lazy" />
                <span>{formatTime(f.time)}</span>
              </button>
            );
          })}
        </div>
      )}

      {!isImage && duration > 0 && (timeline.series.length > 0 || timeline.events.length > 0) && (
        <Timeline duration={duration} series={timeline.series} events={timeline.events} currentTime={time} onSeek={seek} />
      )}

      {(isImage ? imageLayers.length > 1 : figures.length > 0) && (
        <nav className="views" aria-label={isImage ? "Image layers" : "Evidence views"}>
          <span className="views-label"><IconLayers size={14} /> {isImage ? "Layers" : "Views"}</span>
          <div className="views-list">
            {isImage
              ? imageLayers.map((l) => (
                  <button key={l.url} className={layer?.url === l.url ? "active" : ""} aria-pressed={layer?.url === l.url}
                          title={l.label} onClick={() => setLayer(l)}>
                    {layerInfo(l.label).short}
                  </button>
                ))
              : figures.map((l) => (
                  <button key={l.url} title={l.label} onClick={() => onFigure(l.label, l.url)}>{layerInfo(l.label).short}</button>
                ))}
          </div>
        </nav>
      )}
    </div>
  );
});
