"""Case pipeline: ingest -> verify -> analyze -> fuse -> report -> log."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from realis import TOOL_NAME, __version__
from realis.audio import analyzers as _register_audio_analyzers  # noqa: F401
from realis.audio import visual as audio_visual
from realis.audio.context import AudioContext
from realis.core.analyzer import all_analyzer_names, analyzers_for
from realis.core.context import ImageContext, MediaContext
from realis.core.custody import CaseStore, sha256_file
from realis.core.fusion import fuse
from realis.core.models import AnalyzerResult, Report
from realis.image import analyzers as _register_image_analyzers  # noqa: F401
from realis.report.render import write_reports
from realis.video import analyzers as _register_video_analyzers  # noqa: F401
from realis.video import visual as video_visual
from realis.video.context import VideoContext

log = logging.getLogger("realis.pipeline")

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".amr",
                  ".aif", ".aiff", ".weba"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".mts", ".m2ts", ".ts", ".wmv",
                  ".flv"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | AUDIO_SUFFIXES | VIDEO_SUFFIXES

# progress(stage, fraction 0-1)
Progress = Callable[[str, float], None]


class IntegrityError(RuntimeError):
    pass


def modality_of(name: str) -> str:
    suffix = Path(name).suffix.lower()
    for modality, suffixes in (("image", IMAGE_SUFFIXES), ("audio", AUDIO_SUFFIXES), ("video", VIDEO_SUFFIXES)):
        if suffix in suffixes:
            return modality
    raise ValueError(f"unsupported file type '{suffix or 'none'}'")


def _open(modality: str, path: Path, sha256: str, case_dir: Path) -> MediaContext:
    """Build the context and force a decode, so unreadable files fail up front."""
    if modality == "image":
        ctx = ImageContext(path, sha256, case_dir)
        _ = ctx.image
    elif modality == "audio":
        ctx = AudioContext(path, sha256, case_dir)
        _ = ctx.samples
    else:
        ctx = VideoContext(path, sha256, case_dir)
        _ = ctx.video
        if ctx.duration <= 0:
            raise ValueError("video has no duration")
    return ctx


def _extras(ctx: MediaContext, results: list[AnalyzerResult]) -> tuple[dict[str, str], list[str]]:
    """Case-level timeline figure and notes for time-based media."""
    if not isinstance(ctx, AudioContext):
        return {}, []
    notes = []
    if ctx.truncated:
        notes.append(f"Only the first {ctx.analysed_seconds:.0f} s of {ctx.duration:.0f} s were analysed.")
    if isinstance(ctx, VideoContext) and not ctx.has_audio:
        notes.append("The video has no audio track: voice and ENF checks did not run.")
    try:
        fig = (video_visual.overview(ctx, results) if isinstance(ctx, VideoContext)
               else audio_visual.overview(ctx.samples, ctx.rate, results))
        overview = {"Evidence timeline": ctx.save_figure("overview", fig)}
    except Exception:  # a missing figure must not lose the case
        log.exception("could not render evidence timeline")
        overview = {}
    return overview, notes


def analyze_media(
    src: Path,
    cases_root: Path,
    case_id: str | None = None,
    only: list[str] | None = None,
    original_name: str | None = None,
    exclude: list[str] | None = None,
    deep: bool = True,
    progress: Progress | None = None,
) -> tuple[Report, dict[str, Path]]:
    """Analyse one file as a sealed case. deep=False skips heavy analyzers (TruFor)."""
    step = progress or (lambda stage, fraction: None)
    name = original_name or src.name
    modality = modality_of(name)
    unknown = (set(only or []) | set(exclude or [])) - all_analyzer_names()
    if unknown:
        raise ValueError(f"unknown analyzers: {', '.join(sorted(unknown))}")
    available = analyzers_for(modality)
    if only:
        available = {k: v for k, v in available.items() if k in only}
    if exclude:
        available = {k: v for k, v in available.items() if k not in exclude}
    if not deep:
        available = {k: v for k, v in available.items() if not v.deep}

    step("Sealing evidence", 0.0)
    store = CaseStore(cases_root)
    record = store.ingest(src, case_id, original_name)
    custody = store.log(record.case_id)
    if not store.verify(record):
        raise IntegrityError(f"stored evidence hash mismatch for {record.stored_path}")

    case_dir = store.case_dir(record.case_id)
    step(f"Decoding {modality}", 0.04)
    try:
        ctx = _open(modality, Path(record.stored_path), record.sha256, case_dir)
    except Exception as e:
        custody.append("analysis_aborted", sha256=record.sha256, reason=f"{type(e).__name__}: {e}")
        raise ValueError(f"{name} is not a decodable {modality} file: {e}") from e

    custody.append("analysis_start", sha256=record.sha256, modality=modality, deep=deep,
                   analyzers={n: cls.version for n, cls in available.items()})
    results = []
    for i, cls in enumerate(available.values()):
        title = cls.title or cls.name
        lo, span = 0.05 + 0.85 * i / len(available), 0.85 / len(available)
        ctx.on_progress = lambda f, note, lo=lo, span=span, title=title: step(
            f"{title} · {note}" if note else title, lo + span * f)
        step(title, lo)
        results.append(cls().run(ctx))
    ctx.on_progress = None

    step("Fusing evidence and writing the report", 0.9)
    verdict = fuse(results)
    overview, notes = _extras(ctx, results)
    if not deep:
        notes.append("Quick scan: deep-scan analyzers (TruFor) were skipped.")

    # Re-hash after analysis: proves no analyzer altered the evidence.
    integrity = store.verify(record)
    log_ok, _ = custody.verify()
    report = Report(
        tool=TOOL_NAME,
        tool_version=__version__,
        generated_at=datetime.now(timezone.utc),
        modality=modality,
        evidence=record,
        integrity_verified=integrity,
        results=results,
        verdict=verdict,
        custody_log_valid=log_ok,
        overview=overview,
        notes=notes,
    )
    paths = write_reports(report, case_dir, custody.entries())
    custody.append("report_written", sha256=record.sha256,
                   json_report=paths["json"].name, json_report_sha256=sha256_file(paths["json"]),
                   verdict=verdict.label, manipulation_probability=verdict.manipulation_probability)
    step("Done", 1.0)
    return report, paths
