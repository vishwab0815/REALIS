"""Hard cuts and duplicated frames from a full low-resolution pass over the video."""

from __future__ import annotations

from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, Finding, Severity
from realis.video import io, temporal
from realis.video.context import VideoContext

# Above this share of moving frames, duplicates are a pattern (rate conversion), not an insert.
REGULAR_SHARE = 0.15


@register
class TemporalEditsAnalyzer(Analyzer):
    name = "temporal_edits"
    title = "Cuts & duplicated frames"
    modalities = ("video",)
    weight = 1.0
    description = "Hard cuts, frozen or inserted frames, and frame-rate conversion from every frame"

    def analyze(self, ctx: VideoContext) -> AnalyzerResult:
        fps = ctx.fps or 30.0
        expected = int(ctx.analysed_seconds * fps)
        scan = temporal.scan(io.scan_frames(ctx.path), expected,
                             progress=lambda f: ctx.report_progress(f, "scanning frames"))
        cuts = [round(i / fps, 2) for i in scan.cuts]
        share = len(scan.duplicates) / max(scan.moving_frames, 1)
        runs = temporal.group_times(scan.duplicates, fps)

        findings, events = [], []
        score, conf = 0.42, 0.2
        if cuts:
            shown = ", ".join(f"{t:.2f} s" for t in cuts[:8])
            findings.append(Finding(
                severity=Severity.MEDIUM, title=f"{len(cuts)} hard cut(s)",
                detail=f"At {shown}. Normal for edited footage; not expected in a single continuous "
                       "recording such as CCTV or a phone clip presented as unedited."))
            events += [{"time": t, "kind": "cut", "label": "cut"} for t in cuts]
            score, conf = 0.62, 0.3
        if runs and share >= REGULAR_SHARE:
            findings.append(Finding(
                severity=Severity.LOW, title="Regular duplicated frames",
                detail=f"{len(scan.duplicates)} of {scan.moving_frames} moving frames repeat the previous one: "
                       "converted from a lower frame rate or re-rendered by an editor."))
            score, conf = max(score, 0.56), max(conf, 0.2)
        elif runs:
            shown = ", ".join(f"{a:.2f}-{b:.2f} s ({n})" for a, b, n in runs[:6])
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Frozen or inserted frames",
                detail=f"Identical frames inside moving footage at {shown}: frames were duplicated, "
                       "e.g. to hide a removed moment or pad an insert."))
            events += [{"time": a, "end": b if b > a else None, "kind": "duplicate", "label": "frozen"}
                       for a, b, _ in runs]
            score, conf = max(score, 0.68), max(conf, 0.35)
        if not findings:
            findings.append(Finding(severity=Severity.INFO, title="Continuous footage",
                                    detail=f"No cuts or duplicated frames in {scan.frames} frames."))

        return self.result(
            score=score, confidence=conf, findings=findings,
            data={"frames_scanned": scan.frames, "fps": round(fps, 3), "moving_frames": scan.moving_frames,
                  "cuts": cuts, "duplicate_runs": runs, "duplicate_share": round(share, 3), "events": events},
            limitations=[
                "Dissolves and fades are not reported as cuts; a single dropped frame is not detectable.",
                "Times are frame index / average frame rate, approximate for variable-frame-rate video.",
            ],
        )
