"""C2PA Content Credentials: cryptographically signed provenance."""

from __future__ import annotations

import json
from typing import Any

import c2pa

from realis.core.analyzer import Analyzer, register
from realis.core.context import MediaContext
from realis.core.models import AnalyzerResult, EvidenceKind, Finding, Severity

AI_SOURCE_TYPES = ("trainedalgorithmicmedia", "algorithmicmedia")
CAPTURE_SOURCE_TYPES = ("digitalcapture",)
TAMPER_CODES = ("hash.mismatch", "datahash.mismatch", "bmffhash.mismatch", "boxhash.mismatch",
                "signature.mismatch", "claimsignature.mismatch")
EDIT_ACTIONS = {
    "c2pa.edited", "c2pa.cropped", "c2pa.filtered", "c2pa.color_adjustments", "c2pa.drawing",
    "c2pa.placed", "c2pa.removed", "c2pa.resized", "c2pa.orientation", "c2pa.transcoded",
}


def _actions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for a in manifest.get("assertions", []):
        if str(a.get("label", "")).startswith("c2pa.actions"):
            out += a.get("data", {}).get("actions", [])
    return out


def _failure_codes(store: dict[str, Any]) -> list[str]:
    codes = [s.get("code", "") for s in store.get("validation_status", []) or []]
    results = store.get("validation_results") or {}
    active = results.get("activeManifest") or {}
    codes += [f.get("code", "") for f in active.get("failure", []) or []]
    return [c for c in codes if c]


@register
class ProvenanceAnalyzer(Analyzer):
    name = "c2pa_provenance"
    title = "Content Credentials (C2PA)"
    evidence_kind = EvidenceKind.PROVENANCE
    modalities = ("image", "audio", "video")
    weight = 1.5
    description = "C2PA Content Credentials: signer, actions, AI declarations, tamper checks"

    def analyze(self, ctx: MediaContext) -> AnalyzerResult:
        raw = ctx.raw_bytes
        has_markers = b"jumb" in raw and b"c2pa" in raw
        try:
            reader = c2pa.Reader.try_create(str(ctx.path))
        except c2pa.C2paError as e:
            if not has_markers:
                return self.result(score=0.5, confidence=0.0, findings=[Finding(
                    severity=Severity.INFO, title="No C2PA manifest",
                    detail=f"Format not supported by the C2PA reader ({e}).")])
            return self.result(score=0.7, confidence=0.4, findings=[Finding(
                severity=Severity.MEDIUM, title="C2PA data present but unreadable",
                detail=f"Manifest is corrupt or was damaged by later edits: {e}",
            )])

        if reader is None:
            return self.result(
                score=0.5, confidence=0.0,
                findings=[Finding(
                    severity=Severity.INFO, title="No C2PA manifest",
                    detail="Neutral: most media files carry no Content Credentials, and platforms often strip them.",
                )],
                limitations=["Absence of C2PA says nothing about authenticity."],
            )

        with reader:
            store = json.loads(reader.json())
        active_label = store.get("active_manifest")
        manifests = store.get("manifests", {})
        active = manifests.get(active_label, {})
        state = store.get("validation_state")
        failures = _failure_codes(store)
        sig = active.get("signature_info", {}) or {}
        generator = active.get("claim_generator") or ", ".join(
            g.get("name", "") for g in active.get("claim_generator_info", []) or [])

        all_actions = [a for m in manifests.values() for a in _actions(m)]
        source_types = [str(a.get("digitalSourceType", "")).lower() for a in all_actions]
        action_names = sorted({str(a.get("action", "")) for a in all_actions})

        findings = [Finding(
            severity=Severity.INFO, title="C2PA manifest found",
            detail=f"Generator: {generator or 'n/a'}; signer: {sig.get('issuer') or sig.get('common_name') or 'n/a'}; "
                   f"signed: {sig.get('time') or 'n/a'}; validation state: {state or 'n/a'}",
        )]
        score, conf, decisive = 0.5, 0.0, None

        tamper = [c for c in failures if any(t in c.lower() for t in TAMPER_CODES)]
        untrusted = [c for c in failures if "untrusted" in c.lower()]
        other_failures = [c for c in failures if c not in tamper and c not in untrusted]

        if tamper:
            score, conf = 0.88, 0.85
            findings.append(Finding(
                severity=Severity.HIGH, title="Content changed after it was signed",
                detail=f"Validation failures: {', '.join(tamper)}",
            ))
        if any(t in s for s in source_types for t in AI_SOURCE_TYPES):
            composite = any("composite" in s for s in source_types)
            decisive = ("C2PA provenance declares AI-assisted composite" if composite
                        else "C2PA provenance declares AI-generated content")
            score, conf = max(score, 0.98), 0.95
            findings.append(Finding(severity=Severity.CRITICAL, title=decisive,
                                    detail=f"digitalSourceType values: {sorted(set(source_types))}"))
        edits = sorted(set(action_names) & EDIT_ACTIONS)
        if edits and not decisive:
            score, conf = max(score, 0.6), max(conf, 0.6)
            findings.append(Finding(
                severity=Severity.MEDIUM, title="Provenance records edits",
                detail=f"Declared actions: {', '.join(edits)}",
            ))
        if (not tamper and not decisive and not edits
                and any(t in s for s in source_types for t in CAPTURE_SOURCE_TYPES)):
            score, conf = 0.1, 0.85
            findings.append(Finding(
                severity=Severity.INFO, title="Signed camera capture with no recorded edits",
                detail="Strong evidence of authenticity if the signer is trusted.",
            ))
        if untrusted:
            conf *= 0.7
            findings.append(Finding(
                severity=Severity.LOW, title="Signer not in a configured trust list",
                detail=", ".join(untrusted),
            ))
        if other_failures:
            findings.append(Finding(severity=Severity.LOW, title="Other validation issues",
                                    detail=", ".join(other_failures)))

        if decisive:
            kind = EvidenceKind.SYNTHESIS
        elif tamper or edits:
            kind = EvidenceKind.MANIPULATION
        else:
            kind = EvidenceKind.PROVENANCE  # signed capture: speaks to both questions
        return self.result(
            score=score, confidence=conf, findings=findings, decisive_label=decisive, evidence_kind=kind,
            data={"validation_state": state, "failures": failures, "actions": action_names,
                  "digital_source_types": sorted(set(source_types)), "manifest_store": store},
            limitations=["A valid manifest proves who signed what was declared, not that the declaration is true."],
        )
