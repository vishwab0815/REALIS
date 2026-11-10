"""Learned manipulation localisation with TruFor (RGB + Noiseprint++)."""

from __future__ import annotations

import numpy as np

from realis.core.analyzer import Analyzer, register
from realis.core.context import ImageContext
from realis.core.models import AnalyzerResult, Finding, Severity
from realis.image.blocks import Regions, anomaly_regions
from realis.ml import trufor

LOC_THRESHOLD = 0.5


@register
class TruForAnalyzer(Analyzer):
    name = "trufor"
    title = "TruFor manipulation detector"
    modalities = ("image",)
    deep = True
    weight = 1.3
    description = "TruFor (CVPR 2023): manipulation score, localisation and reliability maps"

    def skip_reason(self, ctx: ImageContext) -> str | None:
        if not trufor.available():
            return "model not installed: run `realis setup-models`"
        return None

    def analyze(self, ctx: ImageContext) -> AnalyzerResult:
        out = trufor.predict(ctx.rgb)
        score = out.score
        # Only trust localisation where TruFor itself says it is reliable.
        trusted = out.confidence >= 0.5
        flagged = (out.localization >= LOC_THRESHOLD) & trusted
        flagged_fraction = float(flagged.mean())
        region = self._largest_region(flagged)

        findings = []
        where = (f" Largest flagged region at x,y,w,h={region.largest_bbox} "
                 f"({flagged_fraction:.1%} of the image).") if region.largest_bbox else ""
        if score >= 0.8:
            findings.append(Finding(severity=Severity.HIGH, title="Manipulated regions detected",
                                    detail=f"Integrity score {score:.1%}.{where}"))
        elif score >= 0.5:
            findings.append(Finding(severity=Severity.MEDIUM, title="Possible manipulation",
                                    detail=f"Integrity score {score:.1%}.{where}"))
        else:
            findings.append(Finding(severity=Severity.INFO, title="No manipulation detected",
                                    detail=f"Integrity score {score:.1%}."))

        artifacts = {
            "TruFor localization map": ctx.save_overlay("trufor_localization", out.localization, lo=0, hi=1),
            "TruFor reliability map": ctx.save_overlay("trufor_reliability", out.confidence, lo=0, hi=1),
        }
        return self.result(
            score=score, confidence=0.55 if score >= 0.5 else 0.35, findings=findings,
            artifacts=artifacts,
            data={"integrity_score": score, "flagged_fraction": flagged_fraction,
                  "trusted_fraction": float(trusted.mean()), "tiled": out.tiled,
                  "largest_region_bbox": region.largest_bbox, "license": trufor.LICENSE_NOTE},
            limitations=[
                "Built for local edits (splicing, copy-move, inpainting); fully AI-generated images "
                "are the AI-generation detector's job.",
                "Heavy recompression and resizing weaken the Noiseprint++ traces it relies on.",
                trufor.LICENSE_NOTE,
            ],
        )

    @staticmethod
    def _largest_region(mask: np.ndarray, block: int = 16) -> Regions:
        h, w = (mask.shape[0] // block) * block, (mask.shape[1] // block) * block
        grid = mask[:h, :w].reshape(h // block, block, w // block, block).mean(axis=(1, 3))
        # Reuse the block-region grouping: a block counts when half of it is flagged.
        z = (grid >= 0.5).astype(float) * 10
        return anomaly_regions(z, np.ones_like(grid, dtype=bool), threshold=5, block=block, min_blocks=2)
