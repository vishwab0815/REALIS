"""Metadata forensics: EXIF/XMP/PNG text, generator signatures, thumbnail check."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from datetime import datetime
from typing import Any

import cv2
import numpy as np
from PIL import ExifTags, Image

from realis.core.analyzer import Analyzer, register
from realis.core.context import ImageContext
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity

# Lower-cased substrings that identify generative AI tools.
AI_SIGNATURES = {
    "trainedalgorithmicmedia": "IPTC DigitalSourceType: trainedAlgorithmicMedia",
    "compositewithtrainedalgorithmicmedia": "IPTC DigitalSourceType: composite with AI",
    "midjourney": "Midjourney",
    "dall-e": "OpenAI DALL-E",
    "dall·e": "OpenAI DALL-E",
    "openai": "OpenAI",
    "stable diffusion": "Stable Diffusion",
    "stablediffusion": "Stable Diffusion",
    "comfyui": "ComfyUI",
    "automatic1111": "Stable Diffusion WebUI",
    "novelai": "NovelAI",
    "adobe firefly": "Adobe Firefly",
    "black forest labs": "FLUX (Black Forest Labs)",
    "leonardo.ai": "Leonardo.ai",
    "ideogram": "Ideogram",
}

EDITING_SOFTWARE = [
    "photoshop", "gimp", "lightroom", "snapseed", "picsart", "canva", "affinity",
    "pixelmator", "paint.net", "facetune", "photopea", "luminar", "meitu", "faceapp",
    "remini", "photodirector",
]

DATE_FMT = "%Y:%m:%d %H:%M:%S"


def _jsonable(v: Any) -> Any:
    if isinstance(v, bytes):
        if len(v) <= 64:
            return v.decode("ascii", "replace").rstrip("\x00")
        return f"<{len(v)} bytes>"
    if isinstance(v, (tuple, list)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (int, float, str)) or v is None:
        return v
    try:
        return float(v)  # IFDRational
    except (TypeError, ValueError):
        return str(v)


def _named(ifd: dict, names: dict) -> dict[str, Any]:
    return {str(names.get(k, k)): _jsonable(v) for k, v in ifd.items()}


def _parse_date(v: Any) -> datetime | None:
    try:
        return datetime.strptime(str(v).strip()[:19], DATE_FMT)
    except ValueError:
        return None


def _run_exiftool(path: str) -> dict[str, Any] | None:
    exe = shutil.which("exiftool")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-j", "-G1", "-a", "-n", path], capture_output=True, timeout=30, check=True
        )
        return json.loads(out.stdout)[0]
    except (subprocess.SubprocessError, json.JSONDecodeError, IndexError):
        return None


def extract_thumbnail(exif_bytes: bytes) -> bytes | None:
    """Return the JPEG thumbnail embedded in an APP1 EXIF segment, if any."""
    start = exif_bytes.find(b"\xff\xd8\xff", 6)
    if start < 0:
        return None
    end = exif_bytes.find(b"\xff\xd9", start)
    return exif_bytes[start:end + 2] if end > 0 else None


def compare_thumbnail(thumb_bytes: bytes, gray: np.ndarray) -> dict[str, Any] | None:
    try:
        thumb = np.asarray(Image.open(io.BytesIO(thumb_bytes)).convert("L"), dtype=np.float32)
    except Exception:
        return None
    # Cameras often letterbox thumbnails; trim near-black borders.
    rows = np.where(thumb.mean(axis=1) > 8)[0]
    cols = np.where(thumb.mean(axis=0) > 8)[0]
    if rows.size < 8 or cols.size < 8:
        return None
    thumb = thumb[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    th, tw = thumb.shape
    gh, gw = gray.shape
    aspect_delta = abs((tw / th) - (gw / gh)) / (gw / gh)
    small = cv2.resize(gray, (tw, th), interpolation=cv2.INTER_AREA)
    corr = float(np.corrcoef(thumb.ravel(), small.ravel())[0, 1])
    return {"thumbnail_size": [tw, th], "aspect_delta": round(aspect_delta, 3),
            "correlation": round(corr, 4)}


@register
class MetadataAnalyzer(Analyzer):
    name = "metadata"
    title = "Metadata"
    evidence_kind = EvidenceKind.PROVENANCE
    modalities = ("image",)
    weight = 1.0
    description = "EXIF/XMP/PNG-text inspection, AI generator signatures, thumbnail consistency"

    def analyze(self, ctx: ImageContext) -> AnalyzerResult:
        img = ctx.image
        exif = img.getexif()
        ifd0 = _named(dict(exif), ExifTags.TAGS)
        exif_ifd = _named(exif.get_ifd(ExifTags.IFD.Exif), ExifTags.TAGS)
        gps = _named(exif.get_ifd(ExifTags.IFD.GPSInfo), ExifTags.GPSTAGS)
        text_chunks = {}
        for k, v in img.info.items():
            if k in ("exif", "icc_profile") or not isinstance(v, (str, bytes)):
                continue
            if isinstance(v, bytes) and "xmp" in k.lower():
                v = v.decode("utf-8", "replace")[:50_000]
            text_chunks[k] = _jsonable(v)
        exiftool = _run_exiftool(str(ctx.path))

        findings: list[Finding] = []
        signals: list[tuple[float, float]] = []  # (score, confidence)
        decisive: str | None = None

        # 1. Generator signatures anywhere in the metadata.
        haystack = json.dumps([ifd0, exif_ifd, text_chunks, exiftool], default=str).lower()
        hits = sorted({label for sig, label in AI_SIGNATURES.items() if sig in haystack})
        if "parameters" in text_chunks and "steps:" in str(text_chunks["parameters"]).lower():
            hits.append("Stable Diffusion WebUI generation parameters (PNG text chunk)")
        if {"prompt", "workflow"} & text_chunks.keys():
            hits.append("ComfyUI prompt/workflow embedded (PNG text chunk)")
        if hits:
            decisive = "Metadata declares AI generation"
            signals.append((0.97, 0.9))
            findings.append(Finding(
                severity=Severity.CRITICAL, title="Generative-AI signature in metadata",
                detail="; ".join(hits),
            ))

        # 2. Editing software.
        software = str(ifd0.get("Software", "") or "")
        editors = [e for e in EDITING_SOFTWARE if e in haystack]
        if editors:
            signals.append((0.68, 0.45))
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Processed with image-editing software",
                detail=f"Software tag: {software or 'n/a'}; matches: {', '.join(editors)}",
            ))

        # 3. Capture vs modification time.
        taken = _parse_date(exif_ifd.get("DateTimeOriginal"))
        modified = _parse_date(ifd0.get("DateTime"))
        if taken and modified and abs((modified - taken).total_seconds()) > 60:
            signals.append((0.62, 0.35))
            findings.append(Finding(
                severity=Severity.LOW, title="File modified after capture",
                detail=f"DateTimeOriginal={taken}, DateTime(modified)={modified}",
            ))

        # 4. Embedded thumbnail vs main image (editors often leave the old thumbnail).
        thumb_info = None
        if (raw_exif := img.info.get("exif")) and (tb := extract_thumbnail(raw_exif)):
            thumb_info = compare_thumbnail(tb, ctx.gray)
            if thumb_info:
                corr, aspect = thumb_info["correlation"], thumb_info["aspect_delta"]
                if aspect > 0.08:
                    signals.append((0.7, 0.4))
                    findings.append(Finding(
                        severity=Severity.MEDIUM, title="EXIF thumbnail aspect ratio differs",
                        detail=f"Relative aspect difference {aspect:.1%}: image may have been cropped.",
                    ))
                elif corr < 0.75:
                    signals.append((0.85, 0.7))
                    findings.append(Finding(
                        severity=Severity.HIGH, title="EXIF thumbnail does not match image",
                        detail=f"Correlation {corr:.2f}: content changed after the thumbnail was written.",
                    ))
                elif corr < 0.9:
                    signals.append((0.65, 0.4))
                    findings.append(Finding(
                        severity=Severity.MEDIUM, title="EXIF thumbnail partially differs from image",
                        detail=f"Correlation {corr:.2f}",
                    ))
                else:
                    findings.append(Finding(
                        severity=Severity.INFO, title="EXIF thumbnail consistent with image",
                        detail=f"Correlation {corr:.2f}",
                    ))

        make, model = ifd0.get("Make"), ifd0.get("Model")
        if make or model:
            findings.append(Finding(severity=Severity.INFO, title="Camera identified",
                                    detail=f"{make or ''} {model or ''}".strip()))
        if not ifd0 and not exif_ifd:
            findings.append(Finding(
                severity=Severity.INFO, title="No EXIF metadata",
                detail="Stripped by a platform (social media, messaging) or a tool; neutral on its own.",
            ))

        # The AI signature is the strongest signal; every other flag is about editing.
        kind = EvidenceKind.SYNTHESIS if hits else EvidenceKind.MANIPULATION
        if signals:
            score, conf = max(signals, key=lambda s: s[0])
        elif make and taken:
            score, conf = 0.3, 0.3  # consistent camera metadata, but easily forged
            kind = EvidenceKind.PROVENANCE
        else:
            score, conf = 0.5, 0.0

        return self.result(
            score=score, confidence=conf, findings=findings, decisive_label=decisive, evidence_kind=kind,
            data={
                "format": ctx.format, "mode": img.mode, "size": list(img.size),
                "exif_ifd0": ifd0, "exif": exif_ifd, "gps": gps, "text_chunks": text_chunks,
                "thumbnail": thumb_info, "exiftool": exiftool,
            },
            limitations=[
                "Metadata is trivially editable; absence of red flags is weak evidence.",
                "exiftool not installed: using Pillow only." if exiftool is None else
                "exiftool output included.",
            ],
        )
