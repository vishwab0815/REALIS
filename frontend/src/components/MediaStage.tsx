import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { CasePayload } from "../types";
import { formatTime, timelineData } from "../util";
import { Timeline } from "./Timeline";

export interface StageHandle {
  seek: (seconds: number) => void;
}

interface Layer {
  label: string;
  url: string;
}

/** Media viewer: image layers, or an audio/video player with filmstrip and evidence timeline. */
export const MediaStage = forwardRef<StageHandle, { payload: CasePayload }>(function MediaStage({ payload }, ref) {
  const { report, urls } = payload;
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const [time, setTime] = useState(0);
  const [mediaDuration, setMediaDuration] = useState(0);
  const timeline = useMemo(() => timelineData(report), [report]);
  const duration = mediaDuration || timeline.duration;

  const layers: Layer[] = useMemo(() => {
    const figures = [
      ...Object.entries(urls.overview).map(([label, url]) => ({ label, url })),
      ...Object.values(urls.artifacts).flatMap((a) => Object.entries(a).map(([label, url]) => ({ label, url }))),
    ];
    return report.modality === "image" && urls.evidence ? [{ label: "Original", url: urls.evidence }, ...figures] : figures;
  }, [report.modality, urls]);
  // Images open on the original; time-based media keep the player in front and show figures on demand.
  const [layer, setLayer] = useState<Layer | null>(report.modality === "image" ? layers[0] ?? null : null);
  useEffect(() => setLayer(report.modality === "image" ? layers[0] ?? null : null), [layers, report.modality]);

  const seek = (t: number) => {
    const m = mediaRef.current;
    if (m) {
      m.currentTime = t;
      setTime(t);
    }
  };
  useImperativeHandle(ref, () => ({ seek }));

  const player = urls.evidence && report.modality !== "image" && (
    report.modality === "video" ? (
      <video ref={mediaRef} src={urls.evidence} controls preload="metadata" className="player-video"
             onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
             onLoadedMetadata={(e) => setMediaDuration(e.currentTarget.duration || 0)} />
    ) : (
      <audio ref={mediaRef} src={urls.evidence} controls preload="metadata" className="player-audio"
             onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
             onLoadedMetadata={(e) => setMediaDuration(e.currentTarget.duration || 0)} />
    )
  );

  return (
    <div className={`stage stage-${report.modality}`}>
      <div className="stage-main">
        {report.modality === "image" && layer && <img src={layer.url} alt={layer.label} className="stage-img" />}
        {report.modality === "video" && player}
        {report.modality === "audio" && (
          <img src={urls.overview["Evidence timeline"] ?? layers[0]?.url} alt="Evidence timeline" className="stage-img" />
        )}
        {report.modality !== "image" && layer && (
          <div className="lightbox" role="dialog" aria-label={layer.label} onClick={() => setLayer(null)}>
            <figure onClick={(e) => e.stopPropagation()}>
              <img src={layer.url} alt={layer.label} />
              <figcaption>{layer.label} <button className="btn ghost small" onClick={() => setLayer(null)}>Close</button></figcaption>
            </figure>
          </div>
        )}
      </div>

      {report.modality === "audio" && player}

      {timeline.frames.length > 0 && (
        <div className="filmstrip" aria-label="Sampled frames">
          {timeline.frames.map((f) => {
            const tone = f.probability >= 0.9 ? "ai" : f.probability >= 0.6 ? "warn" : "ok";
            const active = Math.abs(time - f.time) < Math.max(0.5, duration / timeline.frames.length / 2);
            return (
              <button key={f.path} className={`frame tone-${tone} ${active ? "active" : ""}`} onClick={() => seek(f.time)}
                      title={`${formatTime(f.time, true)} · AI ${Math.round(f.probability * 100)}%`}>
                <img src={`/cases/${report.evidence.case_id}/${f.path}`} alt={`Frame at ${formatTime(f.time, true)}`} loading="lazy" />
                <span>{formatTime(f.time)}</span>
              </button>
            );
          })}
        </div>
      )}

      {report.modality !== "image" && duration > 0 && (timeline.series.length > 0 || timeline.events.length > 0) && (
        <Timeline duration={duration} series={timeline.series} events={timeline.events} currentTime={time} onSeek={seek} />
      )}

      {layers.length > 0 && (
        <nav className="layers" aria-label="Evidence figures">
          {report.modality !== "image" && <span className="layers-label">Figures</span>}
          {layers.map((l) => (
            <button key={l.url} className={layer?.url === l.url ? "active" : ""} onClick={() => setLayer(l)}>{l.label}</button>
          ))}
        </nav>
      )}
    </div>
  );
});
