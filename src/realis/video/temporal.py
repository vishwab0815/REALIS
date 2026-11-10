"""Frame-to-frame analysis: hard cuts and duplicated frames."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np

# A cut must change the picture this much (histogram distance 0..1) ...
CUT_MIN_HIST = 0.25
# ... and stand out this many times above the surrounding frame-to-frame change.
CUT_PEAK_RATIO = 4.0
# Mean absolute pixel change (0-255) that counts as "the picture is moving".
MOTION = 1.0
# A duplicated frame re-encoded by H.264 differs from its twin by ~0.003-0.05,
# while moving content changes by >= ~1 per frame (measured on test clips).
STILL = 0.1


@dataclass
class TemporalScan:
    frames: int = 0
    diffs: np.ndarray = field(default_factory=lambda: np.zeros(0))  # mean |frame - previous|
    hist: np.ndarray = field(default_factory=lambda: np.zeros(0))   # histogram distance to previous
    cuts: list[int] = field(default_factory=list)                     # index of the first frame after a cut
    duplicates: list[int] = field(default_factory=list)               # repeated frames inside motion

    @property
    def moving_frames(self) -> int:
        return int((self.diffs > MOTION).sum())


def scan(frames: Iterable[np.ndarray], expected: int = 0,
         progress: Callable[[float], None] | None = None) -> TemporalScan:
    diffs, hist = [], []
    prev, prev_h = None, None
    n = 0
    for frame in frames:
        h = np.bincount(frame.ravel() >> 3, minlength=32) / frame.size
        if prev is not None:
            diffs.append(float(np.mean(np.abs(frame.astype(np.int16) - prev))))
            hist.append(float(0.5 * np.abs(h - prev_h).sum()))
        prev, prev_h = frame.astype(np.int16), h
        n += 1
        if progress and expected and n % 200 == 0:
            progress(min(n / expected, 1.0))
    d, hd = np.array(diffs), np.array(hist)
    result = TemporalScan(frames=n, diffs=d, hist=hd)
    if len(d) < 3:
        return result

    for i in range(len(hd)):
        if hd[i] < CUT_MIN_HIST:
            continue
        around = np.concatenate([hd[max(0, i - 6):i], hd[i + 1:i + 7]])
        if around.size and hd[i] > CUT_PEAK_RATIO * max(np.median(around), 0.01):
            result.cuts.append(i + 1)

    # Runs of identical frames with motion on both sides: inserted, frozen or
    # rate-converted frames. Identical frames in a static scene are normal.
    i = 0
    while i < len(d):
        if d[i] > STILL:
            i += 1
            continue
        j = i
        while j + 1 < len(d) and d[j + 1] <= STILL:
            j += 1
        if i > 0 and j + 1 < len(d) and d[i - 1] > MOTION and d[j + 1] > MOTION:
            result.duplicates.extend(range(i + 1, j + 2))
        i = j + 1
    return result


def group_times(indices: list[int], fps: float, gap_s: float = 1.0) -> list[tuple[float, float, int]]:
    """Collapse frame indices into (start_s, end_s, count) runs."""
    runs: list[list[float]] = []
    for i in indices:
        t = i / fps if fps else float(i)
        if runs and t - runs[-1][1] <= gap_s:
            runs[-1][1] = t
            runs[-1][2] += 1
        else:
            runs.append([t, t, 1])
    return [(round(a, 2), round(b, 2), int(c)) for a, b, c in runs]
