"""Download and verify third-party model code and weights."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from huggingface_hub import hf_hub_download

from realis import settings

Log = Callable[[str], None]


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def setup_commfor(log: Log = print) -> Path:
    settings.COMMFOR_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.safetensors"):
        hf_hub_download(settings.COMMFOR_REPO_ID, name, local_dir=settings.COMMFOR_DIR)
    log(f"Community Forensics weights: {settings.COMMFOR_DIR}")
    return settings.COMMFOR_DIR


def setup_antideepfake(log: Log = print) -> Path:
    settings.ANTIDEEPFAKE_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.safetensors"):
        hf_hub_download(settings.ANTIDEEPFAKE_REPO_ID, name, local_dir=settings.ANTIDEEPFAKE_DIR)
    log(f"AntiDeepfake weights: {settings.ANTIDEEPFAKE_DIR}")
    return settings.ANTIDEEPFAKE_DIR


def setup_trufor(log: Log = print) -> Path:
    repo = settings.TRUFOR_SRC.parents[1]
    if not settings.TRUFOR_SRC.exists():
        log(f"Cloning TruFor code into {repo}")
        subprocess.run(["git", "clone", "--depth", "1", settings.TRUFOR_REPO, str(repo)], check=True)

    if settings.TRUFOR_WEIGHTS.exists():
        log(f"TruFor weights already present: {settings.TRUFOR_WEIGHTS}")
        return settings.TRUFOR_WEIGHTS

    target = settings.TRUFOR_WEIGHTS.parent
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "TruFor_weights.zip"
    log(f"Downloading TruFor weights from {settings.TRUFOR_WEIGHTS_URL}")
    with urllib.request.urlopen(settings.TRUFOR_WEIGHTS_URL, timeout=60) as resp, archive.open("wb") as out:
        shutil.copyfileobj(resp, out)
    if (digest := _md5(archive)) != settings.TRUFOR_WEIGHTS_MD5:
        archive.unlink()
        raise RuntimeError(f"TruFor weights checksum mismatch: {digest}")

    with zipfile.ZipFile(archive) as z:
        member = next(n for n in z.namelist() if n.endswith("trufor.pth.tar"))
        with z.open(member) as src, settings.TRUFOR_WEIGHTS.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    archive.unlink()
    log(f"TruFor weights: {settings.TRUFOR_WEIGHTS}")
    return settings.TRUFOR_WEIGHTS


def setup_all(log: Log = print) -> None:
    setup_commfor(log)
    setup_trufor(log)
    setup_antideepfake(log)
