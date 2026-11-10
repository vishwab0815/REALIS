"""Figures for audio evidence: spectrogram overview, ENF track, spectrum, noise floor."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import spectrogram

from realis.core.models import AnalyzerResult, Status

BG, FG, GRID = "#14171d", "#c9cfda", "#2a2f3a"
COLORS = {"synthetic": "#b07cf7", "enf": "#e5533d", "silence": "#e3a33b", "noise": "#e3a33b",
          "cut": "#6ea8fe", "duplicate": "#e3a33b"}
MAX_COLUMNS = 2000


def figure(rows: int = 1, height: float = 3.0, ratios: list[float] | None = None):
    fig, axes = plt.subplots(rows, 1, figsize=(11, height), sharex=True, squeeze=False,
                             gridspec_kw={"height_ratios": ratios} if ratios else None)
    fig.patch.set_facecolor(BG)
    for ax in axes[:, 0]:
        ax.set_facecolor(BG)
        ax.tick_params(colors=FG, labelsize=8)
        for side in ax.spines.values():
            side.set_color(GRID)
        ax.grid(color=GRID, linewidth=0.5, alpha=0.6)
    return fig, list(axes[:, 0])


def label(ax, text: str) -> None:
    ax.set_ylabel(text, color=FG, fontsize=8)


def mark_events(ax, events: list[dict], annotate: bool = False) -> None:
    for e in events:
        color = COLORS.get(e.get("kind", ""), "#e5533d")
        if e.get("end") is not None:
            ax.axvspan(e["time"], e["end"], color=color, alpha=0.18, linewidth=0)
        else:
            ax.axvline(e["time"], color=color, linewidth=1.2, alpha=0.9)
        if annotate and e.get("label"):
            ax.text(e["time"], 1.0, " " + e["label"], color=color, fontsize=7, va="top",
                    transform=ax.get_xaxis_transform())


def draw_spectrogram(ax, x: np.ndarray, sr: int) -> None:
    f, t, s = spectrogram(x, sr, nperseg=1024, noverlap=512)
    db = 10 * np.log10(s + 1e-12)
    if db.shape[1] > MAX_COLUMNS:  # average down so long files render quickly
        k = int(np.ceil(db.shape[1] / MAX_COLUMNS))
        cols = db.shape[1] // k * k
        db = db[:, :cols].reshape(db.shape[0], -1, k).mean(axis=2)
        t = t[:cols:k]
    vmax = np.percentile(db, 99.5)
    extent = (0, len(x) / sr, f[0] / 1000, f[-1] / 1000)
    ax.imshow(db, origin="lower", aspect="auto", cmap="magma", extent=extent, vmin=vmax - 80, vmax=vmax)
    label(ax, "kHz")


def overview(x: np.ndarray, sr: int, results: list[AnalyzerResult]):
    """Waveform, spectrogram and AI-voice timeline with every analyzer's events."""
    events = [e for r in results if r.status == Status.OK for e in r.data.get("events", [])]
    voice = next((r for r in results if r.analyzer == "synthetic_voice" and r.status == Status.OK), None)
    timeline = voice.data.get("timeline", []) if voice else []

    fig, (wave, spec, ai) = figure(3, height=5.2, ratios=[1, 2.2, 1])
    step = max(1, len(x) // 20000)
    t = np.arange(0, len(x), step) / sr
    wave.plot(t, x[::step], color="#6ea8fe", linewidth=0.4)
    wave.set_ylim(-1, 1)
    label(wave, "wave")
    draw_spectrogram(spec, x, sr)
    if timeline:
        mids = [(w["start"] + w["end"]) / 2 for w in timeline]
        ai.plot(mids, [w["fake_probability"] for w in timeline], color=COLORS["synthetic"], marker="o", markersize=3)
    elif voice:
        ai.axhline(voice.score or 0, color=COLORS["synthetic"])
    ai.axhline(0.5, color=GRID, linestyle="--", linewidth=0.8)
    ai.set_ylim(-0.02, 1.02)
    label(ai, "AI voice")
    ai.set_xlabel("time (s)", color=FG, fontsize=8)
    ai.set_xlim(0, len(x) / sr)
    for ax in (wave, spec, ai):
        mark_events(ax, events, annotate=ax is wave)
    fig.tight_layout()
    return fig
