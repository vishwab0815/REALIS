import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import type { Series, TimelineEvent } from "../types";
import { EVENT_COLORS, SERIES_COLORS, formatTime } from "../util";

const LANE = 30;
const EVENT_LANE = 24;
const AXIS = 18;
const GUTTER = 78; // left labels

interface Props {
  duration: number;
  series: Series[];
  events: TimelineEvent[];
  currentTime: number;
  onSeek: (seconds: number) => void;
}

function niceStep(duration: number, width: number): number {
  const target = duration / Math.max(2, width / 90);
  return [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800].find((s) => s >= target) ?? 3600;
}

/** Interactive evidence timeline: probability lanes, event markers, playhead; click to seek. */
export function Timeline({ duration, series, events, currentTime, onSeek }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const span = Math.max(duration, 0.001);
  const plot = width - GUTTER - 8;
  const x = (t: number) => GUTTER + (Math.min(Math.max(t, 0), span) / span) * plot;
  const height = series.length * LANE + EVENT_LANE + AXIS;
  const step = niceStep(span, plot);
  const ticks = Array.from({ length: Math.floor(span / step) + 1 }, (_, i) => i * step);

  const seekFromPointer = (e: MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left - GUTTER;
    onSeek(Math.min(Math.max((px / plot) * span, 0), span));
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === "ArrowLeft") onSeek(Math.max(0, currentTime - 1));
    if (e.key === "ArrowRight") onSeek(Math.min(span, currentTime + 1));
  };

  return (
    <div className="timeline" ref={ref}>
      <svg
        width={width}
        height={height}
        role="slider"
        aria-label="Evidence timeline: click to seek"
        aria-valuemin={0}
        aria-valuemax={Math.round(span)}
        aria-valuenow={Math.round(currentTime)}
        tabIndex={0}
        onClick={seekFromPointer}
        onKeyDown={onKey}
      >
        {series.map((s, i) => {
          const top = i * LANE + 3;
          const h = LANE - 8;
          const color = SERIES_COLORS[s.name] ?? "var(--accent)";
          const pts = s.points.map(([t, v]) => `${x(t)},${top + h - v * h}`).join(" ");
          return (
            <g key={s.name}>
              <text x={6} y={top + h / 2 + 4} className="tl-label">{s.name}</text>
              <rect x={GUTTER} y={top} width={plot} height={h} className="tl-lane" />
              <line x1={GUTTER} x2={GUTTER + plot} y1={top + h / 2} y2={top + h / 2} className="tl-mid" />
              <polyline points={pts} fill="none" stroke={color} strokeWidth={1.6} />
              {s.points.map(([t, v]) => (
                <circle key={t} cx={x(t)} cy={top + h - v * h} r={2.6} fill={color}>
                  <title>{`${s.name} ${Math.round(v * 100)}% at ${formatTime(t, true)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        <g>
          <text x={6} y={series.length * LANE + EVENT_LANE / 2 + 2} className="tl-label">Events</text>
          <rect x={GUTTER} y={series.length * LANE} width={plot} height={EVENT_LANE - 6} className="tl-lane" />
          {events.map((e, i) => {
            const y = series.length * LANE;
            const color = EVENT_COLORS[e.kind] ?? "var(--bad)";
            const label = `${e.label ?? e.kind} at ${formatTime(e.time, true)}`;
            return e.end != null && e.end > e.time ? (
              <rect key={i} x={x(e.time)} y={y} width={Math.max(2, x(e.end) - x(e.time))} height={EVENT_LANE - 6}
                    fill={color} opacity={0.45}><title>{label}</title></rect>
            ) : (
              <rect key={i} x={x(e.time) - 1.5} y={y} width={3} height={EVENT_LANE - 6} fill={color}>
                <title>{label}</title>
              </rect>
            );
          })}
        </g>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={height - AXIS} y2={height - AXIS + 4} className="tl-tick" />
            <text x={x(t)} y={height - 3} textAnchor="middle" className="tl-axis">{formatTime(t)}</text>
          </g>
        ))}
        <line x1={x(currentTime)} x2={x(currentTime)} y1={0} y2={height - AXIS} className="tl-playhead" />
      </svg>
    </div>
  );
}
