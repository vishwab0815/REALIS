# REALIS backend (API + analysis engine) for Cloud Run or any container host.
# The web app is deployed separately (Vercel); see frontend/.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    REALIS_HOME=/srv/realis \
    REALIS_CASES=/tmp/realis/cases \
    HF_HOME=/tmp/hf

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# Locked dependencies, but CPU-only PyTorch: the CUDA build in uv.lock and the
# ~19 NVIDIA/Triton packages it pulls in (~5 GB) are useless without a GPU.
# The export is already fully resolved, so install it with --no-deps: letting
# uv re-resolve made timm pull the CUDA build of torch back in from PyPI.
RUN uv venv /opt/venv \
 && uv export --frozen --no-dev --no-emit-project --no-hashes \
      --no-emit-package torch --no-emit-package torchvision \
    | grep -viE '^(nvidia-|cuda-|triton)' > /tmp/requirements.txt \
 && uv pip install --no-cache --no-deps -r /tmp/requirements.txt \
 && uv pip install --no-cache --no-deps torch==2.14.1 torchvision==0.29.1 \
      --index-url https://download.pytorch.org/whl/cpu \
 && uv pip check \
 && rm /tmp/requirements.txt

COPY README.md ./
COPY src ./src
RUN uv pip install --no-cache --no-deps .

# Quick-scan models, baked in so cold starts do not re-download ~1.3 GB.
# The image must stay private: AntiDeepfake weights are CC BY-NC-SA (no
# redistribution). TruFor (deep scan) is not included.
RUN python -c "from realis.models_setup import setup_antideepfake, setup_commfor; setup_commfor(); setup_antideepfake()"

RUN useradd --create-home --uid 10001 realis && mkdir -p /tmp/realis && chown -R realis /tmp/realis
USER realis

EXPOSE 8080
CMD ["sh", "-c", "exec realis serve --host 0.0.0.0 --port ${PORT:-8080} --exclude trufor,frame_trufor"]
