"""Frame-level detectors: AI generation on sampled frames, TruFor on keyframes (deep scan)."""

from __future__ import annotations

import numpy as np
from PIL import Image

from realis import settings
from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity
from realis.core.viz import overlay
from realis.ml import commfor, trufor
from realis.video.context import VideoContext

TRUFOR_FRAMES = 6


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


@register
class FrameAiAnalyzer(Analyzer):
    name = "frame_ai"
    title = "AI-generated frames"
    evidence_kind = EvidenceKind.SYNTHESIS
    modalities = ("video",)
    weight = 1.2
    description = "Community Forensics image detector on evenly sampled frames, as a timeline"

    def skip_reason(self, ctx: VideoContext) -> str | None:
        return None if commfor.available() else "model weights not installed: run `realis setup-models`"

    def analyze(self, ctx: VideoContext) -> AnalyzerResult:
        probs = []
        for i, (_, rgb) in enumerate(ctx.frames):
            probs.append(float(commfor.predict(Image.fromarray(rgb))["probability"]))
            ctx.report_progress((i + 1) / len(ctx.frames), f"frame {i + 1}/{len(ctx.frames)}")
        thumbs = ctx.thumbnails
        p = float(1 / (1 + np.exp(-np.mean([_logit(x) for x in probs]))))
        flagged = sum(x >= 0.9 for x in probs)

        if p >= 0.9:
            finding = Finding(severity=Severity.HIGH, title="Frames look AI-generated",
                              detail=f"Mean probability {p:.1%}; {flagged} of {len(probs)} frames above 90%.")
        elif p >= 0.6:
            finding = Finding(severity=Severity.MEDIUM, title="Some AI-generation signal in frames",
                              detail=f"Mean probability {p:.1%}; {flagged} of {len(probs)} frames above 90%.")
        else:
            finding = Finding(severity=Severity.INFO, title="No AI-generation signal in frames",
                              detail=f"Mean probability {p:.1%} over {len(probs)} frames. Video compression and "
                                     "new video generators often defeat image detectors: weak evidence.")

        return self.result(
            score=p, confidence=0.45 if p >= 0.5 else 0.2, findings=[finding],
            data={"probability": p, "frames_flagged": flagged, "model": settings.COMMFOR_REPO_ID,
                  "frames": [{**th, "probability": round(x, 4)} for th, x in zip(thumbs, probs)],
                  "series": [{"name": "AI frames", "points": [[th["time"], round(x, 4)]
                                                               for th, x in zip(thumbs, probs)]}]},
            limitations=[
                "An image detector applied per frame: not trained on video, and weakened by video compression.",
                "Dedicated AI-video and face-swap detectors are not included yet.",
            ],
        )


@register
class FrameTruForAnalyzer(Analyzer):
    name = "frame_trufor"
    title = "TruFor on keyframes"
    modalities = ("video",)
    deep = True
    weight = 1.1
    description = "TruFor manipulation detector on up to 6 sampled frames (deep scan)"

    def skip_reason(self, ctx: VideoContext) -> str | None:
        return None if trufor.available() else "model not installed: run `realis setup-models`"

    def analyze(self, ctx: VideoContext) -> AnalyzerResult:
        frames = ctx.frames
        picks = sorted({round(i) for i in np.linspace(0, len(frames) - 1, min(TRUFOR_FRAMES, len(frames)))})
        scores, outputs = [], []
        for n, i in enumerate(picks):
            t, rgb = frames[i]
            out = trufor.predict(rgb)
            scores.append((t, out.score))
            outputs.append((t, rgb, out))
            ctx.report_progress((n + 1) / len(picks), f"keyframe {n + 1}/{len(picks)}")
        # A splice persists across frames; one high frame alone is weak. Use the second highest.
        ordered = sorted(s for _, s in scores)
        score = ordered[-2] if len(ordered) > 1 else ordered[-1]
        t_best, rgb_best, best = max(outputs, key=lambda o: o[2].score)

        if score >= 0.8:
            finding = Finding(severity=Severity.HIGH, title="Manipulated regions in several keyframes",
                              detail=f"Second-highest frame integrity score {score:.1%}; strongest at {t_best:.1f} s.")
        elif score >= 0.5:
            finding = Finding(severity=Severity.MEDIUM, title="Possible manipulation in keyframes",
                              detail=f"Second-highest frame integrity score {score:.1%}; strongest at {t_best:.1f} s.")
        else:
            finding = Finding(severity=Severity.INFO, title="No manipulation detected in keyframes",
                              detail=f"Integrity scores {', '.join(f'{s:.0%}' for _, s in scores)}.")

        artifacts = {f"TruFor map @ {t_best:.1f} s": ctx.save_image(
            "frame_trufor", overlay(rgb_best, best.localization, lo=0, hi=1))}
        return self.result(
            score=score, confidence=0.5 if score >= 0.5 else 0.3, findings=[finding], artifacts=artifacts,
            data={"frame_scores": [[round(t, 2), round(s, 4)] for t, s in scores],
                  "series": [{"name": "TruFor", "points": [[round(t, 2), round(s, 4)] for t, s in scores]}],
                  "license": trufor.LICENSE_NOTE},
            limitations=["Built for photo splicing and inpainting, not face-swap deepfakes.", trufor.LICENSE_NOTE],
        )
