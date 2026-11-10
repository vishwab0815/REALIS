"""JSON (machine) and HTML (human) case reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from realis.core.models import Report

_env = Environment(
    loader=PackageLoader("realis.report", "templates"),
    autoescape=select_autoescape(["html"]),
)

# Large raw blobs stay in the JSON report only.
_HTML_HIDDEN_KEYS = {"manifest_store", "exiftool", "quantization_tables", "traceback", "text_chunks"}


def _brief(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in _HTML_HIDDEN_KEYS and v not in (None, {}, [])}


def write_reports(report: Report, case_dir: Path, custody: list[dict[str, Any]]) -> dict[str, Path]:
    out_dir = case_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = report.evidence.sha256[:12]

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    html_path = out_dir / f"{stem}.html"
    html = _env.get_template("report.html.j2").render(
        r=report, custody=custody, brief=_brief, artifact_prefix="../",
    )
    html_path.write_text(html, encoding="utf-8")
    return {"json": json_path, "html": html_path}
