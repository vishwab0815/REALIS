"""Per-file analysis contexts: lazily decoded views shared across analyzers."""

from __future__ import annotations

from collections.abc import Callable
from functools import cached_property
from pathlib import Path

import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener

from realis.core import viz

register_heif_opener()


class MediaContext:
    """What every modality shares: the sealed evidence file and an artifact folder."""

    def __init__(self, path: Path, sha256: str, case_dir: Path):
        self.path = path
        self.sha256 = sha256
        self.case_dir = case_dir
        self.artifact_dir = case_dir / "artifacts" / sha256[:12]
        # Set by the pipeline while an analyzer runs: (fraction 0-1, note) -> None.
        self.on_progress: Callable[[float, str], None] | None = None

    def report_progress(self, fraction: float, note: str = "") -> None:
        if self.on_progress:
            self.on_progress(min(max(fraction, 0.0), 1.0), note)

    @cached_property
    def raw_bytes(self) -> bytes:
        return self.path.read_bytes()

    def artifact_path(self, name: str) -> Path:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        return self.artifact_dir / f"{name}.png"

    def relative(self, path: Path) -> str:
        return path.relative_to(self.case_dir).as_posix()

    def save_image(self, name: str, rgb: np.ndarray) -> str:
        out = self.artifact_path(name)
        Image.fromarray(viz.limit_size(rgb)).save(out)
        return self.relative(out)


class ImageContext(MediaContext):
    @cached_property
    def image(self) -> Image.Image:
        # Pixels are analysed exactly as stored: no EXIF auto-rotation or
        # colour management, which would alter the forensic traces.
        img = Image.open(self.path)
        img.load()
        return img

    @property
    def format(self) -> str | None:
        return self.image.format

    @cached_property
    def rgb(self) -> np.ndarray:
        return np.asarray(self.image.convert("RGB"), dtype=np.uint8)

    @cached_property
    def gray(self) -> np.ndarray:
        """Luma (ITU-R 601) as float32 in [0, 255]."""
        rgb = self.rgb.astype(np.float32)
        return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114

    def save_overlay(self, name: str, heat: np.ndarray, **kwargs) -> str:
        """Blend a heat map over the image, save it, return a case-relative path."""
        return self.save_image(name, viz.overlay(self.rgb, heat, **kwargs))
