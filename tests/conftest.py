import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from skimage import data

from realis.common.provenance import _c2pa
from realis.core.context import ImageContext

# Some systems block the C2PA native library (e.g. Windows Smart App Control); then that check is skipped.
C2PA_AVAILABLE = _c2pa()[1] is None


def jpeg_bytes(arr: np.ndarray, quality: int) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def decode(b: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(b)).convert("RGB"))


@pytest.fixture
def coffee() -> np.ndarray:
    return data.coffee()


@pytest.fixture
def make_ctx(tmp_path: Path):
    """Write raw bytes or an array to disk and wrap it in an ImageContext."""

    def _make(content: bytes | np.ndarray, name: str = "img.jpg", **save_kwargs) -> ImageContext:
        path = tmp_path / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            Image.fromarray(content).save(path, **save_kwargs)
        return ImageContext(path, "0" * 64, tmp_path)

    return _make
