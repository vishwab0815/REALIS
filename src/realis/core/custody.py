"""Chain of custody: immutable evidence storage and a tamper-evident log.

Every case lives in its own directory:

    <root>/<case_id>/
        evidence/<sha256><ext>   read-only working copy, never modified
        artifacts/<sha12>/       heatmaps and other derived outputs
        reports/<sha12>.json|html
        custody.jsonl            append-only, hash-chained action log
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import shutil
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from realis.core.models import EvidenceRecord

GENESIS_HASH = "0" * 64
_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_case_id() -> str:
    return f"CASE-{_now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


class CustodyLog:
    """Append-only JSONL log where each entry commits to the previous one.

    Editing, deleting or reordering any line breaks the chain, which
    verify() detects.
    """

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _digest(entry: dict[str, Any]) -> str:
        body = {k: v for k, v in entry.items() if k != "entry_hash"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def append(self, action: str, **details: Any) -> dict[str, Any]:
        entries = self.entries()
        prev = entries[-1]["entry_hash"] if entries else GENESIS_HASH
        entry = {
            "seq": len(entries),
            "timestamp": _now().isoformat(),
            "actor": getpass.getuser(),
            "action": action,
            "details": details,
            "prev_hash": prev,
        }
        entry["entry_hash"] = self._digest(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> tuple[bool, str]:
        prev = GENESIS_HASH
        try:
            entries = self.entries()
        except json.JSONDecodeError as e:
            return False, f"log is not valid JSONL: {e}"
        for i, entry in enumerate(entries):
            if entry.get("seq") != i:
                return False, f"entry {i}: sequence number mismatch"
            if entry.get("prev_hash") != prev:
                return False, f"entry {i}: chain broken (prev_hash mismatch)"
            if entry.get("entry_hash") != self._digest(entry):
                return False, f"entry {i}: content altered (entry_hash mismatch)"
            prev = entry["entry_hash"]
        return True, f"{len(entries)} entries, chain intact"


class CaseStore:
    def __init__(self, root: Path):
        self.root = root

    def case_dir(self, case_id: str) -> Path:
        return self.root / case_id

    def log(self, case_id: str) -> CustodyLog:
        return CustodyLog(self.case_dir(case_id) / "custody.jsonl")

    def ingest(
        self, src: Path, case_id: str | None = None, original_name: str | None = None
    ) -> EvidenceRecord:
        """Hash the source, store a read-only copy, and log the acquisition."""
        src = src.resolve()
        if not src.is_file():
            raise FileNotFoundError(src)
        case_id = case_id or new_case_id()
        evidence_dir = self.case_dir(case_id) / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        name = original_name or src.name
        digest = sha256_file(src)
        stored = evidence_dir / f"{digest}{Path(name).suffix.lower()}"
        if not stored.exists():
            shutil.copy2(src, stored)
            os.chmod(stored, stat.S_IREAD)
        if sha256_file(stored) != digest:
            raise RuntimeError(f"copy of {src} does not match source hash")

        record = EvidenceRecord(
            case_id=case_id,
            original_name=name,
            stored_path=str(stored),
            sha256=digest,
            size_bytes=stored.stat().st_size,
            ingested_at=_now(),
        )
        self.log(case_id).append(
            "ingest",
            source=str(src),
            original_name=name,
            stored_path=str(stored),
            sha256=digest,
            size_bytes=record.size_bytes,
        )
        return record

    def verify(self, record: EvidenceRecord) -> bool:
        actual = sha256_file(Path(record.stored_path))
        ok = actual == record.sha256
        self.log(record.case_id).append(
            "verify_integrity", sha256_expected=record.sha256, sha256_actual=actual, ok=ok
        )
        return ok
