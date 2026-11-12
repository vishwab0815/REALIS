import subprocess
import sys

import numpy as np
import pytest
from audio_fixtures import SR, recording, write_wav
from conftest import C2PA_AVAILABLE
from scipy.signal import resample_poly

from realis.audio import io, signal
from realis.audio.analyzers.bandwidth import BandwidthAnalyzer
from realis.audio.analyzers.edits import EditDiscontinuityAnalyzer
from realis.audio.analyzers.enf import EnfAnalyzer
from realis.audio.analyzers.metadata import AudioMetadataAnalyzer
from realis.audio.context import AudioContext
from realis.core.models import Severity, Status
from realis.ml import antideepfake
from realis.pipeline import analyze_media

needs_ffmpeg = pytest.mark.skipif(not io.available(), reason="FFmpeg not installed")


@pytest.fixture
def make_audio_ctx(tmp_path):
    def _make(x: np.ndarray, name: str = "a.wav", sr: int = SR) -> AudioContext:
        path = tmp_path / name
        write_wav(path, x, sr)
        return AudioContext(path, "0" * 64, tmp_path)
    return _make


def _titles(res):
    return [f.title for f in res.findings]


# --- ENF ---------------------------------------------------------------------

def test_enf_clean_recording_is_continuous():
    r = signal.enf_analysis(recording(), SR)
    assert r.present and r.continuity_checked and r.grid_hz == 50
    assert r.discontinuities == []


@pytest.mark.parametrize("cut_at, cut_len", [(18.0, 0.37), (25.0, 0.25)])
def test_enf_finds_deleted_segment(cut_at, cut_len):
    x = recording()
    cut = np.concatenate([x[: int(cut_at * SR)], x[int((cut_at + cut_len) * SR):]])
    events = signal.enf_analysis(cut, SR).discontinuities
    assert any(abs(e["time"] - cut_at) < 0.5 for e in events), events


def test_enf_finds_both_edges_of_insert():
    x, other = recording(), recording(seed=2, f0=50.06)
    pasted = np.concatenate([x[: 15 * SR], other[15 * SR: 22 * SR], x[15 * SR:]])
    times = [e["time"] for e in signal.enf_analysis(pasted, SR).discontinuities]
    assert any(abs(t - 15) < 0.5 for t in times) and any(abs(t - 22) < 0.5 for t in times), times


def test_enf_absent_without_hum():
    assert not signal.enf_analysis(recording(with_hum=False), SR).present


def test_enf_short_clip_is_not_judged(make_audio_ctx):
    r = signal.enf_analysis(recording(seconds=12), SR)
    assert r.present and not r.continuity_checked and r.discontinuities == []
    res = EnfAnalyzer().run(make_audio_ctx(recording(seconds=12)))
    assert "Mains hum present, not judged" in _titles(res) and res.confidence == 0
    assert "ENF track" in res.artifacts


# --- edits -------------------------------------------------------------------

def test_digital_silence_found_inside_only():
    x = recording(seconds=20)
    x[12 * SR: int(12.05 * SR)] = 0
    x[:800] = 0  # leading digital silence is normal padding
    assert signal.digital_silence_runs(x, SR) == [(12.0, 12.05)]


def test_background_jump_found_at_splice():
    # No hum here: the hum would set the pause level and mask the background change.
    quiet = recording(noise=0.0005, with_hum=False)
    noisy = recording(noise=0.004, seed=3, with_hum=False)
    joined = np.concatenate([quiet[: 20 * SR], noisy[20 * SR:]])
    steps = signal.noise_floor_steps(joined, SR)[0]
    assert len(steps) == 1 and abs(steps[0]["time"] - 20) < 1.5 and steps[0]["step_db"] > 10
    assert signal.noise_floor_steps(recording(), SR)[0] == []


def test_edit_analyzer_reports_silence(make_audio_ctx):
    x = recording(seconds=20)
    x[10 * SR: int(10.1 * SR)] = 0
    res = EditDiscontinuityAnalyzer().run(make_audio_ctx(x))
    assert res.status == Status.OK and "Digital silence inside the recording" in _titles(res)
    assert res.data["events"] and res.score > 0.5


# --- bandwidth ---------------------------------------------------------------

def test_bandwidth_detects_upsampling():
    rng = np.random.default_rng(0)
    native = rng.normal(0, 0.05, 48_000 * 5).astype(np.float32)
    up = resample_poly(rng.normal(0, 0.05, SR * 5), 3, 1).astype(np.float32)
    assert signal.effective_bandwidth(native, 48_000)["cutoff_hz"] is None
    assert 7_500 < signal.effective_bandwidth(up, 48_000)["cutoff_hz"] < 9_500


