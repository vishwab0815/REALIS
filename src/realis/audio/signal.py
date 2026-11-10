"""Signal-level audio forensics: ENF, edit discontinuities, bandwidth history."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import gcd

import numpy as np
from scipy.ndimage import median_filter, percentile_filter, uniform_filter1d
from scipy.signal import butter, hilbert, resample_poly, sosfiltfilt, stft, welch

EPS = 1e-12


def resample(x: np.ndarray, sr: int, target: int) -> np.ndarray:
    if sr == target:
        return x
    g = gcd(int(sr), int(target))
    return resample_poly(x, target // g, sr // g).astype(np.float32)


def frame_db(x: np.ndarray, sr: int, frame_s: float = 0.02) -> np.ndarray:
    """RMS level in dBFS per non-overlapping frame."""
    n = max(1, int(sr * frame_s))
    frames = x[: len(x) // n * n].reshape(-1, n)
    return 10 * np.log10(np.mean(frames.astype(np.float64) ** 2, axis=1) + EPS)


def speech_seconds(x: np.ndarray, sr: int) -> float:
    """Rough voice-activity estimate: frames well above the noise floor."""
    db = frame_db(x, sr)
    if db.size == 0:
        return 0.0
    floor = np.percentile(db, 10)
    active = (db > floor + 12) & (db > -55)
    return float(active.sum() * 0.02)


# --------------------------------------------------------------------------- ENF

@dataclass
class EnfResult:
    present: bool
    reason: str = ""
    # False when hum is present but too short or weak to judge continuity.
    continuity_checked: bool = False
    grid_hz: float | None = None
    harmonic: int | None = None
    snr_db: float | None = None
    times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    freqs: np.ndarray = field(default_factory=lambda: np.zeros(0))
    phase_times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    phase_dev: np.ndarray = field(default_factory=lambda: np.zeros(0))
    discontinuities: list[dict] = field(default_factory=list)


ENF_RATE = 1000
ENF_MIN_SECONDS = 8.0
ENF_MIN_SNR_DB = 12.0
# Continuity (edit) analysis needs a long, strong trace: short clips and weak
# hum produced false breaks on real recordings in testing.
ENF_CONTINUITY_SECONDS = 20.0
ENF_CONTINUITY_SNR_DB = 20.0


def _strongest_mains_line(y: np.ndarray, grids: tuple[float, ...]) -> tuple[float, int, float]:
    f, p = welch(y, ENF_RATE, nperseg=min(len(y), 16 * ENF_RATE))
    best = (grids[0], 1, -np.inf)
    for grid in grids:
        for k in range(1, 5):
            fk = grid * k
            if fk > ENF_RATE / 2 - 20:
                break
            peak = (f > fk - 0.5) & (f < fk + 0.5)
            ref = ((f > fk - 6) & (f < fk - 1.5)) | ((f > fk + 1.5) & (f < fk + 6))
            snr = 10 * np.log10(p[peak].max() / (np.median(p[ref]) + EPS) + EPS)
            if snr > best[2]:
                best = (grid, k, float(snr))
    return best


def enf_analysis(x: np.ndarray, sr: int, grids: tuple[float, ...] = (50.0, 60.0)) -> EnfResult:
    """Track the mains-hum frequency and look for phase/frequency discontinuities.

    A recording made near mains-powered equipment carries a faint hum whose
    frequency wanders with grid load and whose phase runs continuously.
    Removing or inserting audio breaks that continuity: a phase step where a
    segment was cut out, a frequency step where audio from another time was
    pasted in.
    """
    if len(x) / sr < ENF_MIN_SECONDS:
        return EnfResult(False, f"recording shorter than {ENF_MIN_SECONDS:.0f} s")
    y = resample(x.astype(np.float64), sr, ENF_RATE)
    grid, k, snr = _strongest_mains_line(y, grids)
    if snr < ENF_MIN_SNR_DB:
        return EnfResult(False, f"no mains hum found (best line {snr:.1f} dB above background)",
                         grid_hz=grid, harmonic=k, snr_db=snr)
    fk = grid * k
    yb = sosfiltfilt(butter(4, [fk - 2.0, fk + 2.0], btype="band", fs=ENF_RATE, output="sos"), y)

    # Frequency track: long STFT frames, zero-padded, peak refined by parabola.
    f, t, z = stft(yb, ENF_RATE, nperseg=4 * ENF_RATE, noverlap=int(3.5 * ENF_RATE), nfft=2**16,
                   boundary=None, padded=False)
    band = (f > fk - 1.0) & (f < fk + 1.0)
    mag = np.abs(z[band])
    fb = f[band]
    idx = np.clip(mag.argmax(axis=0), 1, len(fb) - 2)
    cols = np.arange(mag.shape[1])
    a, b, c = (np.log(mag[idx - 1, cols] + EPS), np.log(mag[idx, cols] + EPS),
               np.log(mag[idx + 1, cols] + EPS))
    offset = 0.5 * (a - c) / (a - 2 * b + c + EPS)
    freqs = (fb[idx] + offset * (fb[1] - fb[0])) / k

    # Phase continuity: instantaneous-frequency deviation, smoothed over 100 ms.
    phase = np.unwrap(np.angle(hilbert(yb)))
    inst = np.diff(phase) * ENF_RATE / (2 * np.pi) - fk
    inst = uniform_filter1d(inst, size=ENF_RATE // 10)
    step = ENF_RATE // 20  # evaluate every 50 ms
    pt = np.arange(0, len(inst), step) / ENF_RATE
    dev = inst[::step]
    resid = dev - median_filter(dev, size=41)  # remove slow grid drift (~2 s)
    mad = np.median(np.abs(resid - np.median(resid))) * 1.4826 + EPS
    threshold = max(8 * mad, 0.4 * k)
    edge = (pt > 1.5) & (pt < pt[-1] - 1.5)  # filter start-up transients
    hits = np.flatnonzero((np.abs(resid) > threshold) & edge)

    events: list[dict] = []
    for i in hits:
        if events and pt[i] - events[-1]["time"] < 1.0:
            if abs(resid[i]) > events[-1]["_peak"]:
                events[-1].update(time=float(pt[i]), _peak=float(abs(resid[i])))
            continue
        events.append({"time": float(pt[i]), "_peak": float(abs(resid[i]))})
    for e in events:
        peak = e.pop("_peak")
        e["strength"] = round(peak / threshold, 2)
        e["kind"] = "phase"

    # Frequency steps between neighbouring 4 s frames that phase did not catch.
    jumps = np.abs(np.diff(freqs))
    fmad = np.median(np.abs(jumps - np.median(jumps))) * 1.4826 + EPS
    for i in np.flatnonzero(jumps > max(10 * fmad, 0.02)):
        tj = float((t[i] + t[i + 1]) / 2)
        if 2.0 < tj < t[-1] - 2.0 and not any(abs(tj - e["time"]) < 2.0 for e in events):
            events.append({"time": tj, "strength": round(float(jumps[i] / max(10 * fmad, 0.02)), 2),
                           "kind": "frequency"})
    events.sort(key=lambda e: e["time"])
    checked = len(x) / sr >= ENF_CONTINUITY_SECONDS and snr >= ENF_CONTINUITY_SNR_DB
    reason = "" if checked else (
        f"hum too weak ({snr:.0f} dB) for continuity analysis" if snr < ENF_CONTINUITY_SNR_DB
        else f"recording shorter than {ENF_CONTINUITY_SECONDS:.0f} s: too short for continuity analysis")
    return EnfResult(True, reason=reason, continuity_checked=checked, grid_hz=grid, harmonic=k, snr_db=snr,
                     times=t, freqs=freqs, phase_times=pt, phase_dev=resid,
                     discontinuities=events if checked else [])


# ----------------------------------------------------------- edit discontinuities

def digital_silence_runs(x: np.ndarray, sr: int, min_s: float = 0.02,
                         edge_s: float = 0.25, level: float = 1e-6) -> list[tuple[float, float]]:
    """Stretches of true digital silence away from the file's start and end.

    A microphone always records some noise; exact zeros in the middle of a
    recording usually mean audio was cut, muted or inserted by software.
    """
    silent = np.abs(x) < level
    if not silent.any():
        return []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], silent.astype(np.int8), [0]])))
    runs = []
    for s, e in zip(edges[::2], edges[1::2]):
        start, end = s / sr, e / sr
        if end - start >= min_s and start > edge_s and end < len(x) / sr - edge_s:
            runs.append((round(start, 3), round(end, 3)))
    return runs


def pause_segments(db: np.ndarray, min_frames: int = 8, below_db: float = 18.0,
                   stable_db: float = 6.0) -> list[tuple[float, float, float]]:
    """Real pauses: >=160 ms runs well below the surrounding speech, at a steady level.

    Brief dips between words are excluded: they never reach the room's noise
    level, and mistaking them for background produced false steps in testing.
    Returns (start_s, end_s, level_db) per pause.
    """
    local_speech = percentile_filter(db, 90, size=300)  # 6 s neighbourhood
    quiet = db < local_speech - below_db
    edges = np.flatnonzero(np.diff(np.concatenate([[0], quiet.astype(np.int8), [0]])))
    pauses = []
    for s, e in zip(edges[::2], edges[1::2]):
        if e - s < min_frames:
            continue
        seg = db[s:e]
        q75, q25 = np.percentile(seg, [75, 25])
        if q75 - q25 <= stable_db:
            pauses.append((s * 0.02, e * 0.02, float(np.median(seg))))
    return pauses


def noise_floor_steps(x: np.ndarray, sr: int, min_step_db: float = 10.0,
                      side_s: float = 6.0) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """Abrupt, sustained changes of the background-noise level.

    The background is the level of real pauses. Between every pair of
    neighbouring pauses, compare the pauses in the preceding and following
    6 s (at least two each side). A splice joining two recordings made in
    different conditions shows up as a step that stays changed.
    """
    pauses = pause_segments(frame_db(x, sr))
    mids = np.array([(s + e) / 2 for s, e, _ in pauses])
    levels = np.array([lvl for _, _, lvl in pauses])
    steps: list[dict] = []
    for i in range(len(pauses) - 1):
        t = (pauses[i][1] + pauses[i + 1][0]) / 2
        left = levels[(mids < t) & (mids >= t - side_s)]
        right = levels[(mids > t) & (mids <= t + side_s)]
        if len(left) < 2 or len(right) < 2:
            continue
        d = float(np.median(right) - np.median(left))
        if abs(d) < min_step_db:
            continue
        if steps and t - steps[-1]["time"] < side_s:
            if abs(d) > abs(steps[-1]["step_db"]):
                steps[-1].update(time=round(t, 2), step_db=round(d, 1))
            continue
        steps.append({"time": round(t, 2), "step_db": round(d, 1)})
    return steps, mids, levels


# ------------------------------------------------------------------- bandwidth

SOURCE_RATES = (8000, 11025, 16000, 22050, 24000, 32000)
# Band above a candidate edge must be this much weaker than the band below.
EMPTY_BAND_DB = -40.0


def effective_bandwidth(x: np.ndarray, sr: int) -> dict:
    """Detect audio that was upsampled from, or low-passed to, a lower bandwidth.

    A microphone recording leaves some noise right up to Nyquist. Audio that
    once lived at a lower sample rate (or went through a lossy encoder's
    low-pass) has an essentially empty band above that limit.

    Stage 1 finds the lowest standard source-rate edge with an empty band above
    it, skipping the resampler's transition zone. Stage 2 locates the cutoff
    (midpoint between in-band and empty-band levels). The exact original rate
    is not reported: speech often has no energy right up to its old Nyquist,
    so only the cutoff itself is reliable.
    """
    f, p = welch(x.astype(np.float64), sr, nperseg=8192)
    db = uniform_filter1d(10 * np.log10(p + EPS), size=3)
    nyq = sr / 2
    ratios = {}
    for rate in SOURCE_RATES:
        edge = rate / 2
        if edge > 0.8 * nyq:
            break
        below = p[(f > 0.5 * edge) & (f < 0.85 * edge)].sum()
        above = p[(f > 1.15 * edge) & (f < min(0.95 * nyq, 2.0 * edge))].sum()
        ratios[rate] = float(10 * np.log10((above + EPS) / (below + EPS)))

    result = {"sample_rate": sr, "cutoff_hz": None,
              "band_ratios_db": {str(k): round(v, 1) for k, v in ratios.items()}, "freqs": f, "psd_db": db}
    candidate = next((r for r, v in ratios.items() if v < EMPTY_BAND_DB), None)
    if candidate is None:
        return result

    edge = candidate / 2
    floor = np.median(db[(f > 1.15 * edge) & (f < min(0.95 * nyq, 2.0 * edge))])
    inband = np.median(db[(f > 0.5 * edge) & (f < 0.85 * edge)])
    above_mid = np.flatnonzero((f > 0.5 * edge) & (f < 1.15 * edge) & (db > (inband + floor) / 2))
    result["cutoff_hz"] = round(float(f[above_mid[-1]]) if above_mid.size else edge)
    return result
