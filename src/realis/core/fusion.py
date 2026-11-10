"""Evidence fusion: combine analyzer outputs into one explainable verdict.

Two questions are answered separately, because evidence for one says nothing
about the other ("not AI-generated" must not cancel out a detected clone):

  * AI generation: was the whole image synthesised?
  * Editing:       was a real image locally manipulated or re-processed?

Each analyzer's score is converted to log-odds and scaled by
confidence x weight, so a score of 0.5 (no information) contributes nothing
and every term can be shown to the investigator. Provenance evidence feeds
both questions. The scores are heuristic, not calibrated probabilities;
calibration against a labelled dataset is a later step.
"""

from __future__ import annotations

import math

from realis.core.models import (
    AnalyzerResult,
    Contribution,
    EvidenceKind,
    Finding,
    Severity,
    Status,
    Verdict,
)

_SEVERITY_RANK = {s: i for i, s in enumerate(Severity)}

CLEAR, UNSURE, STRONG = 0.45, 0.60, 0.80
# "Inconclusive" needs at least one contribution this suspicious; without one,
# the absence of findings is reported as such rather than as a coin flip.
MIN_SUSPICION = 0.25
LABELS = {
    "synthesis": ("Indications of AI generation", "Strong indications of AI generation"),
    "manipulation": ("Indications of manipulation", "Strong indications of manipulation"),
}
QUESTION_KINDS = {
    "synthesis": {EvidenceKind.SYNTHESIS, EvidenceKind.PROVENANCE},
    "manipulation": {EvidenceKind.MANIPULATION, EvidenceKind.PROCESSING, EvidenceKind.PROVENANCE},
}


def _logit(p: float) -> float:
    p = min(max(p, 0.02), 0.98)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def top_finding(r: AnalyzerResult) -> Finding | None:
    """Most severe finding; among equals the last, which analyzers use for the conclusion."""
    return max(reversed(r.findings), key=lambda f: _SEVERITY_RANK[f.severity], default=None)


def _headline(r: AnalyzerResult) -> str:
    top = top_finding(r)
    return top.title if top else "no notable findings"


def fuse(results: list[AnalyzerResult]) -> Verdict:
    by_name = {r.analyzer: r for r in results}
    contributions: list[Contribution] = []
    for r in results:
        if r.status != Status.OK or r.score is None or r.confidence <= 0:
            continue
        contributions.append(Contribution(
            analyzer=r.analyzer, score=round(r.score, 3), confidence=round(r.confidence, 3),
            weight=r.weight, log_odds=round(r.weight * r.confidence * _logit(r.score), 3),
        ))

    probs = {
        question: _sigmoid(sum(c.log_odds for c in contributions
                               if by_name[c.analyzer].evidence_kind in kinds))
        for question, kinds in QUESTION_KINDS.items()
    }
    leading = max(probs, key=probs.get)
    prob = probs[leading]
    supporters = [c for c in contributions if c.log_odds >= MIN_SUSPICION
                  and by_name[c.analyzer].evidence_kind in QUESTION_KINDS[leading]]
    decisive = [r for r in results if r.status == Status.OK and r.decisive_label]

    rationale: list[str] = []
    category = "none"
    if decisive:
        # Every decisive signal so far is a declaration of AI generation.
        label = "; ".join(r.decisive_label for r in decisive)  # type: ignore[misc]
        probs["synthesis"] = max(probs["synthesis"], *(r.score or 0 for r in decisive))
        prob = max(prob, probs["synthesis"])
        category = "synthesis"
        rationale += [f"[{r.analyzer}] {r.decisive_label}" for r in decisive]
    elif prob < CLEAR or (prob < UNSURE and not supporters):
        label = "No significant evidence of manipulation or AI generation found"
    elif prob < UNSURE:
        label = "Inconclusive"
    else:
        category = leading
        # Every detector has known false positives: "strong" needs two independent supporters.
        strong = prob >= STRONG and len(supporters) >= 2
        label = LABELS[category][strong]
        if prob >= STRONG and not strong:
            rationale.append(f"Only one analyzer ({supporters[0].analyzer}) supports this; a strong "
                             "finding needs independent corroboration.")

    for c in sorted(contributions, key=lambda c: abs(c.log_odds), reverse=True)[:4]:
        direction = "raises suspicion" if c.log_odds > 0 else "supports authenticity"
        rationale.append(f"[{c.analyzer}] {_headline(by_name[c.analyzer])} ({direction}, {c.log_odds:+.2f})")

    return Verdict(
        label=label,
        manipulation_probability=round(prob, 3),
        ai_generation_probability=round(probs["synthesis"], 3),
        editing_probability=round(probs["manipulation"], 3),
        category=category,
        decisive=bool(decisive),
        rationale=rationale,
        contributions=contributions,
    )
