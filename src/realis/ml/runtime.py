"""Shared device selection and a process-wide model cache."""

from __future__ import annotations

import threading
from collections.abc import Callable
from functools import cache
from typing import Any, TypeVar

import torch

T = TypeVar("T")

_models: dict[str, Any] = {}
_lock = threading.Lock()
# One GPU, many web requests: run inference one at a time.
gpu_lock = threading.Lock()


@cache
def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def device_info() -> dict[str, Any]:
    dev = device()
    info: dict[str, Any] = {"device": dev.type, "torch": torch.__version__}
    if dev.type == "cuda":
        props = torch.cuda.get_device_properties(0)
        info |= {"gpu": props.name, "vram_gb": round(props.total_memory / 2**30, 1),
                 "cuda": torch.version.cuda}
    return info


def get_model(name: str, loader: Callable[[], T]) -> T:
    """Load a model once and reuse it for the life of the process."""
    if name not in _models:
        with _lock:
            if name not in _models:
                _models[name] = loader()
    return _models[name]


def loaded_models() -> list[str]:
    return sorted(_models)
