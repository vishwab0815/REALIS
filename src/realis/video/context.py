"""Video analysis context: video stream facts, sampled frames, and the audio track."""

from __future__ import annotations

from functools import cached_property
from typing import Any

import numpy as np
from PIL import Image

from realis.audio.context import AudioContext
from realis.video import io

MIN_SAMPLES, MAX_SAMPLES = 8, 32
SECONDS_PER_SAMPLE = 2.5
THUMB_SIDE = 320


class VideoContext(AudioContext):
    """A video is frames plus (usually) an audio track; audio analyzers reuse the parent class."""

    @cached_property
    def video(self) -> dict[str, Any]:
        stream = io.video_stream(self.probe)
        if stream is None:
            raise io.VideoDecodeError("file has no video stream")
        return stream

    @property
    def video_codec(self) -> str:
        return str(self.video.get("codec_name", ""))

    @cached_property
    def fps(self) -> float:
        return io.rate(self.video.get("avg_frame_rate")) or io.rate(self.video.get("r_frame_rate"))

    @cached_property
    def size(self) -> tuple[int, int]:
        """Display size (width, height), after the rotation flag is applied."""
        w, h = int(self.video.get("width", 0)), int(self.video.get("height", 0))
        return (h, w) if io.rotation(self.video) in (90, 270) else (w, h)

    @cached_property
    def duration(self) -> float:
        fmt = float(self.probe.get("format", {}).get("duration") or 0)
        return fmt or float(self.video.get("duration") or 0)

    @property
    def analysed_seconds(self) -> float:
        return min(self.duration, io.MAX_SECONDS)

    @property
    def truncated(self) -> bool:
        return self.duration > io.MAX_SECONDS + 1.0

    @cached_property
    def sample_times(self) -> list[float]:
        """Evenly spaced sample points at the centre of equal slices of the analysed span."""
        span = self.analysed_seconds
        count = int(np.clip(round(span / SECONDS_PER_SAMPLE), MIN_SAMPLES, MAX_SAMPLES))
        if self.fps:
            count = max(1, min(count, int(span * self.fps)))
        return [round((i + 0.5) * span / count, 3) for i in range(count)]

    @cached_property
    def frames(self) -> list[tuple[float, np.ndarray]]:
        """Sampled frames as (time, RGB) pairs, shared by every frame-level analyzer."""
        out = []
        for i, t in enumerate(self.sample_times):
            out.append((t, io.frame_at(self.path, t)))
            self.report_progress((i + 1) / len(self.sample_times), f"decoding frame {i + 1}/{len(self.sample_times)}")
        return out

    @cached_property
    def thumbnails(self) -> list[dict]:
        """Small JPEGs of the sampled frames for filmstrips: [{time, path}]."""
        folder = self.artifact_dir / "frames"
        folder.mkdir(parents=True, exist_ok=True)
        out = []
        for i, (t, rgb) in enumerate(self.frames):
            img = Image.fromarray(rgb)
            img.thumbnail((THUMB_SIDE, THUMB_SIDE))
            path = folder / f"frame_{i:03d}.jpg"
            img.save(path, quality=82)
            out.append({"time": t, "path": self.relative(path)})
        return out
