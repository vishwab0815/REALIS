from pathlib import Path

import pytest
from PIL import Image
from skimage import data

from realis import settings
from realis.ml import commfor

SAMPLES = sorted((settings.THIRD_PARTY_DIR / "Community-Forensics" / "test_images").glob("*.png"))

needs_commfor = pytest.mark.skipif(not commfor.available(), reason="run `realis setup-models`")


@needs_commfor
@pytest.mark.skipif(not SAMPLES, reason="Community Forensics sample images not present")
@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: Path(p).name)
def test_commfor_flags_dalle2_samples(path):
    assert commfor.predict(Image.open(path))["probability"] > 0.8


@needs_commfor
@pytest.mark.parametrize("name", ["coffee", "chelsea", "astronaut", "rocket"])
def test_commfor_passes_real_photos(name):
    assert commfor.predict(Image.fromarray(getattr(data, name)()))["probability"] < 0.2


@needs_commfor
def test_commfor_handles_odd_modes():
    for mode in ("L", "RGBA", "P", "CMYK"):
        img = Image.fromarray(data.coffee()).convert(mode)
        out = commfor.predict(img)
        assert 0.0 <= out["probability"] <= 1.0 and len(out["crop_probabilities"]) == 5
