"""Deterministic analysis-quality signals (no LLM).

Grounding checks + a quality scorecard. This is a *process-health* layer, not a
truth score for the thesis: it measures whether the analysis is well-evidenced,
corroborated, and (once the adversarial QC runs) disconfirmed — never whether
the conclusion is correct.
"""

from __future__ import annotations

from typing import Any

from .models import CausalEdge, Evidence

# Same policy weights as the evidence audit; kept local so this module is
# self-contained and importable without pulling in the fetch machinery.
RELIABILITY_WEIGHTS = {"high": 1.0, "medium": 0.7, "low": 0.4}

_REVIEW_SEVERITIES = {"high", "medium", "low"}
_REVIEW_RECOMMENDATIONS = {"accept", "revise"}
_REQUIRED_LENSES = ("premortem", "steelman_bear", "consistency", "unsupported_claims")


def validate_quality_review_shape(data: Any) -> list[str]:
    """Validate the adversarial quality-review JSON (style matches validate_critique_shape)."""
    if not isinstance(data, dict):
        return ["quality_review: expected a JSON object"]

    errors = [f"quality_review.{field}: missing" for field in ("lenses", "open_concerns", "recommendation") if field not in data]
    if errors:
        return errors

    lenses = data["lenses"]
    if not isinstance(lenses, dict):
        errors.append("quality_review.lenses: expected object")
    else:
        for name in _REQUIRED_LENSES:
            if name not in lenses:
                errors.append(f"quality_review.lenses.{name}: missing")
            elif not isinstance(lenses[name], dict):
                errors.append(f"quality_review.lenses.{name}: expected object")

    concerns = data["open_concerns"]
    if not isinstance(concerns, list):
        errors.append("quality_review.open_concerns: expected list")
    else:
        for index, item in enumerate(concerns):
            prefix = f"quality_review.open_concerns[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix}: expected object")
                continue
            severity = item.get("severity")
            if not isinstance(severity, str):
                errors.append(f"{prefix}.severity: expected str")
            elif severity not in _REVIEW_SEVERITIES:
                errors.append(f"{prefix}.severity: unknown value '{severity}'")
            if not isinstance(item.get("issue"), str):
                errors.append(f"{prefix}.issue: expected str")

    recommendation = data["recommendation"]
    if not isinstance(recommendation, str) or recommendation not in _REVIEW_RECOMMENDATIONS:
        errors.append(f"quality_review.recommendation: unknown value '{recommendation}'")

    return errors


def _weight(reliability: str) -> float:
    return RELIABILITY_WEIGHTS.get(reliability, 0.5)


def _source_key(ev: Evidence) -> str:
    """Identify an independent source: prefer URL, fall back to title."""
    url = (ev.url or "").strip()
    return url if url else (ev.title or "").strip()


def _edge_value(edge: CausalEdge | dict[str, Any] | Any, field: str, default: Any = None) -> Any:
    if isinstance(edge, dict):
        return edge.get(field, default)
    return getattr(edge, field, default)


def _normalize_provenance_records(claim_provenance: Any) -> list[dict[str, Any]]:
    if claim_provenance is None:
        return []
    if isinstance(claim_provenance, dict):
        records = claim_provenance.get("records", [])
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict)]
        return []
    if isinstance(claim_provenance, list):
        return [item for item in claim_provenance if isinstance(item, dict)]
    return []


