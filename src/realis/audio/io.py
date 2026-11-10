"""Audio probing and decoding through FFmpeg (handles WAV, MP3, AAC/M4A, Opus, FLAC...)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

# Analyse at most this much audio: one hour of 48 kHz float32 would need ~700 MB.
MAX_SECONDS = 600.0


class AudioDecodeError(RuntimeError):
    pass


def _tool(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise AudioDecodeError(f"{name} not found on PATH: install FFmpeg")
    return exe


def available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, timeout=60,
    )
    if out.returncode != 0:
        raise AudioDecodeError(out.stderr.decode(errors="replace").strip() or "ffprobe failed")
    return json.loads(out.stdout)


def audio_stream(info: dict[str, Any]) -> dict[str, Any] | None:
    return next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)


def decode(path: Path, sample_rate: int | None = None, max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """First audio stream as mono float32, optionally resampled."""
    cmd = [_tool("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0", "-ac", "1"]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    cmd += ["-t", str(max_seconds), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    if out.returncode != 0:
        raise AudioDecodeError(out.stderr.decode(errors="replace").strip() or "ffmpeg failed")
    samples = np.frombuffer(out.stdout, dtype=np.float32)
    if samples.size == 0:
        raise AudioDecodeError("no audio samples decoded")
    return samples
