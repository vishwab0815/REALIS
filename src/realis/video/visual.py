"""Video evidence timeline: filmstrip, per-analyzer probability curves, event markers."""

from __future__ import annotations

import numpy as np
from PIL import Image

from realis.audio import visual
from realis.core.models import AnalyzerResult, Status
from realis.video.context import VideoContext

SERIES_COLORS = {"AI frames": "#b07cf7", "AI voice": "#e070c0", "TruFor": "#e5533d"}
STRIP_FRAMES = 8


def _strip(ctx: VideoContext) -> np.ndarray:
    frames = ctx.frames
    picks = np.linspace(0, len(frames) - 1, min(STRIP_FRAMES, len(frames))).round().astype(int)
    tiles = []
    for i in picks:
        img = Image.fromarray(frames[i][1])
        img.thumbnail((240, 135))
        tile = Image.new("RGB", (240, 135), visual.BG)
        tile.paste(img, ((240 - img.width) // 2, (135 - img.height) // 2))
        tiles.append(np.asarray(tile))
    return np.concatenate(tiles, axis=1)


def overview(ctx: VideoContext, results: list[AnalyzerResult]):
    ok = [r for r in results if r.status == Status.OK]
    series = [s for r in ok for s in r.data.get("series", [])]
    events = [e for r in ok for e in r.data.get("events", [])]
    span = ctx.analysed_seconds

    fig, axes = visual.figure(2, height=4.6, ratios=[1.4, 1.6])
    strip_ax, curve_ax = axes
    strip_ax.imshow(_strip(ctx), extent=(0, span, 0, 1), aspect="auto")
    strip_ax.set_yticks([])
    visual.label(strip_ax, "frames")
    for s in series:
        pts = np.array(s["points"], dtype=float).reshape(-1, 2)
        if len(pts):
            curve_ax.plot(pts[:, 0], pts[:, 1], marker="o", markersize=3, linewidth=1.2,
                          color=SERIES_COLORS.get(s["name"], "#6ea8fe"), label=s["name"])
    curve_ax.axhline(0.5, color=visual.GRID, linestyle="--", linewidth=0.8)
    curve_ax.set_ylim(-0.02, 1.02)
    curve_ax.set_xlim(0, span)
    visual.label(curve_ax, "probability")
    curve_ax.set_xlabel("time (s)", color=visual.FG, fontsize=8)
    if series:
        curve_ax.legend(loc="upper right", fontsize=7, facecolor=visual.BG, edgecolor=visual.GRID, labelcolor=visual.FG)
    for ax in axes:
        visual.mark_events(ax, events, annotate=ax is strip_ax)
    fig.tight_layout()
    return fig
