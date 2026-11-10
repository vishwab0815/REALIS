"""Web service: the React app plus a JSON API over the forensic pipeline.

Binds to localhost by default: uploaded evidence never leaves the machine.

API
  GET  /api/health                 runtime, models, analyzers, limits
  POST /api/jobs                   upload a file (multipart: file, deep) -> job (202)
  GET  /api/jobs/{id}              job status, progress and, when done, the result
  GET  /api/jobs                   active jobs
  POST /api/analyze                synchronous analysis (scripts; small files)
  GET  /api/cases?limit=&q=        case history summaries
  GET  /api/cases/{case_id}        full reports of one case
  GET  /cases/...                  sealed evidence copies, reports and figures
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from realis import DISPLAY_NAME, FULL_NAME, TOOL_NAME, __version__, settings
from realis.audio import io as audio_io
from realis.cases import CaseIndex
from realis.core.analyzer import analyzers_for
from realis.jobs import JobManager
from realis.ml import antideepfake, commfor, runtime, trufor
from realis.pipeline import AUDIO_SUFFIXES, IMAGE_SUFFIXES, SUPPORTED_SUFFIXES, VIDEO_SUFFIXES, analyze_media
from realis.video import io as video_io

log = logging.getLogger("realis.server")

MODEL_MODULES = {"ai_generated": commfor, "trufor": trufor, "synthetic_voice": antideepfake}
CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
NOT_BUILT = """<!doctype html><meta charset=utf-8><title>REALIS</title>
<body style="font:16px system-ui;background:#0c0e12;color:#e7e9ee;padding:40px">
<h1>Frontend not built</h1><p>Run <code>npm --prefix frontend ci</code> and
<code>npm --prefix frontend run build</code>, then reload. The API is available under <code>/api</code>.</p>"""


def _warmup(skip: set[str]) -> None:
    """Load models in the background so the first upload is not slow."""
    for analyzer, module in MODEL_MODULES.items():
        if analyzer in skip or not module.available():
            continue
        try:
            module.load()
            log.info("loaded model for %s", analyzer)
        except Exception:
            log.exception("could not load model for %s", analyzer)


def create_app(
    cases_dir: Path = settings.CASES_DIR,
    exclude: list[str] | None = None,
    warmup: bool = True,
    web_dist: Path = settings.WEB_DIST,
    max_upload_mb: int = settings.MAX_UPLOAD_MB,
) -> FastAPI:
    cases_dir = cases_dir.resolve()
    cases_dir.mkdir(parents=True, exist_ok=True)
    uploads = cases_dir.parent / ".uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    skip = sorted(set(exclude or []))
    max_bytes = max_upload_mb * 1024 * 1024
    index = CaseIndex(cases_dir)

    def run(path: Path, name: str, deep: bool, progress) -> dict[str, Any]:
        report, _ = analyze_media(path, cases_dir, None, None, name, skip or None, deep=deep, progress=progress)
        return index.payload(report)

    jobs = JobManager(run, workers=settings.JOB_WORKERS)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if warmup:
            threading.Thread(target=_warmup, args=(set(skip),), daemon=True).start()
        yield
        jobs.shutdown()

    app = FastAPI(title=DISPLAY_NAME, description=FULL_NAME, version=__version__, lifespan=lifespan)
    app.mount("/cases", StaticFiles(directory=cases_dir), name="cases")

    async def receive(file: UploadFile) -> tuple[Path, str, int]:
        """Stream an upload to a temp file, enforcing type and size limits."""
        name = Path(file.filename or "upload").name
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(415, f"Unsupported file type '{suffix or 'none'}'. "
                                     f"Allowed: {', '.join(sorted(SUPPORTED_SUFFIXES))}")
        tmp = uploads / f"{uuid.uuid4().hex}{suffix}"
        size = 0
        try:
            with tmp.open("wb") as out:
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, f"File larger than {max_upload_mb} MB")
                    out.write(chunk)
            if size == 0:
                raise HTTPException(400, "Empty file")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return tmp, name, size

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        analyzers = analyzers_for("image") | analyzers_for("audio") | analyzers_for("video")
        return {
            "tool": TOOL_NAME,
            "name": DISPLAY_NAME,
            "full_name": FULL_NAME,
            "version": __version__,
            "runtime": runtime.device_info(),
            "ffmpeg": audio_io.available(),
            "models": {
                analyzer: {"installed": module.available(),
                           "loaded": module.MODEL_KEY in runtime.loaded_models(),
                           "enabled": analyzer not in skip}
                for analyzer, module in MODEL_MODULES.items()
            },
            "analyzers": [
                {"name": name, "title": cls.title or name, "description": cls.description,
                 "modalities": list(cls.modalities), "weight": cls.weight, "kind": cls.evidence_kind,
                 "deep": cls.deep, "enabled": name not in skip}
                for name, cls in analyzers.items()
            ],
            "supported_types": {"image": sorted(IMAGE_SUFFIXES), "audio": sorted(AUDIO_SUFFIXES),
                                "video": sorted(VIDEO_SUFFIXES)},
            "limits": {"max_upload_mb": max_upload_mb, "max_analysis_seconds": video_io.MAX_SECONDS},
        }

    @app.post("/api/jobs", status_code=202)
    async def create_job(file: UploadFile = File(...), deep: bool = Form(False)) -> dict[str, Any]:
        tmp, name, size = await receive(file)
        return jobs.submit(tmp, name, size, deep).model_dump(mode="json")

    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [j.model_dump(mode="json", exclude={"result"}) for j in jobs.active()]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job (it may have expired)")
        return job.model_dump(mode="json")

    @app.post("/api/analyze")
    async def analyze(file: UploadFile = File(...), deep: bool = Form(False)) -> dict[str, Any]:
        tmp, name, _ = await receive(file)
        try:
            report, _ = await run_in_threadpool(
                analyze_media, tmp, cases_dir, None, None, name, skip or None, deep)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        finally:
            tmp.unlink(missing_ok=True)
        return index.payload(report)

    @app.get("/api/cases")
    def list_cases(limit: int = 100, q: str = "") -> list[dict[str, Any]]:
        return index.list(limit=max(1, min(limit, 500)), query=q)

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> dict[str, Any]:
        items = index.case(case_id) if CASE_ID.match(case_id) else []
        if not items:
            raise HTTPException(404, "Unknown case")
        return {"case_id": case_id, "items": items}

    # The single-page app: built assets, with index.html for every other route.
    if (web_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (web_dist / path).resolve()
        if path and web_dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index_html = web_dist / "index.html"
        return FileResponse(index_html) if index_html.is_file() else HTMLResponse(NOT_BUILT)

    return app
