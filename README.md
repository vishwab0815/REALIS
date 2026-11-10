# REALIS

**Real-media Evidence, Authenticity & Lineage Intelligence System** · *Know what's real.*

Evidence-driven forensics for images, audio and video: is it AI-generated, was it edited, and
can the evidence be trusted?

## Getting started

### 1. What you need

- **OS:** Windows 10/11, Linux (x86-64 or ARM64), or macOS on Apple Silicon (M1 or newer).
  Intel Macs are not supported: PyTorch no longer publishes builds for them.
- **Disk:** about 10 GB free (Python packages including PyTorch ~4 GB, AI models ~1.6 GB).
- **Memory:** 8 GB RAM minimum, 16 GB recommended.
- **GPU (optional):** an NVIDIA GPU with a recent driver (CUDA 13) makes analysis much faster.
  Without one, REALIS runs on the CPU: seconds per image, up to a few minutes per video.

### 2. Install the tools (once)

| Tool | Windows (PowerShell) | macOS (Homebrew) | Linux (Ubuntu/Debian) |
|---|---|---|---|
| Git | `winget install Git.Git` | `xcode-select --install` | `sudo apt install git` |
| uv (installs Python 3.12 for you) | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| FFmpeg (audio and video) | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Node.js 22 LTS or newer (builds the web app) | `winget install OpenJS.NodeJS.LTS` | `brew install node` | the LTS installer from [nodejs.org](https://nodejs.org) (apt's version is too old) |

Then **open a new terminal** so the new tools are on your PATH, and check them:

```
git --version
uv --version
ffmpeg -version
node --version
```

### 3. Download and set up REALIS (once)

```
git clone https://github.com/vishwab0815/REALIS.git
cd REALIS
uv sync                              # Python 3.12 and all packages (first run downloads ~4 GB)
uv run realis setup-models           # AI model weights (~1.6 GB)
npm --prefix frontend ci             # web app packages
npm --prefix frontend run build      # build the web app
```

`setup-models` downloads third-party model weights under their own licences (see
[Known limitations](#known-limitations)); they stay on your machine and are not part of this repository.

### 4. Run

```
uv run realis serve --open
```

Your browser opens <http://127.0.0.1:8000>. Wait until the chips in the top bar say **ready**
(the first start loads the AI models), then drop an image, audio or video file. Stop the server
with `Ctrl+C`. Next time, only step 4 is needed.

Everything runs locally: uploaded files are stored as sealed evidence under `cases/` in the project
folder and never leave your machine.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Page says **"Frontend not built"** | Run the two `npm --prefix frontend ...` commands from step 3. |
| **"FFmpeg missing"** chip, audio/video fail | Install FFmpeg, open a new terminal, check `ffmpeg -version`. |
| A model chip says **"not installed"** | Run `uv run realis setup-models` again. |
| **"CPU mode"** chip | No usable NVIDIA GPU or the driver is too old. Everything still works, only slower. |
| TruFor download fails | Its university server can be slow or down; retry later, or run without it: `uv run realis serve --exclude trufor`. |
| Port 8000 is busy | `uv run realis serve --port 8080 --open` |

## Using REALIS

The web app: drop a file (optionally with **deep scan**), watch the job progress, then get a verdict
with two meters (AI generation, editing), per-analyzer findings, and a viewer: image layers, or an
audio/video player with a filmstrip and an interactive evidence timeline (click any marker or
"▶" chip to jump to that moment). Every case stays in the history sidebar.

Command line:

```
uv run realis analyze clip.mp4 --open         # analysis + HTML report (deep scan by default)
uv run realis analyze call.m4a --quick        # skip deep-scan analyzers
uv run realis serve --exclude trufor          # run without TruFor
uv run realis verify-case CASE-YYYYMMDD-xxxxxx
uv run realis analyzers
```

Development:

```
uv run pytest                                 # backend tests
npm --prefix frontend test                    # frontend tests
npm --prefix frontend run dev                 # UI dev server on :5173, proxied to :8000
```

Optional: install ExifTool for deeper image metadata parsing.

Configuration (environment variables): `REALIS_HOME` (data root), `REALIS_CASES`,
`REALIS_MAX_UPLOAD_MB` (default 500), `REALIS_JOB_WORKERS` (default 1: one GPU).

## Web API

| Endpoint | Purpose |
|---|---|
| `POST /api/jobs` (multipart `file`, `deep`) | Start an analysis; returns a job (202) |
| `GET /api/jobs/{id}` | Status, stage, progress; the full result when done |
| `GET /api/jobs` | Running and queued jobs |
| `POST /api/analyze` | Synchronous analysis for scripts and small files |
| `GET /api/cases?q=` / `GET /api/cases/{id}` | Case history / one case's reports |
| `GET /api/health` | Runtime, models, analyzers, supported types, limits |
| `GET /cases/...` | Sealed evidence copies (with byte ranges for seeking), reports, figures |

## How a case flows

1. **Ingest**: SHA-256 the file, store a read-only copy under `cases/<case>/evidence/`.
2. **Verify**: re-hash before and after analysis.
3. **Analyse**: every analyzer registered for the file's media type runs independently; one
   failing never sinks the case.
4. **Fuse**: confidence-weighted log-odds, answered separately for *AI generation* and *editing*.
   Provenance-grade evidence (C2PA, generator signatures) is decisive; otherwise a "strong"
   verdict needs two independent analyzers, because every ML detector has false positives.
5. **Report**: JSON (machine) + HTML (examiner) with figures and limitations.
6. **Custody log**: every step is appended to a hash-chained `custody.jsonl`.

## Image analyzers

| Analyzer | Role | Weight in verdict |
|---|---|---|
| `c2pa_provenance` | Content Credentials: signer, AI declarations, post-signing tampering (all media) | High, can be decisive |
| `ai_generated` | Community Forensics ViT (CVPR 2025, MIT): whole-image AI generation | High for positives, low for negatives |
| `trufor` | TruFor (CVPR 2023): manipulation score + localisation + reliability maps | High |
| `metadata` | EXIF/XMP/PNG text, AI generator signatures, editing software, EXIF-thumbnail mismatch | Medium, can be decisive |
| `jpeg_structure` | Quantization fingerprint, quality estimate, double-compression detection | Medium |
| `copy_move` | Cloned regions (SIFT g2NN + RANSAC) | Medium-high |
| `ela` | Texture-normalised ELA maps | Visual aid only |
| `noise_inconsistency` | Block noise-level maps | Visual aid only |

## Audio analyzers

| Analyzer | Role | Weight in verdict |
|---|---|---|
| `synthetic_voice` | NII AntiDeepfake MMS-300M (2025): AI/cloned speech, with a timeline for partial fakes | High for positives, low for negatives |
| `enf` | Mains-hum (50/60 Hz) tracking: phase/frequency breaks reveal cuts and inserts | High when hum is present |
| `edit_discontinuity` | Digital silence inside the recording; abrupt background-noise changes between pauses | Medium |
| `bandwidth` | Empty upper band in lossless files: upsampled from 16-24 kHz (TTS, telephony) or transcoded | Low-medium |
| `audio_metadata` | Container tags: AI-voice tool signatures, editing software, device, encoder | Medium, can be decisive |

## Video analyzers

The audio analyzers above also run on a video's soundtrack, and C2PA applies to video containers.

| Analyzer | Role | Weight in verdict |
|---|---|---|
| `frame_ai` | Image AI detector on 8-32 evenly sampled frames, as a timeline with thumbnails | High for positives, low for negatives |
| `temporal_edits` | Every frame at low resolution: hard cuts, frozen/inserted frames, frame-rate conversion | Medium |
| `video_metadata` | AI video generator and editor signatures, device, audio/video track length mismatch | Medium, can be decisive |
| `frame_trufor` | TruFor on up to 6 keyframes (deep scan only) | Medium-high |

## Known limitations

- Scores are heuristic and uncalibrated until a labelled benchmark is added.
- The image AI detector misses many images from the newest commercial generators and is
  sensitive to JPEG recompression (DALL-E 2 samples fell from >0.9 to 0.14-0.56 after one
  quality-85 re-save).
- The voice detector produced a false positive on heavily produced film audio in local testing;
  its error rate on the Deepfake-Eval-2024 in-the-wild set is about 30%.
- ENF only helps when mains hum was recorded; continuity is judged only on recordings of at least
  20 s with strong hum. Audio and video longer than 10 minutes are analysed up to the first 10 minutes.
- Video: frames are judged by an image detector (not trained on video); there is no dedicated
  face-swap or AI-video detector yet, because no credible open model could be loaded safely.
  Dissolves are not reported as cuts and a single dropped frame is not detectable.
- Licences: TruFor (GRIP-UNINA) is **informational and non-profit use only**; AntiDeepfake (NII)
  is **CC BY-NC-SA 4.0, research and educational use**. Weights are downloaded into `models/`
  and `third_party/`, not redistributed.

Adding an analyzer: subclass `realis.core.analyzer.Analyzer`, set `modalities`, decorate
with `@register`, and import it in the media type's `analyzers/__init__.py`.
