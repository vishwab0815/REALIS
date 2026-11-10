"""Signature matching over metadata text (word-boundary regexes -> display names)."""

from __future__ import annotations

import re


def match(table: dict[str, str], text: str) -> list[str]:
    return sorted({name for pattern, name in table.items() if re.search(pattern, text)})


def container_tags(probe: dict, streams: list[dict] | None = None) -> dict[str, str]:
    """Format tags and every stream's tags, lower-cased keys, prefixed by origin."""
    tags = {f"format.{k.lower()}": str(v) for k, v in probe.get("format", {}).get("tags", {}).items()}
    for i, stream in enumerate(streams if streams is not None else probe.get("streams", [])):
        kind = stream.get("codec_type", "stream")
        tags |= {f"{kind}{i}.{k.lower()}": str(v) for k, v in stream.get("tags", {}).items()}
    return tags
