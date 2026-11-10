"""Bandwidth history: upsampling and earlier lossy compression."""

from __future__ import annotations

from realis.audio import signal, visual
from realis.audio.context import AudioContext
from realis.core.analyzer import Analyzer, register
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity

LOSSLESS_CODECS = {"flac", "alac", "wavpack", "ape", "tta", "mlp", "truehd"}


def lossless(codec: str) -> bool:
    return codec.startswith("pcm_") or codec in LOSSLESS_CODECS


@register
class BandwidthAnalyzer(Analyzer):
    name = "bandwidth"
    title = "Bandwidth & resampling history"
    evidence_kind = EvidenceKind.PROCESSING
    modalities = ("audio", "video")
    weight = 0.8
    description = "Empty upper band in a lossless file: upsampled from a lower rate or transcoded from lossy"

    def skip_reason(self, ctx: AudioContext) -> str | None:
        return None if ctx.has_audio else "no audio track"

    def analyze(self, ctx: AudioContext) -> AnalyzerResult:
        b = signal.effective_bandwidth(ctx.samples, ctx.rate)
        cutoff, nyq = b["cutoff_hz"], ctx.rate / 2
        stored = f"{ctx.codec} at {ctx.rate / 1000:g} kHz"

        if cutoff is None:
            finding = Finding(severity=Severity.INFO, title="Full bandwidth",
                              detail=f"Content up to {nyq / 1000:.1f} kHz ({stored}).")
            score, conf = 0.5, 0.0
        elif not lossless(ctx.codec):
            finding = Finding(severity=Severity.INFO, title="Codec bandwidth limit",
                              detail=f"No content above ~{cutoff / 1000:.1f} kHz: normal low-pass for {stored}.")
            score, conf = 0.5, 0.0
        elif cutoff <= 12_500:
            finding = Finding(
                severity=Severity.MEDIUM, title="Upsampled from a lower-rate source",
                detail=f"No content above ~{cutoff / 1000:.1f} kHz although stored as {stored}. The audio passed "
                       "through a sample rate of roughly 16-24 kHz, as TTS and voice-cloning tools output, or a "
                       "phone/VoIP channel.")
            score, conf = 0.62, 0.35
        else:
            finding = Finding(
                severity=Severity.LOW, title="Earlier lossy compression",
                detail=f"No content above ~{cutoff / 1000:.1f} kHz although stored as lossless {stored}: "
                       "typical of an MP3/AAC file converted to WAV/FLAC.")
            score, conf = 0.56, 0.25

        fig, (ax,) = visual.figure(1, height=2.4)
        ax.plot(b["freqs"] / 1000, b["psd_db"], color="#6ea8fe", linewidth=0.8)
        if cutoff:
            ax.axvline(cutoff / 1000, color="#e3a33b", linewidth=1.2)
        visual.label(ax, "power (dB)")
        ax.set_xlabel("frequency (kHz)", color=visual.FG, fontsize=8)
        fig.tight_layout()

        return self.result(
            score=score, confidence=conf, findings=[finding],
            artifacts={"Frequency spectrum": ctx.save_figure("spectrum", fig)},
            data={"sample_rate": ctx.rate, "codec": ctx.codec, "cutoff_hz": cutoff,
                  "band_ratios_db": b["band_ratios_db"]},
            limitations=["Processing history is not manipulation by itself; many apps resample or transcode."],
        )
