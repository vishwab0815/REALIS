"""Whole-image AI-generation detection with the Community Forensics ViT."""

from __future__ import annotations

from realis import settings
from realis.core.analyzer import Analyzer, register
from realis.core.context import ImageContext
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity
from realis.ml import commfor


@register
class AiGeneratedAnalyzer(Analyzer):
    name = "ai_generated"
    title = "AI-generation detector"
    evidence_kind = EvidenceKind.SYNTHESIS
    modalities = ("image",)
    weight = 1.3
    description = "Community Forensics ViT-S/16 (CVPR 2025), trained on ~4,800 generators"

    def skip_reason(self, ctx: ImageContext) -> str | None:
        if not commfor.available():
            return "model weights not installed: run `realis setup-models`"
        return None

    def analyze(self, ctx: ImageContext) -> AnalyzerResult:
        out = commfor.predict(ctx.image)
        p = float(out["probability"])

        if p >= 0.9:
            finding = Finding(severity=Severity.HIGH, title="Strong AI-generation signal",
                              detail=f"Detector probability {p:.1%} across 5 crops.")
        elif p >= 0.6:
            finding = Finding(severity=Severity.MEDIUM, title="AI-generation signal",
                              detail=f"Detector probability {p:.1%} across 5 crops.")
        elif p > 0.1:
            finding = Finding(severity=Severity.LOW, title="Uncertain AI-generation signal",
                              detail=f"Detector probability {p:.1%}.")
        else:
            finding = Finding(severity=Severity.INFO, title="No AI-generation signal detected",
                              detail=f"Detector probability {p:.1%}. Recent commercial generators are "
                                     "often missed, so this is weak evidence of a real photo.")

        # A positive is far more informative than a negative: open detectors
        # catch only ~20-30% of images from the newest commercial generators.
        confidence = 0.55 if p >= 0.5 else 0.25
        if min(ctx.image.size) < 256:
            confidence *= 0.5

        return self.result(
            score=p, confidence=confidence, findings=[finding],
            data={**out, "model": settings.COMMFOR_REPO_ID, "license": "MIT"},
            limitations=[
                "Generalises poorly to the newest commercial generators (Flux, Firefly, Midjourney v7, "
                "Imagen 4 in 2026 benchmarks): a low score is not proof of authenticity.",
                "Sensitive to recompression: in local tests, DALL-E 2 images scoring >0.9 as PNG fell to "
                "0.14-0.56 after one JPEG re-save at quality 85 (as messaging apps do).",
                "Training data is dominated by Stable Diffusion derivatives.",
                "Detects whole-image generation; small AI edits inside a real photo are TruFor's job.",
            ],
        )
