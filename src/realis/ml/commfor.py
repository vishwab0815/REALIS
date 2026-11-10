"""Community Forensics ViT detector (Park & Owens, CVPR 2025; MIT licence).

Trained on images from ~4,800 generators. Re-implements the upstream test
transform (resize short side to 440, crop 384, ImageNet normalisation) and
loads the published weights without the upstream training code.
"""

from __future__ import annotations

import json

import timm
import torch
from PIL import Image
from safetensors.torch import load_file
from torchvision import transforms

from realis import settings
from realis.ml.runtime import device, get_model, gpu_lock

MODEL_KEY = "commfor-384"
RESIZE, CROP = 440, 384
_MEAN, _STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def available() -> bool:
    return (settings.COMMFOR_DIR / "model.safetensors").exists()


def load() -> torch.nn.Module:
    return get_model(MODEL_KEY, _load)


def _load() -> torch.nn.Module:
    cfg = json.loads((settings.COMMFOR_DIR / "config.json").read_text())
    name = f"vit_{cfg['model_size']}_patch{cfg['patch_size']}_{cfg['input_size']}"
    model = timm.create_model(name, pretrained=False, num_classes=1)
    state = load_file(settings.COMMFOR_DIR / "model.safetensors")
    model.load_state_dict({k.removeprefix("vit."): v for k, v in state.items()})
    return model.eval().to(device())


_resize = transforms.Resize(RESIZE)
_to_tensor = transforms.Compose([transforms.ToTensor(), transforms.Normalize(_MEAN, _STD)])


@torch.inference_mode()
def predict(img: Image.Image) -> dict[str, float | list[float]]:
    """Probability of being AI-generated, from the centre crop and four corners."""
    model = load()
    resized = _resize(img.convert("RGB"))
    crops = transforms.FiveCrop(CROP)(resized)  # 4 corners + centre
    batch = torch.stack([_to_tensor(c) for c in crops]).to(device())
    with gpu_lock:
        logits = model(batch).squeeze(1).float().cpu()
    probs = torch.sigmoid(logits)
    return {
        "probability": float(torch.sigmoid(logits.mean())),
        "center_probability": float(probs[4]),
        "crop_probabilities": [round(float(p), 4) for p in probs],
    }
