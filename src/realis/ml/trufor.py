"""TruFor (Guillaro et al., CVPR 2023): manipulation localisation + integrity score.

The upstream code is fetched into third_party/ by `realis setup-models`
rather than vendored, because its licence permits informational and
non-profit use only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F
from numpy._core.multiarray import scalar as np_scalar
from yacs.config import CfgNode as CN

from realis import settings
from realis.ml.runtime import device, get_model, gpu_lock

MODEL_KEY = "trufor"
LICENSE_NOTE = "TruFor weights/code: GRIP-UNINA licence, informational and non-profit use only."
# Full-image inference up to this many pixels; larger images are tiled.
MAX_PIXELS = 2_400_000
TILE, OVERLAP = 1280, 128


def available() -> bool:
    return settings.TRUFOR_WEIGHTS.exists() and settings.TRUFOR_SRC.exists()


def load() -> torch.nn.Module:
    return get_model(MODEL_KEY, _load)


def _config() -> CN:
    c = CN()
    c.DATASET = CN({"NUM_CLASSES": 2})
    c.MODEL = CN()
    c.MODEL.NAME = "detconfcmx"
    c.MODEL.PRETRAINED = ""
    c.MODEL.MODS = ("RGB", "NP++")
    c.MODEL.EXTRA = CN({
        "BACKBONE": "mit_b2", "DECODER": "MLPDecoder", "DECODER_EMBED_DIM": 512,
        "PREPRC": "imagenet", "BN_EPS": 0.001, "BN_MOMENTUM": 0.1,
        "DETECTION": "confpool", "CONF": True,
    })
    return c


def _load() -> torch.nn.Module:
    src = str(settings.TRUFOR_SRC)
    sys.path.insert(0, src)
    try:
        from models.cmx.builder_np_conf import myEncoderDecoder  # type: ignore[import-not-found]
    finally:
        sys.path.remove(src)
    model = myEncoderDecoder(cfg=_config())
    # The checkpoint stores two numpy scalars next to the tensors; allow exactly
    # those instead of falling back to unsafe unpickling.
    allowed = [(np_scalar, "numpy.core.multiarray.scalar"), np.dtype] + [
        getattr(np.dtypes, n) for n in dir(np.dtypes) if n.endswith("DType")]
    with torch.serialization.safe_globals(allowed):
        ckpt = torch.load(settings.TRUFOR_WEIGHTS, map_location="cpu", weights_only=True)
    model.load_state_dict(ckpt["state_dict"])
    return model.eval().to(device())


@dataclass
class TruForOutput:
    localization: np.ndarray  # P(manipulated) per pixel
    confidence: np.ndarray  # reliability of the localization per pixel
    score: float  # whole-image integrity score: P(manipulated)
    tiled: bool


def _forward(model: torch.nn.Module, rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    x = torch.from_numpy(rgb.transpose(2, 0, 1).copy()).float().div_(256.0)[None].to(device())
    pred, conf, det, _ = model(x)
    loc = F.softmax(pred[0], dim=0)[1].float().cpu().numpy()
    conf_map = torch.sigmoid(conf[0, 0]).float().cpu().numpy()
    return loc, conf_map, float(torch.sigmoid(det).item())


def _tiles(n: int) -> list[int]:
    if n <= TILE:
        return [0]
    step = TILE - OVERLAP
    starts = list(range(0, n - TILE, step)) + [n - TILE]
    return sorted(set(starts))


@torch.inference_mode()
def predict(rgb: np.ndarray) -> TruForOutput:
    model = load()
    h, w = rgb.shape[:2]
    with gpu_lock:
        if h * w <= MAX_PIXELS:
            loc, conf, score = _forward(model, rgb)
            out = TruForOutput(loc, conf, score, tiled=False)
        else:
            # Tiles keep native resolution (resizing would erase Noiseprint++
            # traces); maps are averaged in overlaps, the score is the maximum.
            loc_acc = np.zeros((h, w), np.float32)
            conf_acc = np.zeros((h, w), np.float32)
            count = np.zeros((h, w), np.float32)
            scores = []
            for y in _tiles(h):
                for x in _tiles(w):
                    tile = rgb[y:y + TILE, x:x + TILE]
                    loc, conf, score = _forward(model, tile)
                    th, tw = tile.shape[:2]
                    loc_acc[y:y + th, x:x + tw] += loc
                    conf_acc[y:y + th, x:x + tw] += conf
                    count[y:y + th, x:x + tw] += 1
                    scores.append(score)
            out = TruForOutput(loc_acc / count, conf_acc / count, max(scores), tiled=True)
        if device().type == "cuda":
            torch.cuda.empty_cache()
    return out
