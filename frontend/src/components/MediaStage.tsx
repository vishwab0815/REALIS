import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { asset } from "../api";
import type { CasePayload } from "../types";
import { formatTime, timelineData } from "../util";
import { IconLayers } from "./Icons";
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
        {report.modality === "audio" && (
          <img src={urls.overview["Evidence timeline"] ?? figures[0]?.url} alt="Evidence timeline" className="stage-img" />
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
        <nav className="views" aria-label="Evidence views">
          <span className="views-label"><IconLayers size={14} /> {isImage ? "Layers" : "Evidence views"}</span>
          {isImage
            ? imageLayers.map((l) => (
                <button key={l.url} className={layer?.url === l.url ? "active" : ""} onClick={() => setLayer(l)}>{l.label}</button>
              ))
            : figures.map((l) => <button key={l.url} onClick={() => onFigure(l.label, l.url)}>{l.label}</button>)}
        </nav>
      )}
    </div>
  );
});
