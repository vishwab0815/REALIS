import json
import os

import pytest

from realis.core.custody import CaseStore


@pytest.fixture
def evidence(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8 not really a jpeg, but bytes are bytes \xff\xd9")
    return p


def test_ingest_stores_read_only_copy_and_logs(tmp_path, evidence):
    store = CaseStore(tmp_path / "cases")
    rec = store.ingest(evidence)
    stored = store.case_dir(rec.case_id) / "evidence" / f"{rec.sha256}.jpg"
    assert stored.exists()
    assert not os.access(stored, os.W_OK)
    assert store.verify(rec)
    entries = store.log(rec.case_id).entries()
    assert [e["action"] for e in entries] == ["ingest", "verify_integrity"]
    assert store.log(rec.case_id).verify()[0]


def test_log_detects_edited_entry(tmp_path, evidence):
    store = CaseStore(tmp_path / "cases")
    rec = store.ingest(evidence)
    store.verify(rec)
    log = store.log(rec.case_id)
    lines = log.path.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["details"]["sha256"] = "f" * 64
    lines[0] = json.dumps(entry, sort_keys=True)
    log.path.write_text("\n".join(lines) + "\n")
    ok, msg = log.verify()
    assert not ok and "altered" in msg


def test_log_detects_deleted_entry(tmp_path, evidence):
    store = CaseStore(tmp_path / "cases")
    rec = store.ingest(evidence)
    store.verify(rec)
    store.verify(rec)
    log = store.log(rec.case_id)
    lines = log.path.read_text().splitlines()
    log.path.write_text("\n".join([lines[0], lines[2]]) + "\n")
    assert not log.verify()[0]
