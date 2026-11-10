"""Edit discontinuities: inserted digital silence and abrupt background changes."""

from __future__ import annotations

from realis.audio import signal, visual
from realis.audio.context import AudioContext
from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, Finding, Severity


@register
class EditDiscontinuityAnalyzer(Analyzer):
    name = "edit_discontinuity"
    title = "Edit / splice detection"
    modalities = ("audio", "video")
    weight = 1.0
    description = "Digital silence inside the recording and abrupt, sustained background-noise changes"

    def skip_reason(self, ctx: AudioContext) -> str | None:
        return None if ctx.has_audio else "no audio track"

    def analyze(self, ctx: AudioContext) -> AnalyzerResult:
        runs = signal.digital_silence_runs(ctx.samples, ctx.rate)
        steps, times, floor = signal.noise_floor_steps(ctx.samples, ctx.rate)

        findings, events = [], []
        if runs:
            spans = ", ".join(f"{s:.2f}-{e:.2f} s" for s, e in runs[:5])
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Digital silence inside the recording",
                detail=f"{len(runs)} stretch(es) of exact zeros at {spans}. A microphone always records "
                       "some noise; true silence mid-recording usually means a cut, mute or insert."))
            events += [{"time": s, "end": e, "kind": "silence", "label": "digital silence"} for s, e in runs]
        if steps:
            where = ", ".join(f"{s['time']:.1f} s ({s['step_db']:+.0f} dB)" for s in steps[:5])
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Abrupt background-noise change",
                detail=f"At {where}. The room or microphone noise changes suddenly and stays changed, "
                       "as when two recordings are joined."))
            events += [{"time": s["time"], "kind": "noise", "label": f"noise {s['step_db']:+.0f} dB"} for s in steps]
        if not findings:
            findings.append(Finding(severity=Severity.INFO, title="No edit discontinuities found",
                                    detail="No inserted silence and no abrupt background changes."))

        if runs and steps:
            score, conf = 0.75, 0.45
        elif runs or steps:
            score, conf = 0.68, 0.35
        else:
            score, conf = 0.42, 0.2

        artifacts = {}
        if len(floor):
            fig, (ax,) = visual.figure(1, height=2.4)
            ax.plot(times, floor, color="#6ea8fe", linewidth=0.6, marker="o", markersize=3)
            visual.label(ax, "pause level (dBFS)")
            ax.set_xlabel("time (s)", color=visual.FG, fontsize=8)
            visual.mark_events(ax, events)
            fig.tight_layout()
            artifacts["Background noise level"] = ctx.save_figure("noise_floor", fig)

        return self.result(
            score=score, confidence=conf, findings=findings, artifacts=artifacts,
            data={"digital_silence": runs, "noise_steps": steps, "events": events},
            limitations=[
                "Noise gates and some VoIP apps output exact zeros during pauses.",
                "Real changes in the scene (a door, an air conditioner, moving the phone) also shift the noise level.",
                "Tuned to avoid false alarms: splices into very noisy recordings (pauses less than 18 dB below "
                "speech) or background changes under 10 dB are not reported.",
            ],
        )
