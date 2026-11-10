"""Block statistics and anomaly-region scoring shared by local analyzers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


def block_view(arr: np.ndarray, b: int) -> np.ndarray:
    """Reshape a 2-D array into (rows, cols, b, b) blocks, cropping the remainder."""
    h, w = (arr.shape[0] // b) * b, (arr.shape[1] // b) * b
    return arr[:h, :w].reshape(h // b, b, w // b, b).swapaxes(1, 2)


def block_mean(arr: np.ndarray, b: int) -> np.ndarray:
    return block_view(arr, b).mean(axis=(2, 3))


def robust_z(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    vals = x[mask]
    if vals.size < 10:
        return np.zeros_like(x)
    med = np.median(vals)
    mad = np.median(np.abs(vals - med)) * 1.4826
    z = (x - med) / max(mad, 1e-6)
    return np.where(mask, z, 0.0)


def detrend(y: np.ndarray, x: np.ndarray, mask: np.ndarray, deg: int = 1) -> np.ndarray:
    """Residual of y after a robust polynomial fit on x (two-pass, outliers dropped)."""
    if mask.sum() < 10:
        return np.zeros_like(y)
    coef = np.polyfit(x[mask], y[mask], deg)
    resid = y - np.polyval(coef, x)
    keep = mask & (np.abs(robust_z(resid, mask)) < 3)
    if keep.sum() >= 10:
        coef = np.polyfit(x[keep], y[keep], deg)
        resid = y - np.polyval(coef, x)
    return np.where(mask, resid, 0.0)


@dataclass
class Regions:
    count: int
    largest_blocks: int
    largest_fraction: float
    largest_bbox: tuple[int, int, int, int] | None  # x, y, w, h in pixels
    anomalous_fraction: float


def anomaly_regions(
    z: np.ndarray, mask: np.ndarray, threshold: float, block: int, min_blocks: int = 4
) -> Regions:
    """Group outlier blocks into 8-connected regions.

    Isolated outlier blocks are expected by chance; a coherent region is what
    points to a locally different processing history.
    """
    anom = (np.abs(z) > threshold) & mask
    labels, n = ndimage.label(anom, structure=np.ones((3, 3)))
    sizes = ndimage.sum(anom, labels, range(1, n + 1)) if n else np.array([])
    valid = max(int(mask.sum()), 1)
    big = [i for i, s in enumerate(sizes, start=1) if s >= min_blocks]
    if not big:
        return Regions(0, 0, 0.0, None, float(anom.sum() / valid))
    best = max(big, key=lambda i: sizes[i - 1])
    sl = ndimage.find_objects(labels)[best - 1]
    bbox = (sl[1].start * block, sl[0].start * block,
            (sl[1].stop - sl[1].start) * block, (sl[0].stop - sl[0].start) * block)
    largest = int(sizes[best - 1])
    return Regions(len(big), largest, largest / valid, bbox, float(anom.sum() / valid))


def region_score(regions: Regions, min_fraction: float = 0.004) -> float:
    """Map the largest anomalous region to a manipulation score in [0.35, 0.85]."""
    if regions.largest_blocks == 0 or regions.largest_fraction < min_fraction:
        return 0.35
    return min(0.85, 0.55 + regions.largest_fraction * 3)
