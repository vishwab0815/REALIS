"""Local noise-level inconsistency (exploratory).

A single capture has one sensor noise profile that varies smoothly with
brightness. Content pasted from another source, denoised, or synthesised
usually carries a different noise level. Noise is estimated per block with
Immerkaer's Laplacian method on non-edge pixels, then compared with what
the block's brightness predicts.

Hand-crafted estimates are confounded by fine texture (foliage, fabric,
gravel), so automatic region flags were unreliable on test images. The map
is kept as a visual aid for the examiner and carries little weight in the
verdict; a learned noise fingerprint (Noiseprint++/TruFor) supersedes it.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from realis.core.analyzer import Analyzer, register
from realis.core.context import ImageContext
from realis.core.models import AnalyzerResult, Finding, Severity
from realis.image.blocks import anomaly_regions, block_mean, detrend, region_score, robust_z

BLOCK = 32
Z_THRESHOLD = 3.0
IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)


def noise_map(gray: np.ndarray, block: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-block noise sigma and a per-block validity mask."""
    lap = np.abs(cv2.filter2D(gray, cv2.CV_32F, IMMERKAER))
    grad = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    flat = (grad < np.percentile(grad, 85)).astype(np.float32)
    flat = cv2.erode(flat, np.ones((3, 3), np.uint8))
    frac = block_mean(flat, block)
    sigma = block_mean(lap * flat, block) / np.maximum(frac, 1e-6) * math.sqrt(math.pi / 2) / 6
    lum = block_mean(gray, block)
    valid = (frac > 0.3) & (lum > 12) & (lum < 243)
    return sigma, valid


@register
class NoiseAnalyzer(Analyzer):
    name = "noise_inconsistency"
    title = "Noise map (visual aid)"
    modalities = ("image",)
    weight = 0.5
    description = "Block-wise noise-level map (exploratory visual aid)"

    def analyze(self, ctx: ImageContext) -> AnalyzerResult:
        gray = ctx.gray
        sigma, valid = noise_map(gray, BLOCK)
        lum = block_mean(gray, BLOCK)
        resid = detrend(np.log(sigma + 0.05), lum / 255.0, valid, deg=2)
        z = robust_z(resid, valid)
        regions = anomaly_regions(z, valid, Z_THRESHOLD, BLOCK, min_blocks=3)
        score = region_score(regions, min_fraction=0.006)
        median_sigma = float(np.median(sigma[valid])) if valid.any() else None

        findings = []
        if score > 0.5:
            findings.append(Finding(
                severity=Severity.LOW, title="Possible region with a different noise level",
                detail=f"Largest region covers {regions.largest_fraction:.1%} at x,y,w,h={regions.largest_bbox}. "
                       "Could be splicing, local blurring/denoising or generated patches, but also "
                       "dense texture: check the map.",
            ))
        else:
            findings.append(Finding(severity=Severity.INFO, title="Noise level consistent across image",
                                    detail=f"Median noise sigma {median_sigma:.2f}" if median_sigma else ""))
        if median_sigma is not None and median_sigma < 0.4:
            findings.append(Finding(
                severity=Severity.LOW, title="Unusually clean image",
                detail="Very low sensor noise: heavy denoising, rendering, or AI generation; "
                       "it also makes this test less sensitive.",
            ))

        artifacts = {
            "Noise level map": ctx.save_overlay("noise_level", np.log(sigma + 0.1)),
            "Noise inconsistency map": ctx.save_overlay("noise_anomaly", np.abs(z), lo=0, hi=6),
        }
        return self.result(
            score=score, confidence=0.1,
            findings=findings, artifacts=artifacts,
            data={"block": BLOCK, "median_sigma": median_sigma, "valid_fraction": float(valid.mean()),
                  "regions": regions.__dict__},
            limitations=[
                "Exploratory: fine texture is easily mistaken for noise, so automatic flags are unreliable.",
                "Strong JPEG compression and resizing flatten noise and reduce sensitivity.",
            ],
        )
