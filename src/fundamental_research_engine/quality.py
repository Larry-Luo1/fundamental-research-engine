"""Deterministic analysis-quality signals (no LLM).

Grounding checks + a quality scorecard. This is a *process-health* layer, not a
truth score for the thesis: it measures whether the analysis is well-evidenced,
corroborated, and (once the adversarial QC runs) disconfirmed — never whether
the conclusion is correct.
"""

from __future__ import annotations

from typing import Any

from .models import Evidence

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

    return {
        "grounding_score": grounding_score,
        "grounding": grounding,
        "disconfirmation": disconfirmation,
        "calibration": calibration,
        "flags": flags,
        "note": "process-health signal, not a truth score for the thesis",
    }