def _claim_index(
    evidence: list[Evidence],
    claim_provenance: Any = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    evidence_by_id = {item.id: item for item in evidence}
    provenance_by_id = {
        str(item.get("claim_id")): item
        for item in _normalize_provenance_records(claim_provenance)
        if item.get("claim_id")
    }

    claims: dict[str, dict[str, Any]] = {}
    for ev in evidence:
        for index, claim in enumerate(ev.claims, start=1):
            claim_id = f"{ev.id}.C{index}"
            provenance = provenance_by_id.get(claim_id, {})
            claims[claim_id] = {
                "claim_id": claim_id,
                "evidence_id": ev.id,
                "claim": claim,
                "source_type": ev.source_type,
                "reliability": ev.reliability,
                "source_key": _source_key(ev) or ev.id,
                "status": "applied",
                "provenance": provenance,
            }

    for claim_id, provenance in provenance_by_id.items():
        if claim_id in claims:
            continue
        evidence_id = str(provenance.get("evidence_id", claim_id.partition(".")[0]))
        ev = evidence_by_id.get(evidence_id)
        source_key = str(provenance.get("source_url") or provenance.get("source_title") or "").strip()
        if not source_key and ev is not None:
            source_key = _source_key(ev)
        claims[claim_id] = {
            "claim_id": claim_id,
            "evidence_id": evidence_id,
            "claim": str(provenance.get("claim", "")),
            "source_type": str(provenance.get("source_type") or (ev.source_type if ev else "")),
            "reliability": str(provenance.get("reliability") or (ev.reliability if ev else "")),
            "source_key": source_key or evidence_id,
            "status": str(provenance.get("status", "candidate")),
            "provenance": provenance,
        }

    return claims, provenance_by_id


def _quote_verified(provenance: dict[str, Any]) -> bool:
    quote = str(provenance.get("quote") or "").strip()
    return bool(provenance.get("verified")) and bool(quote)


def build_causal_quality(
    causal_map: list[CausalEdge] | list[dict[str, Any]] | list[Any],
    evidence: list[Evidence],
    claim_provenance: Any = None,
) -> dict[str, Any]:
    """Score whether causal edges are supported by cited claim provenance."""
    claims_by_id, provenance_by_id = _claim_index(evidence, claim_provenance)
    edges_out: list[dict[str, Any]] = []
    flags: list[str] = []
    supported_count = 0
    fully_quote_verified_count = 0
    thin_count = 0
    low_confidence_count = 0
    missing_claim_edges = 0
    weak_count = 0

    for edge in causal_map:
        edge_id = str(_edge_value(edge, "id", "") or "causal_edge")
        claim_ids = [str(item) for item in (_edge_value(edge, "claim_ids", []) or [])]
        confidence = str(_edge_value(edge, "confidence", "") or "")
        resolved = [claims_by_id[item] for item in claim_ids if item in claims_by_id]
        missing = [item for item in claim_ids if item not in claims_by_id]
        distinct_sources = {item["source_key"] for item in resolved if item.get("source_key")}
        distinct_source_types = {item["source_type"] for item in resolved if item.get("source_type")}
        reliability_max = max((item["reliability"] for item in resolved), key=_weight, default="")

        quote_verified_ids: list[str] = []
        unverified_claim_ids: list[str] = []
        for claim_id in claim_ids:
            if claim_id in missing:
                continue
            provenance = provenance_by_id.get(claim_id) or claims_by_id.get(claim_id, {}).get("provenance", {})
            if _quote_verified(provenance):
                quote_verified_ids.append(claim_id)
            else:
                unverified_claim_ids.append(claim_id)

        supported = bool(resolved) and not missing
        thin = bool(resolved) and len(distinct_sources) <= 1
        low_confidence = confidence == "low"
        weak_evidence = not supported or reliability_max in {"", "low"}
        fully_quote_verified = bool(resolved) and not missing and not unverified_claim_ids

        if supported:
            supported_count += 1
        if fully_quote_verified:
            fully_quote_verified_count += 1
        if thin:
            thin_count += 1
        if low_confidence:
            low_confidence_count += 1
        if missing:
            missing_claim_edges += 1
        if weak_evidence:
            weak_count += 1

        if missing:
            flags.append(f"causal edge '{edge_id}' has missing claim ids: {', '.join(missing)}")
        if weak_evidence:
            flags.append(f"causal edge '{edge_id}' has weak evidence coverage")
        if unverified_claim_ids:
            flags.append(
                f"causal edge '{edge_id}' lacks quote-verified provenance for: "
                f"{', '.join(unverified_claim_ids)}"
            )
        if thin:
            flags.append(f"causal edge '{edge_id}' is supported by a single source")
        if low_confidence:
            flags.append(f"causal edge '{edge_id}' is low confidence; do not let it drive a high-conviction thesis")

        edges_out.append(
            {
                "id": edge_id,
                "claim_ids": claim_ids,
                "resolved_claim_ids": [item["claim_id"] for item in resolved],
                "missing_claim_ids": missing,
                "evidence_count": len({item["evidence_id"] for item in resolved if item.get("evidence_id")}),
                "distinct_sources": len(distinct_sources),
                "distinct_source_types": len(distinct_source_types),
                "reliability_max": reliability_max or None,
                "quote_verified_claim_count": len(quote_verified_ids),
                "unverified_claim_ids": unverified_claim_ids,
                "supported": supported,
                "fully_quote_verified": fully_quote_verified,
                "thin": thin,
                "low_confidence": low_confidence,
                "weak_evidence": weak_evidence,
            }
        )

    edge_count = len(causal_map)
    if edge_count and thin_count / edge_count > 0.5:
        flags.append(f"causal map has {thin_count}/{edge_count} single-source edges")

    return {
        "edges": edges_out,
        "summary": {
            "edges": edge_count,
            "supported": supported_count,
            "fully_quote_verified": fully_quote_verified_count,
            "thin": thin_count,
            "low_confidence": low_confidence_count,
            "missing_claims": missing_claim_edges,
            "weak_evidence": weak_count,
        },
        "flags": flags,
    }


def _empty_causal_quality() -> dict[str, Any]:
    return {
        "edges": [],
        "summary": {
            "edges": 0,
            "supported": 0,
            "fully_quote_verified": 0,
            "thin": 0,
            "low_confidence": 0,
            "missing_claims": 0,
            "weak_evidence": 0,
        },
        "flags": [],
    }


def build_quality_status(
    grounding_score: float,
    grounding: dict[str, Any],
    causal_quality: dict[str, Any],
    flags: list[str],
    disconfirmation: dict[str, Any],
) -> dict[str, Any]:
    """Assign a deterministic process tier for the analysis artifact."""
    causal_summary = causal_quality.get("summary", {})
    causal_edges = int(causal_summary.get("edges", 0) or 0)
    blockers: list[str] = []

    evidence_backed = grounding["summary"].get("grounded", 0) > 0 and grounding_score >= 0.5
    if not evidence_backed:
        blockers.append("insufficient grounded evidence coverage")

    quote_verified = (
        causal_edges > 0
        and causal_summary.get("fully_quote_verified", 0) == causal_edges
        and causal_summary.get("missing_claims", 0) == 0
    )
    if causal_edges and not quote_verified:
        blockers.append("causal map is not fully quote-verified")

    multi_source_causal = (
        quote_verified
        and causal_summary.get("thin", 0) == 0
        and causal_summary.get("weak_evidence", 0) == 0
        and causal_summary.get("low_confidence", 0) == 0
    )
    if quote_verified and not multi_source_causal:
        blockers.append("causal map still has single-source, weak, or low-confidence edges")

    review_ready = (
        multi_source_causal
        and grounding_score >= 0.7
        and not grounding.get("ungrounded")
        and disconfirmation.get("premortem_done")
        and disconfirmation.get("steelman_done")
        and disconfirmation.get("open_critical", 0) == 0
        and not flags
    )
    if multi_source_causal and not review_ready:
        blockers.append(
            "review-ready requires stronger grounding, adversarial review, and no open quality flags"
        )

    tiers = ["draft"]
    if evidence_backed:
        tiers.append("evidence-backed")
    if quote_verified:
        tiers.append("quote-verified")
    if multi_source_causal:
        tiers.append("multi-source causal map")
    if review_ready:
        tiers.append("review-ready")

    return {
        "tier": tiers[-1],
        "satisfied": tiers,
        "blockers": blockers,
        "policy": {
            "evidence_backed": "grounding_score >= 0.5 and at least one grounded owner",
            "quote_verified": "all causal edges are backed by quote-verified claim ids",
            "multi_source_causal_map": "quote-verified causal map with no single-source, weak, or low-confidence edges",
            "review_ready": "multi-source causal map, grounding_score >= 0.7, adversarial review complete, no ungrounded owners, no critical concerns, no flags — the process gate is met; the human still judges the memo",
        },
    }


def build_grounding(
    evidence: list[Evidence],
    owners_by_kind: dict[str, list[Any]],
) -> dict[str, Any]:
    """Score how well each claim owner (bottleneck/company) is evidenced.

    Each owner must expose ``id``, ``name`` and ``evidence_ids``.
    """
    by_id = {item.id: item for item in evidence}
    owners_out: list[dict[str, Any]] = []
    ungrounded: list[str] = []
    thin: list[str] = []
    weighted_sum = 0.0
    corroborated_count = 0
    total = 0

    for kind, owners in owners_by_kind.items():
        for owner in owners:
            total += 1
            linked = [by_id[eid] for eid in owner.evidence_ids if eid in by_id]
            distinct_sources = {key for key in (_source_key(e) for e in linked) if key}
            distinct_types = {e.source_type for e in linked}
            grounded = len(linked) >= 1
            corroborated = len(distinct_sources) >= 2
            reliability_max = max((e.reliability for e in linked), key=_weight, default="")

            weighted_sum += _weight(reliability_max) if grounded else 0.0
            if corroborated:
                corroborated_count += 1
            if not grounded:
                ungrounded.append(owner.id)
            elif len(distinct_sources) <= 1:
                thin.append(owner.id)

            owners_out.append(
                {
                    "id": owner.id,
                    "kind": kind,
                    "name": owner.name,
                    "evidence_count": len(linked),
                    "distinct_sources": len(distinct_sources),
                    "distinct_source_types": len(distinct_types),
                    "reliability_max": reliability_max or None,
                    "grounded": grounded,
                    "corroborated": corroborated,
                }
            )

    rwc = round(weighted_sum / total, 2) if total else 0.0
    corroboration_ratio = round(corroborated_count / total, 2) if total else 0.0
    return {
        "owners": owners_out,
        "ungrounded": ungrounded,
        "thin": thin,
        "reliability_weighted_coverage": rwc,
        "corroboration_ratio": corroboration_ratio,
        "summary": {
            "owners": total,
            "grounded": total - len(ungrounded),
            "corroborated": corroborated_count,
            "ungrounded": len(ungrounded),
            "thin": len(thin),
        },
    }


def build_quality_scorecard(
    grounding: dict[str, Any],
    review: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
    causal_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate grounding (+ optional adversarial review / calibration) into a scorecard."""
    rwc = grounding["reliability_weighted_coverage"]
    corroboration = grounding["corroboration_ratio"]
    grounding_score = round(0.7 * rwc + 0.3 * corroboration, 2)

    disconfirmation = {
        "premortem_done": False,
        "steelman_done": False,
        "open_critical": 0,
        "open_major": 0,
    }
    if review:
        lenses = review.get("lenses", {})
        disconfirmation["premortem_done"] = "premortem" in lenses
        disconfirmation["steelman_done"] = "steelman_bear" in lenses
        for concern in review.get("open_concerns", []):
            severity = concern.get("severity")
            if severity == "high":
                disconfirmation["open_critical"] += 1
            elif severity == "medium":
                disconfirmation["open_major"] += 1

    # Placeholder for the calibration loop (a later step wires a real track record).
    calibration = calibration or {"track_record_runs": 0, "brier": None}

    owners_by_id = {owner["id"]: owner for owner in grounding["owners"]}
    flags: list[str] = []
    for owner_id in grounding["ungrounded"]:
        owner = owners_by_id.get(owner_id, {})
        flags.append(f"{owner.get('kind', 'owner')} '{owner.get('name', owner_id)}' has no linked evidence")
    for owner_id in grounding["thin"]:
        owner = owners_by_id.get(owner_id, {})
        flags.append(f"{owner.get('kind', 'owner')} '{owner.get('name', owner_id)}' is supported by a single source")
    if review:
        for concern in review.get("open_concerns", []):
            if concern.get("severity") == "high":
                flags.append(f"critical: {concern.get('issue', '')}")
    if causal_quality:
        flags.extend(str(item) for item in causal_quality.get("flags", []))
    causal_quality = causal_quality or _empty_causal_quality()
    quality_status = build_quality_status(
        grounding_score,
        grounding,
        causal_quality,
        flags,
        disconfirmation,
    )

    return {
        "grounding_score": grounding_score,
        "grounding": grounding,
        "causal_quality": causal_quality,
        "quality_status": quality_status,
        "disconfirmation": disconfirmation,
        "calibration": calibration,
        "flags": flags,
        "note": "process-health signal, not a truth score for the thesis",
    }
