import json

import pytest

from conftest import jpeg_bytes
from realis.core.fusion import fuse
from realis.core.models import AnalyzerResult, EvidenceKind, Status
from realis.ml import commfor
from realis.pipeline import analyze_media


def test_end_to_end_report(tmp_path, coffee):
    src = tmp_path / "upload-tmp.jpg"
    src.write_bytes(jpeg_bytes(coffee, 90))
    report, paths = analyze_media(src, tmp_path / "cases", original_name="suspect.jpg", exclude=["trufor"])

    assert report.integrity_verified and report.custody_log_valid
    assert report.evidence.original_name == "suspect.jpg"
    assert {r.analyzer for r in report.results} == {
        "metadata", "c2pa_provenance", "jpeg_structure", "ela", "noise_inconsistency", "copy_move",
        "ai_generated"}
    assert all(r.status == Status.OK or (r.analyzer == "ai_generated" and not commfor.available())
               for r in report.results), [(r.analyzer, r.error) for r in report.results if r.status != Status.OK]
    assert paths["json"].exists() and paths["html"].exists()
    assert json.loads(paths["json"].read_text())["evidence"]["sha256"] == report.evidence.sha256

    case_dir = tmp_path / "cases" / report.evidence.case_id
    for r in report.results:
        for rel in r.artifacts.values():
            assert (case_dir / rel).exists()
    actions = [json.loads(line)["action"] for line in (case_dir / "custody.jsonl").read_text().splitlines()]
    assert actions == ["ingest", "verify_integrity", "analysis_start", "verify_integrity", "report_written"]


def test_rejects_non_image(tmp_path):
    src = tmp_path / "notes.jpg"
    src.write_text("definitely not an image")
    with pytest.raises(ValueError, match="not a decodable image"):
        analyze_media(src, tmp_path / "cases", exclude=["trufor"])


def test_unknown_analyzer(tmp_path, coffee):
    src = tmp_path / "a.jpg"
    src.write_bytes(jpeg_bytes(coffee, 90))
    with pytest.raises(ValueError, match="unknown analyzers"):
        analyze_media(src, tmp_path / "cases", only=["nope"])
    with pytest.raises(ValueError, match="unknown analyzers"):
        analyze_media(src, tmp_path / "cases", exclude=["nope"])


def _result(name, score, conf, kind=EvidenceKind.MANIPULATION):
    return AnalyzerResult(analyzer=name, version="t", status=Status.OK, score=score,
                          confidence=conf, evidence_kind=kind)


def test_fusion_labels_ai_generation():
    v = fuse([_result("ai_generated", 0.99, 0.55, EvidenceKind.SYNTHESIS), _result("copy_move", 0.4, 0.25)])
    assert v.category == "synthesis" and "AI generation" in v.label


def test_fusion_single_detector_is_never_strong():
    # One ML detector (with known false positives) can only raise "Indications".
    v = fuse([_result("synthetic_voice", 0.999, 0.45, EvidenceKind.SYNTHESIS)])
    assert v.ai_generation_probability >= 0.8
    assert v.label == "Indications of AI generation"
    assert any("independent corroboration" in line for line in v.rationale)
    v = fuse([_result("synthetic_voice", 0.999, 0.45, EvidenceKind.SYNTHESIS),
              _result("audio_metadata", 0.9, 0.5, EvidenceKind.SYNTHESIS)])
    assert v.label == "Strong indications of AI generation"


def test_fusion_labels_manipulation():
    v = fuse([_result("copy_move", 0.88, 0.6), _result("ai_generated", 0.01, 0.25, EvidenceKind.SYNTHESIS),
              _result("trufor", 0.95, 0.55)])
    assert v.category == "manipulation" and "manipulation" in v.label


def test_fusion_clean():
    v = fuse([_result("ai_generated", 0.01, 0.25, EvidenceKind.SYNTHESIS), _result("copy_move", 0.4, 0.25)])
    assert v.category == "none" and v.label.startswith("No significant evidence")
    assert v.ai_generation_probability < 0.3


def test_fusion_weak_suspicion_is_inconclusive():
    v = fuse([_result("trufor", 0.65, 0.55), _result("ai_generated", 0.01, 0.25, EvidenceKind.SYNTHESIS)])
    assert v.label == "Inconclusive"


def test_fusion_recompression_alone_is_not_suspicious():
    v = fuse([_result("jpeg_structure", 0.62, 0.5, EvidenceKind.PROCESSING), _result("copy_move", 0.4, 0.25)])
    assert v.label.startswith("No significant evidence")


def test_fusion_not_ai_does_not_cancel_a_clone():
    # Regression: a confident "not AI-generated" used to drag a detected clone down to "Inconclusive".
    v = fuse([_result("copy_move", 0.88, 0.6), _result("jpeg_structure", 0.62, 0.5, EvidenceKind.PROCESSING),
              _result("ai_generated", 0.0, 0.25, EvidenceKind.SYNTHESIS)])
    assert v.category == "manipulation" and v.editing_probability > 0.8
    assert v.ai_generation_probability < 0.3