@needs_ffmpeg
def test_bandwidth_analyzer_lossless_vs_lossy(tmp_path, make_audio_ctx):
    up = resample_poly(recording(seconds=10, with_hum=False), 3, 1).astype(np.float32)
    ctx = make_audio_ctx(up, "up.wav", 48_000)
    res = BandwidthAnalyzer().run(ctx)
    assert "Upsampled from a lower-rate source" in _titles(res) and res.score > 0.5

    mp3 = tmp_path / "up.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ctx.path), "-b:a", "64k", str(mp3)], check=True)
    res = BandwidthAnalyzer().run(AudioContext(mp3, "1" * 64, tmp_path))
    assert res.confidence == 0  # a codec low-pass is normal, not evidence


# --- metadata ----------------------------------------------------------------

@needs_ffmpeg
@pytest.mark.parametrize("tag, expected", [
    ("comment=Generated with ElevenLabs", Severity.CRITICAL),
    ("comment=Cleaned up in Audacity", Severity.MEDIUM),
])
def test_metadata_signatures(tmp_path, make_audio_ctx, tag, expected):
    src = make_audio_ctx(recording(seconds=3, with_hum=False)).path
    tagged = tmp_path / "tagged.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-metadata", tag, str(tagged)], check=True)
    res = AudioMetadataAnalyzer().run(AudioContext(tagged, "2" * 64, tmp_path))
    assert any(f.severity == expected for f in res.findings), res.findings
    assert (res.decisive_label is not None) == (expected == Severity.CRITICAL)


def test_metadata_word_boundaries(make_audio_ctx):
    # "https" contains "tts"; it must not be read as a text-to-speech signature.
    res = AudioMetadataAnalyzer().run(make_audio_ctx(recording(seconds=2, with_hum=False)))
    assert res.decisive_label is None


# --- pipeline ----------------------------------------------------------------

@needs_ffmpeg
def test_audio_pipeline_end_to_end(tmp_path):
    x = recording()
    cut = np.concatenate([x[: 18 * SR], x[int(18.37 * SR):]])
    src = tmp_path / "upload.wav"
    write_wav(src, cut)
    report, paths = analyze_media(src, tmp_path / "cases", original_name="call.wav", exclude=["synthetic_voice"])

    assert report.modality == "audio" and report.integrity_verified and report.custody_log_valid
    assert {r.analyzer for r in report.results} == {
        "c2pa_provenance", "audio_metadata", "enf", "edit_discontinuity", "bandwidth"}
    assert all(r.status == Status.OK or (r.analyzer == "c2pa_provenance" and not C2PA_AVAILABLE)
               for r in report.results), [(r.analyzer, r.error) for r in report.results]
    enf = next(r for r in report.results if r.analyzer == "enf")
    assert "Mains-hum discontinuity: possible cut or insert" in _titles(enf)
    assert report.verdict.category == "manipulation"
    case_dir = tmp_path / "cases" / report.evidence.case_id
    assert (case_dir / report.overview["Evidence timeline"]).exists()
    assert paths["html"].exists() and "Audio forensic report" in paths["html"].read_text(encoding="utf-8")


def test_unsupported_and_undecodable(tmp_path):
    with pytest.raises(ValueError, match="unsupported file type"):
        analyze_media(tmp_path / "notes.txt", tmp_path / "cases")
    bad = tmp_path / "broken.wav"
    bad.write_bytes(b"RIFF....not audio")
    with pytest.raises(ValueError, match="not a decodable audio file"):
        analyze_media(bad, tmp_path / "cases")


# --- AI voice model ----------------------------------------------------------

needs_antideepfake = pytest.mark.skipif(not antideepfake.available(), reason="run `realis setup-models`")


def _real_speech():
    try:
        from huggingface_hub import hf_hub_download
        return hf_hub_download("Narsil/asr_dummy", "1.flac", repo_type="dataset")
    except Exception as e:  # offline
        pytest.skip(f"real speech sample unavailable: {e}")


@needs_antideepfake
@needs_ffmpeg
def test_antideepfake_passes_real_speech():
    wav = io.decode(_real_speech(), 16_000)
    assert antideepfake.predict(wav)["fake_probability"] < 0.2


@needs_antideepfake
@needs_ffmpeg
@pytest.mark.skipif(sys.platform != "win32", reason="uses the Windows speech synthesizer")
def test_antideepfake_flags_synthetic_speech(tmp_path):
    out = tmp_path / "sapi.wav"
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{out}'); $s.Speak('Please transfer the payment before five today.'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=60)
    assert antideepfake.predict(io.decode(out, 16_000))["fake_probability"] > 0.8


@needs_antideepfake
def test_antideepfake_timeline_windows():
    out = antideepfake.predict(recording(seconds=20, with_hum=False))
    tl = out["timeline"]
    assert tl and tl[0]["start"] == 0 and all(0 <= w["fake_probability"] <= 1 for w in tl)
    assert tl[1]["start"] - tl[0]["start"] == pytest.approx(antideepfake.HOP_SECONDS)
