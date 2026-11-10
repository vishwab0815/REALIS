"""Video probing and frame extraction through FFmpeg."""

from __future__ import annotations

import io as _io
import subprocess
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from realis.audio.io import AudioDecodeError, _tool

# Analyse at most this much of a video.
MAX_SECONDS = 600.0
# Resolution of the dense temporal scan: enough to see cuts, small enough to stream.
SCAN_W, SCAN_H = 128, 72


class VideoDecodeError(AudioDecodeError):
    pass


def video_stream(info: dict[str, Any]) -> dict[str, Any] | None:
    """First real video stream (cover art embedded in audio files does not count)."""
    return next((s for s in info.get("streams", [])
                 if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)


def rate(value: str | None) -> float:
    """ffprobe rational like '30000/1001' -> 29.97; 0 when unknown."""
    try:
        r = Fraction(value or "0/1")
        return float(r) if r.denominator else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def rotation(stream: dict[str, Any]) -> int:
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            return int(side["rotation"]) % 360
    return int(stream.get("tags", {}).get("rotate", 0) or 0) % 360


def frame_at(path: Path, t: float, max_side: int = 1024) -> np.ndarray:
    """One frame as RGB, decoded at time t (seconds), scaled so its long side <= max_side.

    Seeking before the input jumps to the previous keyframe and decodes forward,
    which is both fast and frame-accurate. FFmpeg applies the rotation flag, so
    portrait phone videos come out upright.
    """
    scale = (f"scale='if(gte(iw,ih),min(iw,{max_side}),-2)':'if(gte(iw,ih),-2,min(ih,{max_side}))'")
    cmd = [_tool("ffmpeg"), "-v", "error", "-nostdin", "-ss", f"{max(t, 0):.3f}", "-i", str(path),
           "-map", "0:v:0", "-frames:v", "1", "-vf", scale, "-f", "image2pipe", "-c:v", "png", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=120)
    if out.returncode != 0 or not out.stdout:
        raise VideoDecodeError(out.stderr.decode(errors="replace").strip() or f"no frame at {t:.2f} s")
    return np.asarray(Image.open(_io.BytesIO(out.stdout)).convert("RGB"))


def scan_frames(path: Path, max_seconds: float = MAX_SECONDS) -> Iterator[np.ndarray]:
    """Every decoded frame as a small grayscale array, streamed (never all in memory)."""
    cmd = [_tool("ffmpeg"), "-v", "error", "-nostdin", "-t", str(max_seconds), "-i", str(path),
           "-map", "0:v:0", "-vf", f"scale={SCAN_W}:{SCAN_H},format=gray", "-fps_mode", "passthrough",
           "-f", "rawvideo", "-"]
    size = SCAN_W * SCAN_H
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert proc.stdout is not None
        while chunk := proc.stdout.read(size):
            if len(chunk) < size:
                break
            yield np.frombuffer(chunk, dtype=np.uint8).reshape(SCAN_H, SCAN_W)
    finally:
        proc.kill()
        proc.wait()
