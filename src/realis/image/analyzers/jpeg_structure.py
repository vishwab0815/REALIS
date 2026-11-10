"""JPEG compression history: quantization tables and double compression."""

from __future__ import annotations

import numpy as np

from realis.core.analyzer import Analyzer, register
from realis.core.context import ImageContext
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity

# IJG (libjpeg) base tables, natural (row-major) order, as Pillow reports them.
IJG_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
])

# Low/mid-frequency DCT positions: populated enough to show quantization traces.
DQ_POSITIONS = [(0, 1), (1, 0), (1, 1), (0, 2), (2, 0), (1, 2), (2, 1), (2, 2), (0, 3), (3, 0)]
# Calibrated on single vs. double compressed images (single <= 0.04, double >= 0.30).
DQ_STRONG, DQ_WEAK = 0.15, 0.08


def ijg_table(quality: int) -> np.ndarray:
    scale = 5000 / quality if quality < 50 else 200 - 2 * quality
    return np.clip((IJG_LUMA * scale + 50) // 100, 1, 255)


def estimate_quality(luma: np.ndarray) -> tuple[int, bool]:
    """Best-matching IJG quality and whether the table matches it exactly."""
    errors = {q: int(np.abs(ijg_table(q) - luma).sum()) for q in range(1, 101)}
    best = min(errors, key=errors.get)
    return best, errors[best] == 0


def _dct_matrix(n: int = 8) -> np.ndarray:
    k = np.arange(n)
    d = np.sqrt(2 / n) * np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
    d[0] /= np.sqrt(2)
    return d


def double_compression_stat(y: np.ndarray, qtable: np.ndarray) -> float | None:
    """Mean non-monotonicity of quantized DCT histograms.

    A single JPEG pass gives smoothly decaying coefficient histograms. A
    previous pass with a coarser step leaves periodic peaks and gaps, which
    shows up as "rises" in what should be a decreasing curve.
    """
    d = _dct_matrix()
    h, w = (y.shape[0] // 8) * 8, (y.shape[1] // 8) * 8
    blocks = (y[:h, :w].astype(np.float64) - 128).reshape(h // 8, 8, w // 8, 8)
    blocks = blocks.swapaxes(1, 2).reshape(-1, 8, 8)
    coeffs = np.einsum("ij,njk,lk->nil", d, blocks, d)
    stats = []
    for u, v in DQ_POSITIONS:
        vals = np.abs(np.rint(coeffs[:, u, v] / qtable[u, v])).astype(int)
        hist = np.bincount(vals)[1:].astype(float)
        populated = np.nonzero(hist >= 15)[0]
        if populated.size == 0 or populated[-1] < 5:
            continue
        hist = hist[: populated[-1] + 1]
        stats.append(np.clip(np.diff(hist), 0, None).sum() / hist.sum())
    return float(np.mean(stats)) if len(stats) >= 3 else None


@register
class JpegStructureAnalyzer(Analyzer):
    name = "jpeg_structure"
    title = "JPEG compression history"
    evidence_kind = EvidenceKind.PROCESSING
    modalities = ("image",)
    weight = 1.0
    description = "Quantization-table fingerprint, quality estimate, double-compression detection"

    def skip_reason(self, ctx: ImageContext) -> str | None:
        if ctx.format != "JPEG":
            return f"not a JPEG ({ctx.format})"
        if not getattr(ctx.image, "quantization", None):
            return "no quantization tables found"
        return None

    def analyze(self, ctx: ImageContext) -> AnalyzerResult:
        tables = ctx.image.quantization
        luma = np.array(tables[0])
        quality, standard = estimate_quality(luma)
        make = str(ctx.image.getexif().get(0x010F, "") or "").strip()

        findings: list[Finding] = []
        signals: list[tuple[float, float]] = []
        encoder = (f"standard IJG/libjpeg table at quality {quality}" if standard
                   else f"custom tables (closest IJG quality ~{quality})")
        findings.append(Finding(severity=Severity.INFO, title="Quantization fingerprint", detail=encoder))

        if standard and make:
            signals.append((0.65, 0.4))
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Camera metadata with a generic software encoder",
                detail=f"EXIF claims a {make} camera, but the tables are the stock libjpeg ones that "
                       "editors, scripts and web platforms use. Likely re-encoded after capture "
                       "(some phones do use stock tables).",
            ))

        y = np.asarray(ctx.image.convert("YCbCr"))[..., 0]
        dq = double_compression_stat(y, luma.reshape(8, 8))
        if dq is None:
            findings.append(Finding(severity=Severity.INFO, title="Double-compression test inconclusive",
                                    detail="Not enough DCT coefficients (image too small or flat)."))
        elif dq >= DQ_STRONG:
            signals.append((0.62, 0.5))
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Image was JPEG-compressed at least twice",
                detail=f"DCT histogram periodicity {dq:.3f} (threshold {DQ_STRONG}). The file was "
                       "decoded and re-saved: consistent with editing, but also with re-sharing.",
            ))
        elif dq >= DQ_WEAK:
            signals.append((0.55, 0.25))
            findings.append(Finding(severity=Severity.LOW, title="Weak double-compression traces",
                                    detail=f"DCT histogram periodicity {dq:.3f}"))
        else:
            signals.append((0.4, 0.3))
            findings.append(Finding(severity=Severity.INFO, title="No double-compression traces",
                                    detail=f"DCT histogram periodicity {dq:.3f}"))

        score, conf = max(signals, key=lambda s: s[0]) if signals else (0.5, 0.0)
        return self.result(
            score=score, confidence=conf, findings=findings,
            data={"estimated_quality": quality, "standard_ijg_tables": standard,
                  "double_compression_stat": dq, "quantization_tables": {str(k): list(v) for k, v in tables.items()}},
            limitations=[
                "Double compression is only detectable when the earlier quality was clearly lower than the last one.",
                "Re-saving is not manipulation by itself; messaging apps recompress every image.",
            ],
        )
