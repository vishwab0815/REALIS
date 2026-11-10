"""Synthetic recordings with known edits, for testing audio forensics."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

SR = 16_000


def hum(n: int, sr: int = SR, f0: float = 50.0, amp: float = 0.004, seed: int = 0) -> np.ndarray:
    """Mains hum whose frequency wanders slowly, like a real grid."""
    t = np.arange(n) / sr
    f = f0 + 0.03 * np.sin(2 * np.pi * t / 23 + seed)
    phase = 2 * np.pi * np.cumsum(f) / sr
    return amp * (np.sin(phase) + 0.5 * np.sin(2 * phase + 0.3))


def speech_like(n: int, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Band-limited noise bursts with syllable-like rhythm and real pauses."""
    rng = np.random.default_rng(seed)
    x = sosfilt(butter(4, [150, 3500], "band", fs=sr, output="sos"), rng.normal(0, 1, n))
    t = np.arange(n) / sr
    envelope = (np.sin(2 * np.pi * t * 3.1) > 0.2) * (np.sin(2 * np.pi * t * 0.4) > -0.6)
    return 0.1 * x * envelope


def recording(seconds: float = 40, with_hum: bool = True, noise: float = 0.003, seed: int = 0,
              f0: float = 50.0) -> np.ndarray:
    n = int(seconds * SR)
    rng = np.random.default_rng(seed + 100)
    x = speech_like(n, seed=seed) + rng.normal(0, noise, n)
    if with_hum:
        x = x + hum(n, f0=f0, seed=seed)
    return x.astype(np.float32)


def write_wav(path, x: np.ndarray, sr: int = SR) -> None:
    from scipy.io import wavfile

    wavfile.write(path, sr, (np.clip(x, -1, 1) * 32767).astype(np.int16))
