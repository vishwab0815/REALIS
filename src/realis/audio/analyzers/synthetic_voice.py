"""AI-generated / cloned speech detection with NII AntiDeepfake."""

from __future__ import annotations

from realis import settings
from realis.audio import signal
from realis.audio.context import MODEL_RATE, AudioContext
from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity
from realis.ml import antideepfake

MIN_SPEECH_SECONDS = 1.0


def _segments(timeline: list[dict], threshold: float) -> list[dict]:
    """Merge consecutive windows above threshold into time ranges."""
    out: list[dict] = []
    for w in timeline:
        if w["fake_probability"] < threshold:
            continue
        if out and w["start"] <= out[-1]["end"]:
            out[-1]["end"] = w["end"]
            out[-1]["peak"] = max(out[-1]["peak"], w["fake_probability"])
        else:
            out.append({"start": w["start"], "end": w["end"], "peak": w["fake_probability"]})
    return out


@register
class SyntheticVoiceAnalyzer(Analyzer):
    name = "synthetic_voice"
    title = "AI voice detector"
    evidence_kind = EvidenceKind.SYNTHESIS
    modalities = ("audio", "video")
    weight = 1.3
    description = "NII AntiDeepfake MMS-300M (2025): synthetic or cloned speech, with a timeline"

    def skip_reason(self, ctx: AudioContext) -> str | None:
        if not ctx.has_audio:
            return "no audio track"
        if not antideepfake.available():
            return "model weights not installed: run `realis setup-models`"
        if signal.speech_seconds(ctx.samples16k, MODEL_RATE) < MIN_SPEECH_SECONDS:
            return f"less than {MIN_SPEECH_SECONDS:.0f} s of speech-like audio"
        return None

    def analyze(self, ctx: AudioContext) -> AnalyzerResult:
        out = antideepfake.predict(ctx.samples16k)
        p = out["fake_probability"]
        segments = _segments(out["timeline"], 0.9)

        findings = []
        if p >= 0.9:
            findings.append(Finding(severity=Severity.HIGH, title="Strong synthetic-speech signal",
                                    detail=f"Detector probability {p:.1%} over the analysed audio."))
        elif p >= 0.6:
            findings.append(Finding(severity=Severity.MEDIUM, title="Synthetic-speech signal",
                                    detail=f"Detector probability {p:.1%}."))
        elif p > 0.1:
            findings.append(Finding(severity=Severity.LOW, title="Uncertain synthetic-speech signal",
                                    detail=f"Detector probability {p:.1%}."))
        else:
            findings.append(Finding(severity=Severity.INFO, title="No synthetic-speech signal detected",
                                    detail=f"Detector probability {p:.1%}. New voice-cloning systems can evade "
                                           "detection, so this is weak evidence of a real voice."))

        score = p
        partial = p < 0.5 and segments
        if partial:
            # A few replaced words in an otherwise real recording ("partial deepfake").
            spans = ", ".join(f"{s['start']:.1f}-{s['end']:.1f} s" for s in segments[:5])
            findings.append(Finding(severity=Severity.MEDIUM, title="Possible synthetic segment",
                                    detail=f"Windows scoring above 90% at {spans}, although the whole clip "
                                           "scores low: consistent with words replaced by a cloned voice."))
            score = 0.7

        confidence = 0.45 if score >= 0.5 else 0.25
        if signal.speech_seconds(ctx.samples16k, MODEL_RATE) < 3:
            confidence *= 0.6

        return self.result(
            score=score, confidence=confidence, findings=findings,
            data={**out, "segments": segments, "model": settings.ANTIDEEPFAKE_REPO_ID,
                  "series": [{"name": "AI voice", "points": [[round((w["start"] + w["end"]) / 2, 2),
                                                               w["fake_probability"]] for w in out["timeline"]]}],
                  "license": antideepfake.LICENSE_NOTE,
                  "events": [{"time": s["start"], "end": s["end"], "kind": "synthetic",
                              "label": f"AI voice {s['peak']:.0%}"} for s in segments]},
            limitations=[
                "Heavily produced audio (film dialogue, broadcast, music beds) can score as synthetic: "
                "a film clip produced a false positive in local testing.",
                "Score thresholds are domain-dependent: on the Deepfake-Eval-2024 in-the-wild set this "
                "model's error rate is about 30%.",
                antideepfake.LICENSE_NOTE,
            ],
        )
