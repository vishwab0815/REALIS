"""Video container metadata: generator and editor signatures, device, track consistency."""

from __future__ import annotations

import json
import re

from realis.common.signatures import container_tags, match
from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity
from realis.video import io
from realis.video.context import VideoContext

AI_VIDEO_TOOLS = {
    r"\bsora\b": "OpenAI Sora", r"\bopenai\b": "OpenAI", r"runway(ml)?\b": "Runway", r"\bgen-?[234]\b": "Runway Gen",
    r"\bpika\b": "Pika", r"\bkling\b": "Kling", r"kuaishou": "Kuaishou (Kling)", r"\bveo\b": "Google Veo",
    r"deepmind": "Google DeepMind", r"dream machine|lumalabs|luma ai": "Luma Dream Machine",
    r"hailuo": "Hailuo", r"minimax": "MiniMax", r"\bhaiper\b": "Haiper", r"synthesia": "Synthesia",
    r"heygen": "HeyGen", r"\bd-id\b": "D-ID", r"invideo": "InVideo", r"stable video|\bsvd\b": "Stable Video",
    r"\bltx\b|lightricks": "LTX (Lightricks)", r"hunyuan": "HunyuanVideo", r"cogvideo": "CogVideo",
    r"\bmochi\b": "Mochi", r"\bwan ?2": "Wan", r"ai[- ]generated": "AI-generated",
}
EDITORS = {
    r"premiere": "Adobe Premiere", r"after effects": "Adobe After Effects", r"davinci|resolve": "DaVinci Resolve",
    r"final cut": "Final Cut Pro", r"imovie": "iMovie", r"capcut": "CapCut", r"inshot": "InShot",
    r"kinemaster": "KineMaster", r"filmora": "Filmora", r"\bvn video": "VN", r"shotcut": "Shotcut",
    r"handbrake": "HandBrake", r"\bvegas\b": "VEGAS", r"\bavid\b": "Avid", r"lumafusion": "LumaFusion",
    r"clipchamp": "Clipchamp", r"\bcanva\b": "Canva",
}
DEVICE_KEYS = ("com.apple.quicktime.make", "com.apple.quicktime.model", "com.apple.quicktime.software",
               "com.android.version", "com.android.manufacturer", "com.android.model", "make", "model")
TRACK_MISMATCH_S = 1.0


def _duration(stream: dict | None) -> float | None:
    try:
        return float(stream["duration"]) if stream and stream.get("duration") else None
    except (TypeError, ValueError):
        return None


@register
class VideoMetadataAnalyzer(Analyzer):
    name = "video_metadata"
    title = "Metadata & container"
    evidence_kind = EvidenceKind.PROVENANCE
    modalities = ("video",)
    weight = 1.0
    description = "AI video generator and editor signatures, recording device, audio/video track consistency"

    def analyze(self, ctx: VideoContext) -> AnalyzerResult:
        probe = ctx.probe
        tags = container_tags(probe)
        text = json.dumps(tags).lower()
        findings: list[Finding] = []
        signals: list[tuple[float, float, EvidenceKind]] = []
        decisive = None

        if ai := match(AI_VIDEO_TOOLS, text):
            decisive = "Metadata declares AI-generated video"
            signals.append((0.97, 0.9, EvidenceKind.SYNTHESIS))
            findings.append(Finding(severity=Severity.CRITICAL, title="AI video generator signature in metadata",
                                    detail=", ".join(ai)))
        if editors := match(EDITORS, text):
            signals.append((0.66, 0.4, EvidenceKind.MANIPULATION))
            findings.append(Finding(severity=Severity.MEDIUM, title="Processed with video-editing software",
                                    detail=", ".join(editors)))

        audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None)
        v_len, a_len = _duration(ctx.video), _duration(audio)
        if v_len and a_len and abs(v_len - a_len) > TRACK_MISMATCH_S:
            signals.append((0.62, 0.3, EvidenceKind.MANIPULATION))
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Audio and video tracks differ in length",
                detail=f"Video {v_len:.2f} s, audio {a_len:.2f} s: consistent with replaced or dubbed audio, "
                       "or with editing; some apps also pad tracks."))

        encoder = " ".join(v for k, v in tags.items() if k.endswith(".encoder"))
        if re.search(r"\blav[fc]\d", encoder.lower()):
            findings.append(Finding(severity=Severity.INFO, title="Written by an FFmpeg-based tool",
                                    detail=f"Encoder '{encoder.strip()}': converted or re-encoded."))
        device = {k: v for k, v in tags.items() if k.split(".", 1)[1] in DEVICE_KEYS}
        if device:
            findings.append(Finding(severity=Severity.INFO, title="Recording device identified",
                                    detail=", ".join(f"{k.split('.', 1)[1].rsplit('.', 1)[-1]}={v}"
                                                     for k, v in device.items())))
        r_fps, avg_fps = io.rate(ctx.video.get("r_frame_rate")), io.rate(ctx.video.get("avg_frame_rate"))
        if r_fps and avg_fps and abs(r_fps - avg_fps) / r_fps > 0.02:
            findings.append(Finding(severity=Severity.INFO, title="Variable frame rate",
                                    detail=f"Nominal {r_fps:.2f} fps, average {avg_fps:.2f} fps: typical of phone "
                                           "recordings and screen captures."))
        if not tags.get("format.creation_time") and not device:
            findings.append(Finding(severity=Severity.INFO, title="No capture metadata",
                                    detail="No creation time or device tags: exported, re-encoded or stripped."))

        kind = self.evidence_kind
        if signals:
            score, conf, kind = max(signals, key=lambda s: s[0])
        elif device:
            score, conf = 0.35, 0.25  # device tags are easy to forge
        else:
            score, conf = 0.5, 0.0

        fmt = probe.get("format", {})
        return self.result(
            score=score, confidence=conf, findings=findings, decisive_label=decisive, evidence_kind=kind,
            data={"container": fmt.get("format_long_name") or fmt.get("format_name"),
                  "video_codec": ctx.video_codec, "size": list(ctx.size), "fps": round(ctx.fps, 3),
                  "duration_s": round(ctx.duration, 2), "rotation": io.rotation(ctx.video),
                  "audio_codec": audio.get("codec_name") if audio else None,
                  "creation_time": tags.get("format.creation_time"), "tags": tags},
            limitations=["Metadata is trivially editable; absence of red flags is weak evidence."],
        )
