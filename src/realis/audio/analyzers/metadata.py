"""Audio container metadata: AI-voice tool signatures, editors, devices, encoders."""

from __future__ import annotations

import json
import re

from realis.audio.context import AudioContext
from realis.common.signatures import match
from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity

# Word-boundary patterns: a bare "tts" would otherwise match inside "https".
AI_VOICE_TOOLS = {
    r"eleven ?labs": "ElevenLabs", r"\bsuno\b": "Suno", r"\budio\b": "Udio", r"resemble(\.ai)?\b": "Resemble AI",
    r"play\.?ht": "PlayHT", r"\bmurf\b": "Murf", r"speechify": "Speechify", r"wellsaid": "WellSaid",
    r"overdub": "Descript Overdub", r"\blovo\b": "LOVO", r"voicemod": "Voicemod", r"\bcoqui\b": "Coqui",
    r"\bxtts\b": "XTTS", r"tortoise[- ]tts": "Tortoise TTS", r"\bf5[- ]tts\b": "F5-TTS", r"\bopenai\b": "OpenAI",
    r"\btts\b": "TTS", r"text[- ]to[- ]speech": "text-to-speech", r"voice clon": "voice cloning",
    r"ai[- ]generated": "AI-generated",
}
EDITORS = {
    r"audacity": "Audacity", r"adobe audition|\baudition\b": "Adobe Audition", r"garageband": "GarageBand",
    r"logic pro": "Logic Pro", r"fl studio": "FL Studio", r"\breaper\b": "REAPER", r"ableton": "Ableton",
    r"ocenaudio": "ocenaudio", r"wavepad": "WavePad", r"cubase": "Cubase", r"pro tools": "Pro Tools",
    r"izotope|\brx \d": "iZotope RX",
}
DEVICE_KEYS = ("com.apple.quicktime.make", "com.apple.quicktime.model", "com.apple.quicktime.software",
               "com.android.version", "com.android.manufacturer", "com.android.model")


def _tags(ctx: AudioContext) -> dict[str, str]:
    tags = {f"format.{k.lower()}": str(v) for k, v in ctx.probe.get("format", {}).get("tags", {}).items()}
    tags |= {f"stream.{k.lower()}": str(v) for k, v in ctx.stream.get("tags", {}).items()}
    return tags


@register
class AudioMetadataAnalyzer(Analyzer):
    name = "audio_metadata"
    title = "Metadata"
    evidence_kind = EvidenceKind.PROVENANCE
    modalities = ("audio",)
    weight = 1.0
    description = "Container tags: AI-voice tool signatures, editing software, recording device, encoder"

    def analyze(self, ctx: AudioContext) -> AnalyzerResult:
        tags = _tags(ctx)
        text = json.dumps(tags).lower()
        fmt = ctx.probe.get("format", {})
        findings: list[Finding] = []
        signals: list[tuple[float, float, EvidenceKind]] = []
        decisive = None

        if ai := match(AI_VOICE_TOOLS, text):
            decisive = "Metadata declares AI-generated audio"
            signals.append((0.97, 0.9, EvidenceKind.SYNTHESIS))
            findings.append(Finding(severity=Severity.CRITICAL, title="AI voice tool signature in metadata",
                                    detail=", ".join(ai)))
        if editors := match(EDITORS, text):
            signals.append((0.68, 0.45, EvidenceKind.MANIPULATION))
            findings.append(Finding(severity=Severity.MEDIUM, title="Processed with audio-editing software",
                                    detail=", ".join(editors)))
        encoder = tags.get("format.encoder") or tags.get("stream.encoder") or ""
        if re.search(r"\blav[fc]\d", encoder.lower()):
            findings.append(Finding(severity=Severity.INFO, title="Written by an FFmpeg-based tool",
                                    detail=f"Encoder '{encoder}': converted or re-encoded, as many apps and "
                                           "converters do; not suspicious by itself."))
        device = {k.split(".", 1)[1]: v for k, v in tags.items() if k.split(".", 1)[1] in DEVICE_KEYS}
        if device:
            findings.append(Finding(severity=Severity.INFO, title="Recording device identified",
                                    detail=", ".join(f"{k.rsplit('.', 1)[-1]}={v}" for k, v in device.items())))
        if not tags:
            findings.append(Finding(severity=Severity.INFO, title="No metadata tags",
                                    detail="Stripped by a platform or tool, or never written; neutral on its own."))

        kind = self.evidence_kind
        if signals:
            score, conf, kind = max(signals, key=lambda s: s[0])
        elif device:
            score, conf = 0.35, 0.25  # device tags are easy to forge
        else:
            score, conf = 0.5, 0.0

        return self.result(
            score=score, confidence=conf, findings=findings, decisive_label=decisive, evidence_kind=kind,
            data={"format": fmt.get("format_long_name") or fmt.get("format_name"), "codec": ctx.codec,
                  "sample_rate": ctx.rate, "channels": ctx.stream.get("channels"),
                  "duration_s": round(ctx.duration, 2), "bit_rate": fmt.get("bit_rate"), "tags": tags},
            limitations=["Metadata is trivially editable; absence of red flags is weak evidence."],
        )
