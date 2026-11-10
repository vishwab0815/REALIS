"""Error Level Analysis, normalised for texture.

Plain ELA lights up every edge and textured area, which is why it is so
often misread. Here each block's error level is compared with what its
texture predicts, so only blocks whose compression response is out of line
with their content stand out.

On test images even the normalised version did not separate clean from
spliced files (smooth fur and defocused backgrounds look anomalous), so the
maps are an examiner's visual aid with little weight in the verdict.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from realis.core.analyzer import Analyzer, register
from realis.core.context import ImageContext
from realis.core.models import AnalyzerResult, Finding, Severity
from realis.image.blocks import anomaly_regions, block_mean, detrend, region_score, robust_z

BLOCK = 16
RESAVE_QUALITY = 90
Z_THRESHOLD = 3.5


@register
class ElaAnalyzer(Analyzer):
    name = "ela"
    title = "Error Level Analysis (visual aid)"
    modalities = ("image",)
    weight = 0.6
    description = "Texture-normalised Error Level Analysis maps (exploratory visual aid)"

    def analyze(self, ctx: ImageContext) -> AnalyzerResult:
        rgb = ctx.rgb
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, "JPEG", quality=RESAVE_QUALITY)
        resaved = np.asarray(Image.open(buf).convert("RGB"), dtype=np.float32)
        ela = np.abs(rgb.astype(np.float32) - resaved).mean(axis=2)

        gray = ctx.gray
        grad = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
        ela_b = block_mean(ela, BLOCK)
        tex_b = block_mean(grad, BLOCK)
        lum_b = block_mean(gray, BLOCK)
        # Clipped highlights/shadows have no compression error to measure.
        mask = (lum_b > 8) & (lum_b < 247)

        resid = detrend(np.log1p(ela_b), np.log1p(tex_b), mask)
        z = robust_z(resid, mask)
        regions = anomaly_regions(z, mask, Z_THRESHOLD, BLOCK)
        score = region_score(regions)

        findings = []
        if score > 0.5:
            findings.append(Finding(
                severity=Severity.LOW, title="Possible region with inconsistent compression error",
                detail=f"Largest region covers {regions.largest_fraction:.1%} of the image at "
                       f"x,y,w,h={regions.largest_bbox}. Smooth or defocused areas can also cause this: "
                       "check the map.",
            ))
        else:
            findings.append(Finding(severity=Severity.INFO, title="Compression error consistent with content",
                                    detail=f"{regions.anomalous_fraction:.2%} of blocks are scattered outliers."))

        ela_vis = np.clip(ela * (255.0 / max(np.percentile(ela, 99.5), 1e-6)), 0, 255).astype(np.uint8)
        artifacts = {
            "ELA (amplified)": ctx.save_image("ela_raw", np.stack([ela_vis] * 3, -1)),
            "ELA anomaly map (texture-normalised)": ctx.save_overlay("ela_anomaly", np.abs(z), lo=0, hi=6),
        }
        return self.result(
            score=score, confidence=0.1, findings=findings, artifacts=artifacts,
            data={"block": BLOCK, "resave_quality": RESAVE_QUALITY, "regions": regions.__dict__},
            limitations=[
                "Exploratory: automatic region flags were unreliable in testing; use the maps, not the score.",
                "ELA is weak on heavily recompressed images (social media) and on non-JPEG sources.",
                "Strong local edges, text or noise can still produce outlier blocks.",
            ],
        )
