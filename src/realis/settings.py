"""Filesystem locations, overridable with environment variables."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOME = Path(os.environ.get("REALIS_HOME", PROJECT_ROOT))

MODELS_DIR = HOME / "models"
WEB_DIST = Path(os.environ.get("REALIS_WEB_DIST", Path(__file__).parent / "web" / "dist"))

MAX_UPLOAD_MB = int(os.environ.get("REALIS_MAX_UPLOAD_MB", "500"))
JOB_WORKERS = int(os.environ.get("REALIS_JOB_WORKERS", "1"))  # one GPU: keep 1
THIRD_PARTY_DIR = HOME / "third_party"
CASES_DIR = Path(os.environ.get("REALIS_CASES", HOME / "cases"))

# Hosted deployments. All off by default, so a local install behaves as before.
# Shared code that every /api and /cases request must carry (header, ?key= or cookie).
ACCESS_CODE = os.environ.get("REALIS_ACCESS_CODE", "")
# Browser origins allowed to call the API, e.g. the Vercel site: comma-separated list and/or a regex.
CORS_ORIGINS = [o.strip() for o in os.environ.get("REALIS_CORS_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGIN_REGEX = os.environ.get("REALIS_CORS_ORIGIN_REGEX", "") or None
# Delete cases older than this many hours (0 = keep forever).
RETENTION_HOURS = float(os.environ.get("REALIS_RETENTION_HOURS", "0"))

# Upstream code for TruFor is fetched, not vendored: its licence restricts redistribution.
TRUFOR_REPO = "https://github.com/grip-unina/TruFor"
TRUFOR_SRC = THIRD_PARTY_DIR / "TruFor" / "test_docker" / "src"
TRUFOR_WEIGHTS_URL = "https://www.grip.unina.it/download/prog/TruFor/TruFor_weights.zip"
TRUFOR_WEIGHTS_MD5 = "7bee48f3476c75616c3c5721ab256ff8"
TRUFOR_WEIGHTS = MODELS_DIR / "trufor" / "trufor.pth.tar"

COMMFOR_REPO_ID = "OwensLab/commfor-model-384"
COMMFOR_DIR = MODELS_DIR / "commfor-384"

ANTIDEEPFAKE_REPO_ID = "nii-yamagishilab/mms-300m-anti-deepfake"
ANTIDEEPFAKE_DIR = MODELS_DIR / "antideepfake-mms-300m"
