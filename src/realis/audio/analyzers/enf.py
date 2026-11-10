"""Electric Network Frequency (ENF) continuity analysis."""

from __future__ import annotations

from realis.audio import signal, visual
from realis.audio.context import AudioContext
from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, Finding, Severity


@register
class EnfAnalyzer(Analyzer):
    name = "enf"
    title = "Electric network frequency (ENF)"
    modalities = ("audio", "video")
    weight = 1.2
    description = "Mains-hum tracking (50/60 Hz): phase and frequency discontinuities reveal cuts and inserts"

    def skip_reason(self, ctx: AudioContext) -> str | None:
        if not ctx.has_audio:
            return "no audio track"
        if ctx.analysed_seconds < signal.ENF_MIN_SECONDS:
            return f"recording shorter than {signal.ENF_MIN_SECONDS:.0f} s"
        return None

    def analyze(self, ctx: AudioContext) -> AnalyzerResult:
        r = signal.enf_analysis(ctx.samples, ctx.rate)
        limitations = [
            "ENF only reveals edits when mains hum was captured (indoors, near mains-powered devices).",
            "A cut that happens to remove a whole number of hum cycles leaves the phase continuous.",
            "Dating a recording against grid frequency logs needs reference data that is not included.",
        ]
        if not r.present:
            return self.result(score=0.5, confidence=0.0, findings=[Finding(
                severity=Severity.INFO, title="No mains hum (ENF) found",
                detail=f"{r.reason}. Common for phone recordings outdoors or with noise suppression.")],
                limitations=limitations, data={"present": False, "reason": r.reason})

        summary = (f"{r.grid_hz:.0f} Hz grid, harmonic {r.harmonic}, {r.snr_db:.0f} dB above background, "
                   f"frequency {r.freqs.min():.3f}-{r.freqs.max():.3f} Hz")
        events = [{"time": round(e["time"], 2), "kind": "enf", "label": "ENF break"} for e in r.discontinuities]
        if not r.continuity_checked:
            findings = [Finding(severity=Severity.INFO, title="Mains hum present, not judged",
                                detail=f"{r.reason}. {summary}.")]
            score, conf = 0.5, 0.0
        elif r.discontinuities:
            strong = max(e["strength"] for e in r.discontinuities) >= 2
            times = ", ".join(f"{e['time']:.1f} s ({e['kind']})" for e in r.discontinuities[:6])
            findings = [Finding(
                severity=Severity.HIGH if strong else Severity.MEDIUM,
                title="Mains-hum discontinuity: possible cut or insert",
                detail=f"At {times}. The hum's phase or frequency jumps where audio was removed or "
                       f"pasted in. {summary}.")]
            score, conf = (0.85, 0.55) if strong else (0.7, 0.4)
        else:
            findings = [Finding(severity=Severity.INFO, title="Mains hum present and continuous",
                                detail=f"No phase or frequency breaks: consistent with one unedited take. {summary}.")]
            score, conf = 0.3, 0.4

        fig, (freq_ax, phase_ax) = visual.figure(2, height=3.6)
        freq_ax.plot(r.times, r.freqs, color="#6ea8fe", linewidth=1)
        visual.label(freq_ax, "ENF (Hz)")
        phase_ax.plot(r.phase_times, r.phase_dev, color="#9aa3b2", linewidth=0.6)
        visual.label(phase_ax, "phase dev (Hz)")
        phase_ax.set_xlabel("time (s)", color=visual.FG, fontsize=8)
        for ax in (freq_ax, phase_ax):
            visual.mark_events(ax, events)
        fig.tight_layout()

        return self.result(
            score=score, confidence=conf, findings=findings,
            artifacts={"ENF track": ctx.save_figure("enf", fig)},
            data={"present": True, "grid_hz": r.grid_hz, "harmonic": r.harmonic, "snr_db": round(r.snr_db, 1),
                  "discontinuities": r.discontinuities, "events": events},
            limitations=limitations,
        )
