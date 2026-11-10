"""Generated test videos with known edits (FFmpeg lavfi sources)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from audio_fixtures import recording, write_wav


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, timeout=120)


def continuous(path: Path, seconds: int = 6, size: str = "320x180") -> Path:
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def with_cut(path: Path, at: int = 3, seconds: int = 6) -> Path:
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=30:duration={at}",
           "-f", "lavfi", "-i", "mandelbrot=size=320x180:rate=30",
           "-filter_complex", f"[1:v]trim=duration={seconds - at},setpts=PTS-STARTPTS[b];[0:v][b]concat=n=2:v=1:a=0[v]",
           "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def frozen(path: Path, at_frame: int = 90, extra: int = 3) -> Path:
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
           "-vf", f"loop=loop={extra}:size=1:start={at_frame},setpts=N/30/TB",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def rate_converted(path: Path) -> Path:
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=6", "-vf", "fps=30",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def static(path: Path) -> Path:
    ffmpeg("-f", "lavfi", "-i", "smptebars=size=320x180:rate=30:duration=5",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def talking(path: Path, tmp: Path, seconds: int = 30, cut_at: float | None = None,
            audio_seconds: float | None = None, metadata: dict[str, str] | None = None) -> Path:
    """Video plus a hummed 'speech' track; optionally a 0.37 s cut in the audio."""
    audio = recording(seconds=audio_seconds or seconds)
    if cut_at is not None:
        import numpy as np
        sr = 16_000
        audio = np.concatenate([audio[: int(cut_at * sr)], audio[int((cut_at + 0.37) * sr):]])
    wav = tmp / f"{path.stem}_audio.wav"
    write_wav(wav, audio)
    tags = [a for k, v in (metadata or {}).items() for a in ("-metadata", f"{k}={v}")]
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=25:duration={seconds}", "-i", str(wav),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", *tags, str(path))
    return path
