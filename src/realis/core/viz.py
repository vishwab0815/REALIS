"""Rendering helpers for evidence heat maps."""

from __future__ import annotations

import cv2
import numpy as np

MAX_ARTIFACT_DIM = 2000


def normalize(heat: np.ndarray, lo: float | None = None, hi: float | None = None) -> np.ndarray:
    heat = np.nan_to_num(heat.astype(np.float32), nan=0.0)
    lo = float(np.percentile(heat, 1)) if lo is None else lo
    hi = float(np.percentile(heat, 99)) if hi is None else hi
    if hi - lo < 1e-9:
        return np.zeros_like(heat)
    return np.clip((heat - lo) / (hi - lo), 0.0, 1.0)


def overlay(
    rgb: np.ndarray,
    heat: np.ndarray,
    alpha: float = 0.5,
    lo: float | None = None,
    hi: float | None = None,
) -> np.ndarray:
    """Colour-map `heat` (any resolution, e.g. a per-block grid) over `rgb`.

    Block grids are upscaled with nearest-neighbour so the report shows the
    true analysis resolution instead of a smoothed, more convincing picture.
    """
    h, w = rgb.shape[:2]
    norm = normalize(heat, lo, hi)
    norm = cv2.resize(norm, (w, h), interpolation=cv2.INTER_NEAREST)
    colored = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
    return (rgb * (1 - alpha) + colored * alpha).astype(np.uint8)


def limit_size(rgb: np.ndarray, max_dim: int = MAX_ARTIFACT_DIM) -> np.ndarray:
    h, w = rgb.shape[:2]
    scale = max_dim / max(h, w)
    if scale >= 1:
        return rgb
    return cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
