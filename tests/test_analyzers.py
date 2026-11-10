import numpy as np
from PIL import Image, PngImagePlugin

from conftest import decode, jpeg_bytes
from realis.core.models import Severity, Status
from realis.image.analyzers.copy_move import CopyMoveAnalyzer
from realis.image.analyzers.jpeg_structure import JpegStructureAnalyzer, estimate_quality
from realis.image.analyzers.metadata import MetadataAnalyzer, compare_thumbnail
from realis.image.analyzers.noise import BLOCK, NoiseAnalyzer, noise_map
from realis.common.provenance import ProvenanceAnalyzer


def _titles(res):
    return [f.title for f in res.findings]


# --- JPEG structure ---------------------------------------------------------

def test_quality_estimate_matches_pillow_encoder(make_ctx, coffee):
    for q in (50, 75, 92):
        ctx = make_ctx(jpeg_bytes(coffee, q))
        quality, standard = estimate_quality(np.array(ctx.image.quantization[0]))
        assert (quality, standard) == (q, True)


def test_single_compression_not_flagged(make_ctx, coffee):
    res = JpegStructureAnalyzer().run(make_ctx(jpeg_bytes(coffee, 90)))
    assert res.status == Status.OK
    assert res.data["double_compression_stat"] < 0.08


def test_double_compression_flagged(make_ctx, coffee):
    twice = jpeg_bytes(decode(jpeg_bytes(coffee, 60)), 90)
    res = JpegStructureAnalyzer().run(make_ctx(twice))
    assert "Image was JPEG-compressed at least twice" in _titles(res)
    assert res.score > 0.5


def test_jpeg_analyzer_skips_png(make_ctx, coffee):
    res = JpegStructureAnalyzer().run(make_ctx(coffee, "img.png"))
    assert res.status == Status.SKIPPED


# --- Copy-move --------------------------------------------------------------

def test_copy_move_clean_image(make_ctx, coffee):
    res = CopyMoveAnalyzer().run(make_ctx(coffee, "img.png"))
    assert res.data["clusters"] == []


def test_copy_move_detects_clone(make_ctx, coffee):
    forged = coffee.copy()
    forged[230:350, 420:540] = coffee[40:160, 60:180]  # clone a textured patch
    res = CopyMoveAnalyzer().run(make_ctx(forged, "img.png"))
    assert res.data["clusters"], res.findings
    c = res.data["clusters"][0]
    boxes = [c["src_bbox"], c["dst_bbox"]]
    assert any(abs(b[0] - 60) < 40 and abs(b[1] - 40) < 40 for b in boxes)
    assert any(abs(b[0] - 420) < 40 and abs(b[1] - 230) < 40 for b in boxes)
    assert res.score > 0.7


# --- Noise ------------------------------------------------------------------

def test_noise_map_shows_spliced_noisy_region(make_ctx, coffee):
    rng = np.random.default_rng(0)
    forged = coffee.astype(np.float32)
    forged[96:256, 160:320] += rng.normal(0, 8, (160, 160, 3))
    forged = np.clip(forged, 0, 255).astype(np.uint8)
    ctx = make_ctx(forged, "img.png")
    sigma, valid = noise_map(ctx.gray, BLOCK)
    inside = sigma[3:8, 5:10][valid[3:8, 5:10]]
    # Flat table-top blocks right below and beside the patch.
    outside = np.concatenate([sigma[8:11, 4:10][valid[8:11, 4:10]], sigma[0:3, 6:11][valid[0:3, 6:11]]])
    assert np.median(inside) > 2.5 * np.median(outside)

    res = NoiseAnalyzer().run(ctx)
    assert res.status == Status.OK and len(res.artifacts) == 2


# --- Metadata ---------------------------------------------------------------

def test_metadata_flags_stable_diffusion_png(make_ctx, coffee):
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a cat, Steps: 30, Sampler: Euler a, CFG scale: 7, Seed: 1")
    res = MetadataAnalyzer().run(make_ctx(coffee, "img.png", pnginfo=info))
    assert res.decisive_label
    assert any(f.severity == Severity.CRITICAL for f in res.findings)


def test_metadata_flags_editing_software(make_ctx, coffee):
    exif = Image.Exif()
    exif[0x010F] = "Canon"
    exif[0x0131] = "Adobe Photoshop 25.0 (Windows)"
    res = MetadataAnalyzer().run(make_ctx(coffee, "img.jpg", exif=exif, quality=92))
    assert "Processed with image-editing software" in _titles(res)
    assert "Camera identified" in _titles(res)


def test_thumbnail_comparison(coffee):
    gray = coffee.mean(axis=2).astype(np.float32)
    small = np.asarray(Image.fromarray(coffee).resize((160, 107)))
    same = compare_thumbnail(jpeg_bytes(small, 85), gray)
    other = compare_thumbnail(jpeg_bytes(small[::-1].copy(), 85), gray)
    assert same["correlation"] > 0.95
    assert other["correlation"] < 0.75


def test_camera_jpeg_reencoded_with_stock_tables(make_ctx, coffee):
    exif = Image.Exif()
    exif[0x010F] = "NIKON CORPORATION"
    res = JpegStructureAnalyzer().run(make_ctx(coffee, "img.jpg", exif=exif, quality=88))
    assert "Camera metadata with a generic software encoder" in _titles(res)


# --- Provenance -------------------------------------------------------------

def test_no_c2pa_is_neutral(make_ctx, coffee):
    res = ProvenanceAnalyzer().run(make_ctx(jpeg_bytes(coffee, 90)))
    assert res.status == Status.OK
    assert res.confidence == 0
    assert "No C2PA manifest" in _titles(res)
