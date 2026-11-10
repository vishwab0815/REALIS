"""Case history: summaries and URLs for reports already written to the case store."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from realis.core.models import Report


def urls(report: Report, cases_dir: Path) -> dict[str, Any]:
    """Public URLs (under /cases) for a report, its evidence copy and its figures."""
    case = report.evidence.case_id
    stem = report.evidence.sha256[:12]
    base = f"/cases/{case}"

    def under(path: str) -> str:
        return f"{base}/{path}"

    evidence = Path(report.evidence.stored_path)
    try:
        evidence_url = "/cases/" + evidence.resolve().relative_to(cases_dir.resolve()).as_posix()
    except ValueError:  # evidence stored elsewhere: not served
        evidence_url = None
    return {
        "html": under(f"reports/{stem}.html"),
        "json": under(f"reports/{stem}.json"),
        "evidence": evidence_url,
        "overview": {label: under(p) for label, p in report.overview.items()},
        "artifacts": {r.analyzer: {label: under(p) for label, p in r.artifacts.items()} for r in report.results},
    }


def _thumbnail(report: Report, payload: dict[str, Any]) -> str | None:
    if report.modality == "image":
        return payload["evidence"]
    for r in report.results:
        frames = r.data.get("frames") if r.data else None
        if frames:
            return f"/cases/{report.evidence.case_id}/{frames[len(frames) // 2]['path']}"
    return next(iter(payload["overview"].values()), None)


class CaseIndex:
    """Summaries of every report under the case root, cached by file modification time."""

    def __init__(self, cases_dir: Path):
        self.cases_dir = cases_dir
        self._cache: dict[Path, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def load(self, json_path: Path) -> Report:
        return Report.model_validate_json(json_path.read_text(encoding="utf-8"))

    def payload(self, report: Report) -> dict[str, Any]:
        return {"report": json.loads(report.model_dump_json()), "urls": urls(report, self.cases_dir)}

    def _summary(self, path: Path) -> dict[str, Any] | None:
        mtime = path.stat().st_mtime
        with self._lock:
            hit = self._cache.get(path)
            if hit and hit[0] == mtime:
                return hit[1]
        try:
            report = self.load(path)
        except (OSError, ValueError):
            return None  # half-written or foreign file
        v = report.verdict
        links = urls(report, self.cases_dir)
        summary = {
            "case_id": report.evidence.case_id, "sha256": report.evidence.sha256,
            "name": report.evidence.original_name, "modality": report.modality,
            "size_bytes": report.evidence.size_bytes, "generated_at": report.generated_at.isoformat(),
            "label": v.label, "category": v.category, "decisive": v.decisive,
            "ai_generation_probability": v.ai_generation_probability,
            "editing_probability": v.editing_probability,
            "thumbnail": _thumbnail(report, links),
        }
        with self._lock:
            self._cache[path] = (mtime, summary)
        return summary

    def list(self, limit: int = 100, query: str = "") -> list[dict[str, Any]]:
        paths = sorted(self.cases_dir.glob("*/reports/*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        out = []
        q = query.lower().strip()
        for path in paths:
            summary = self._summary(path)
            if summary and (not q or q in summary["name"].lower() or q in summary["case_id"].lower()):
                out.append(summary)
                if len(out) >= limit:
                    break
        return out

    def case(self, case_id: str) -> list[dict[str, Any]]:
        folder = (self.cases_dir / case_id / "reports").resolve()
        if self.cases_dir.resolve() not in folder.parents or not folder.is_dir():
            return []
        reports = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [self.payload(self.load(p)) for p in reports]
