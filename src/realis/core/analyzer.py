"""Analyzer plugin base class and registry.

Adding a detector means writing one subclass and decorating it with
@register; the pipeline, fusion and reports pick it up automatically.
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Status

_REGISTRY: dict[str, dict[str, type[Analyzer]]] = {}


class Analyzer(ABC):
    name: ClassVar[str]
    title: ClassVar[str] = ""
    modalities: ClassVar[tuple[str, ...]]
    version: ClassVar[str] = "0.1.0"
    # Relative influence on the fused verdict.
    weight: ClassVar[float] = 1.0
    evidence_kind: ClassVar[EvidenceKind] = EvidenceKind.MANIPULATION
    # Heavy analyzers only run in a deep scan.
    deep: ClassVar[bool] = False
    description: ClassVar[str] = ""

    def skip_reason(self, ctx: Any) -> str | None:
        """Return a reason string to skip this analyzer for the given input."""
        return None

    @abstractmethod
    def analyze(self, ctx: Any) -> AnalyzerResult: ...

    def _base(self, status: Status, **kwargs: Any) -> AnalyzerResult:
        # Analyzers whose findings can point either way may pass evidence_kind per result.
        kwargs.setdefault("evidence_kind", self.evidence_kind)
        return AnalyzerResult(
            analyzer=self.name, title=self.title or self.name, version=self.version,
            status=status, weight=self.weight, **kwargs,
        )

    def result(
        self,
        score: float | None = None,
        confidence: float = 0.0,
        findings: list[Finding] | None = None,
        **kwargs: Any,
    ) -> AnalyzerResult:
        return self._base(Status.OK, score=score, confidence=confidence,
                          findings=findings or [], **kwargs)

    def run(self, ctx: Any) -> AnalyzerResult:
        start = time.perf_counter()
        try:
            if reason := self.skip_reason(ctx):
                res = self._base(Status.SKIPPED, error=reason)
            else:
                res = self.analyze(ctx)
        except Exception as e:  # one broken analyzer must not sink the case
            res = self._base(Status.ERROR, error=f"{type(e).__name__}: {e}",
                             data={"traceback": traceback.format_exc()})
        res.elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return res


def register(cls: type[Analyzer]) -> type[Analyzer]:
    for modality in cls.modalities:
        _REGISTRY.setdefault(modality, {})[cls.name] = cls
    return cls


def analyzers_for(modality: str) -> dict[str, type[Analyzer]]:
    return dict(_REGISTRY.get(modality, {}))


def all_analyzer_names() -> set[str]:
    return {name for by_name in _REGISTRY.values() for name in by_name}
