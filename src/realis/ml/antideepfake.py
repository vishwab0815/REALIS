"""NII AntiDeepfake (Ge et al., 2025): synthetic-speech detector, MMS-300M variant.

A wav2vec2 encoder post-trained on 56k hours of real and 18k hours of
synthetic speech across many languages, followed by mean pooling and a
2-way linear head (index 0 = fake, 1 = real).

Upstream ships fairseq code; fairseq does not install on modern Python, so
the published weights are mapped onto the equivalent transformers
Wav2Vec2Model. Licence: CC BY-NC-SA 4.0, research and educational use.
"""

from __future__ import annotations

import re

import numpy as np
import torch
from safetensors.torch import load_file
from transformers import Wav2Vec2Config, Wav2Vec2Model

from realis import settings
from realis.ml.runtime import device, get_model, gpu_lock

MODEL_KEY = "antideepfake-mms-300m"
LICENSE_NOTE = "AntiDeepfake weights: NII, CC BY-NC-SA 4.0, research and educational use only."
SAMPLE_RATE = 16_000
# Whole-clip scoring is done in chunks of at most this length (GPU memory).
CHUNK_SECONDS = 30.0
# Sliding windows for the timeline that localises partially synthetic audio.
WINDOW_SECONDS, HOP_SECONDS = 6.0, 3.0
BATCH = 8

# fairseq name fragment -> transformers name fragment (applied in order).
_RENAMES = [
    (r"^feature_extractor\.conv_layers\.(\d+)\.0\.", r"feature_extractor.conv_layers.\1.conv."),
    (r"^feature_extractor\.conv_layers\.(\d+)\.2\.1\.", r"feature_extractor.conv_layers.\1.layer_norm."),
    (r"^layer_norm\.", "feature_projection.layer_norm."),
    (r"^post_extract_proj\.", "feature_projection.projection."),
    (r"^encoder\.pos_conv\.0\.", "encoder.pos_conv_embed.conv."),
    (r"\.self_attn\.", ".attention."),
    (r"\.self_attn_layer_norm\.", ".layer_norm."),
    (r"\.fc1\.", ".feed_forward.intermediate_dense."),
    (r"\.fc2\.", ".feed_forward.output_dense."),
    (r"^mask_emb$", "masked_spec_embed"),
]
# Pre-training heads that inference never uses.
_UNUSED = ("quantizer.", "project_q.", "final_proj.")


def available() -> bool:
    return (settings.ANTIDEEPFAKE_DIR / "model.safetensors").exists()


class _Detector(torch.nn.Module):
    def __init__(self, config: Wav2Vec2Config):
        super().__init__()
        self.ssl = Wav2Vec2Model(config)
        self.head = torch.nn.Linear(config.hidden_size, 2)

    def forward(self, wav: torch.Tensor) -> torch.Tensor:
        hidden = self.ssl(wav).last_hidden_state  # [B, T, D]
        return self.head(hidden.mean(dim=1))  # [B, 2]


def _map_state(raw: dict[str, torch.Tensor], target_keys: set[str]) -> dict[str, torch.Tensor]:
    weight_norm_new = "ssl.encoder.pos_conv_embed.conv.parametrizations.weight.original0" in target_keys
    out: dict[str, torch.Tensor] = {}
    for key, tensor in raw.items():
        if key.startswith("proj_fc."):
            out["head." + key.removeprefix("proj_fc.")] = tensor
            continue
        name = key.removeprefix("m_ssl.model.")
        if name.startswith(_UNUSED):
            continue
        for pattern, repl in _RENAMES:
            name = re.sub(pattern, repl, name)
        if weight_norm_new:
            name = name.replace("conv.weight_g", "conv.parametrizations.weight.original0")
            name = name.replace("conv.weight_v", "conv.parametrizations.weight.original1")
        out["ssl." + name] = tensor
    return out


def load() -> _Detector:
    return get_model(MODEL_KEY, _load)


def _load() -> _Detector:
    config = Wav2Vec2Config.from_json_file(settings.ANTIDEEPFAKE_DIR / "config.json")
    config.layerdrop = 0.0
    config.apply_spec_augment = False
    model = _Detector(config)
    target = model.state_dict()
    mapped = _map_state(load_file(settings.ANTIDEEPFAKE_DIR / "model.safetensors"), set(target))
    missing = set(target) - set(mapped)
    unexpected = set(mapped) - set(target)
    # A silent mismatch would produce plausible-looking but meaningless scores.
    if missing or unexpected:
        raise RuntimeError(f"AntiDeepfake weight mapping failed: missing={sorted(missing)[:5]} "
                           f"unexpected={sorted(unexpected)[:5]}")
    model.load_state_dict(mapped, strict=True)
    return model.eval().to(device())


def _normalise(x: np.ndarray) -> np.ndarray:
    """Upstream applies layer_norm over the whole input waveform."""
    return (x - x.mean()) / np.sqrt(x.var() + 1e-5)


@torch.inference_mode()
def _fake_logit_margin(model: _Detector, segments: list[np.ndarray]) -> np.ndarray:
    """log P(fake) - log P(real) per segment (segments in a batch share a length)."""
    out = []
    for i in range(0, len(segments), BATCH):
        batch = torch.from_numpy(np.stack([_normalise(s) for s in segments[i:i + BATCH]])).float()
        logits = model(batch.to(device())).float().cpu()
        out.append((logits[:, 0] - logits[:, 1]).numpy())
    return np.concatenate(out)


def predict(wav16k: np.ndarray) -> dict:
    """Probability that the speech is synthetic, overall and per time window."""
    model = load()
    n = len(wav16k)
    chunk = int(CHUNK_SECONDS * SAMPLE_RATE)
    win, hop = int(WINDOW_SECONDS * SAMPLE_RATE), int(HOP_SECONDS * SAMPLE_RATE)
    with gpu_lock:
        chunks = [wav16k[i:i + chunk] for i in range(0, n, chunk)]
        # Trailing scraps under 2 s carry little evidence; fold them out.
        chunks = [c for c in chunks if len(c) >= 2 * SAMPLE_RATE] or [wav16k]
        margins = np.array([_fake_logit_margin(model, [c])[0] for c in chunks])
        weights = np.array([len(c) for c in chunks], dtype=float)
        overall = float(np.average(margins, weights=weights))

        timeline = []
        if n > win + hop:
            starts = list(range(0, n - win + 1, hop))
            window_margins = _fake_logit_margin(model, [wav16k[s:s + win] for s in starts])
            timeline = [{"start": round(s / SAMPLE_RATE, 2), "end": round((s + win) / SAMPLE_RATE, 2),
                         "fake_probability": round(float(1 / (1 + np.exp(-m))), 4)}
                        for s, m in zip(starts, window_margins)]
        if device().type == "cuda":
            torch.cuda.empty_cache()
    return {
        "fake_probability": float(1 / (1 + np.exp(-overall))),
        "chunk_fake_probabilities": [round(float(1 / (1 + np.exp(-m))), 4) for m in margins],
        "timeline": timeline,
    }
