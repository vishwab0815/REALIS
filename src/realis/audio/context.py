"""Audio analysis context: probe data and decoded sample views."""

from __future__ import annotations

from functools import cached_property
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: figures are only ever saved to files
import matplotlib.pyplot as plt
import numpy as np

from realis.audio import io
from realis.core.context import MediaContext

MODEL_RATE = 16_000


class AudioContext(MediaContext):
    @cached_property
    def probe(self) -> dict[str, Any]:
        return io.probe(self.path)

    @cached_property
    def has_audio(self) -> bool:
        return io.audio_stream(self.probe) is not None

    @cached_property
    def stream(self) -> dict[str, Any]:
        stream = io.audio_stream(self.probe)
        if stream is None:
            raise io.AudioDecodeError("file has no audio stream")
        return stream

    @property
    def codec(self) -> str:
        return str(self.stream.get("codec_name", ""))

    @cached_property
    def rate(self) -> int:
        """Native sample rate as stored in the file."""
        return int(self.stream.get("sample_rate") or 0)

    @cached_property
    def duration(self) -> float:
        """Full duration of the file, which may exceed what is analysed."""
        return float(self.probe.get("format", {}).get("duration") or len(self.samples) / self.rate)

    @cached_property
    def samples(self) -> np.ndarray:
        """Mono float32 at the native rate, capped at io.MAX_SECONDS."""
        return io.decode(self.path)

    @cached_property
    def samples16k(self) -> np.ndarray:
        """Mono float32 at 16 kHz, the rate speech models expect."""
        return io.decode(self.path, MODEL_RATE)

    @property
    def analysed_seconds(self) -> float:
        return len(self.samples) / self.rate

    @property
    def truncated(self) -> bool:
        return self.duration > self.analysed_seconds + 1.0

    def save_figure(self, name: str, fig: plt.Figure) -> str:
        out = self.artifact_path(name)
        fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
        plt.close(fig)
        return self.relative(out)
