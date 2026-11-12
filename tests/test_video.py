import pytest
import video_fixtures as vf
from conftest import C2PA_AVAILABLE

from realis.audio import io as audio_io
from realis.core.models import Severity, Status
from realis.ml import commfor
from realis.pipeline import analyze_media
from realis.video import io, temporal
from realis.video.analyzers.frames import FrameAiAnalyzer
from realis.video.analyzers.metadata import VideoMetadataAnalyzer
from realis.video.analyzers.temporal_edits import TemporalEditsAnalyzer
from realis.video.context import VideoContext

pytestmark = pytest.mark.skipif(not audio_io.available(), reason="FFmpeg not installed")


def ctx_for(path, tmp_path):
    return VideoContext(path, "0" * 64, tmp_path)


def _titles(res):
    return [f.title for f in res.findings]


# --- temporal scan -----------------------------------------------------------

def test_scan_finds_cut(tmp_path):
    s = temporal.scan(io.scan_frames(vf.with_cut(tmp_path / "cut.mp4", at=3)))
    assert [round(i / 30, 1) for i in s.cuts] == [3.0]
    assert s.duplicates == []


def test_scan_finds_frozen_frames(tmp_path):
    s = temporal.scan(io.scan_frames(vf.frozen(tmp_path / "frozen.mp4", at_frame=90, extra=3)))
    assert s.cuts == []
    assert len(s.duplicates) == 3 and all(88 <= i <= 95 for i in s.duplicates)


@pytest.mark.parametrize("make", [vf.continuous, vf.static])
def test_scan_clean_footage(tmp_path, make):
    s = temporal.scan(io.scan_frames(make(tmp_path / "clean.mp4")))
    assert s.cuts == [] and s.duplicates == []


def test_temporal_analyzer_distinguishes_rate_conversion(tmp_path):
    res = TemporalEditsAnalyzer().run(ctx_for(vf.rate_converted(tmp_path / "conv.mp4"), tmp_path))
    assert "Regular duplicated frames" in _titles(res)
    res = TemporalEditsAnalyzer().run(ctx_for(vf.frozen(tmp_path / "frozen.mp4"), tmp_path))
    assert "Frozen or inserted frames" in _titles(res) and res.data["events"]


# --- context -----------------------------------------------------------------

def test_context_samples_frames_and_thumbnails(tmp_path):
    ctx = ctx_for(vf.continuous(tmp_path / "c.mp4", seconds=6, size="640x360"), tmp_path)
    assert ctx.size == (640, 360) and ctx.fps == pytest.approx(30)
    assert len(ctx.sample_times) == 8 and ctx.sample_times == sorted(ctx.sample_times)
    t, rgb = ctx.frames[0]
    assert rgb.shape == (360, 640, 3) and 0 < t < 1
    assert all((tmp_path / th["path"]).exists() for th in ctx.thumbnails)
    assert not ctx.has_audio


# --- metadata ----------------------------------------------------------------

@pytest.mark.parametrize("comment, severity, decisive", [
    ("Made with Runway Gen-3", Severity.CRITICAL, True),
    ("Edited in CapCut", Severity.MEDIUM, False),
])
def test_metadata_signatures(tmp_path, comment, severity, decisive):
    path = vf.talking(tmp_path / "t.mp4", tmp_path, seconds=4, metadata={"comment": comment})
    res = VideoMetadataAnalyzer().run(ctx_for(path, tmp_path))
    assert any(f.severity == severity for f in res.findings), res.findings
    assert (res.decisive_label is not None) is decisive


def test_metadata_flags_shorter_audio_track(tmp_path):
    path = vf.talking(tmp_path / "dub.mp4", tmp_path, seconds=8, audio_seconds=4)
    res = VideoMetadataAnalyzer().run(ctx_for(path, tmp_path))
    assert "Audio and video tracks differ in length" in _titles(res)


# --- frames ------------------------------------------------------------------

@pytest.mark.skipif(not commfor.available(), reason="run `realis setup-models`")
def test_frame_ai_timeline(tmp_path):
    res = FrameAiAnalyzer().run(ctx_for(vf.continuous(tmp_path / "c.mp4"), tmp_path))
    assert res.status == Status.OK
    pts = res.data["series"][0]["points"]
    assert len(pts) == len(res.data["frames"]) == 8
    assert all(0 <= p <= 1 for _, p in pts)


# --- pipeline ----------------------------------------------------------------

def test_video_pipeline_with_cut_audio(tmp_path):
    path = vf.talking(tmp_path / "talk.mp4", tmp_path, seconds=30, cut_at=18)
    stages = []
    report, paths = analyze_media(path, tmp_path / "cases", exclude=["synthetic_voice", "frame_ai"], deep=False,
                                  progress=lambda s, f: stages.append(f))
    assert report.modality == "video" and report.integrity_verified and report.custody_log_valid
    names = {r.analyzer for r in report.results}
    assert {"video_metadata", "temporal_edits", "enf", "edit_discontinuity", "c2pa_provenance"} <= names
    assert "frame_trufor" not in names  # quick scan
    enf = next(r for r in report.results if r.analyzer == "enf")
    assert any(abs(e["time"] - 18) < 0.6 for e in enf.data["events"]), enf.data
    assert any("Quick scan" in n for n in report.notes)
    assert stages[0] == 0 and stages[-1] == 1 and stages == sorted(stages)
    case_dir = tmp_path / "cases" / report.evidence.case_id
    assert (case_dir / report.overview["Evidence timeline"]).exists()
    assert "Video forensic report" in paths["html"].read_text(encoding="utf-8")


def test_silent_video_skips_audio_checks(tmp_path):
    report, _ = analyze_media(vf.continuous(tmp_path / "silent.mp4"), tmp_path / "cases",
                              exclude=["frame_ai"], deep=False)
    skipped = {r.analyzer: r.error for r in report.results if r.status == Status.SKIPPED}
    if not C2PA_AVAILABLE:
        skipped.pop("c2pa_provenance")
    assert skipped == {"synthetic_voice": "no audio track", "enf": "no audio track",
                       "edit_discontinuity": "no audio track", "bandwidth": "no audio track"}
    assert any("no audio track" in n for n in report.notes)


def test_undecodable_video(tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"\x00\x00\x00\x18ftypmp42 not a real video")
    with pytest.raises(ValueError, match="not a decodable video file"):
        analyze_media(bad, tmp_path / "cases")
