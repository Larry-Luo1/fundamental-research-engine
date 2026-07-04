from __future__ import annotations

import re
from typing import Any

from .stages import CAUSAL_CONFIDENCE_VALUES, CAUSAL_DIRECTIONS, SCORECARD_FIELDS

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_REQUIRED_TOP_LEVEL: dict[str, type] = {
    "id": str,
    "title": str,
    "as_of": str,
    "theme_type": str,
    "domain": str,
    "core_question": str,
    "thesis": str,
    "hype_stage": str,
    "technology_readiness_level": int,
}

_LIST_FIELDS = [
    "drivers",
    "causal_map",
    "bottlenecks",
    "segments",
    "profit_pools",
    "companies",
    "scenarios",
    "evidence",
    "counter_theses",
    "tracking_signals",
]


def _check_type(value: Any, expected: type, path: str, errors: list[str]) -> bool:
    if expected is int and isinstance(value, bool):
        errors.append(f"{path}: expected int, got bool")
        return False
    if not isinstance(value, expected):
        errors.append(f"{path}: expected {expected.__name__}, got {type(value).__name__}")
        return False
    return True


def _check_required_fields(data: dict[str, Any], required: dict[str, type], prefix: str, errors: list[str]) -> None:
    for field, expected_type in required.items():
        if field not in data:
            errors.append(f"{prefix}: missing required field '{field}'")
        else:
            _check_type(data[field], expected_type, f"{prefix}.{field}", errors)


def _validate_evidence(items: Any, errors: list[str]) -> set[str]:
    ids: set[str] = set()
    if not isinstance(items, list):
        errors.append("evidence: expected list")
        return ids
    for index, item in enumerate(items):
        prefix = f"evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _check_required_fields(
            item,
            {"id": str, "title": str, "source_type": str, "date": str},
            prefix,
            errors,
        )
        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in ids:
                errors.append(f"{prefix}: duplicate evidence id '{item_id}'")
            ids.add(item_id)
        date = item.get("date")
        if isinstance(date, str) and not _DATE_RE.match(date):
            errors.append(f"{prefix}.date: '{date}' is not in YYYY-MM-DD format")
        if "url" in item:
            _check_type(item["url"], str, f"{prefix}.url", errors)
        reliability = item.get("reliability")
        if isinstance(reliability, str) and reliability not in {"high", "medium", "low"}:
            errors.append(f"{prefix}.reliability: unknown value '{reliability}'")
        if "claims" in item and not isinstance(item["claims"], list):
            errors.append(f"{prefix}.claims: expected list")
        elif isinstance(item.get("claims"), list):
            for claim_index, claim in enumerate(item["claims"]):
                if not isinstance(claim, str):
                    errors.append(f"{prefix}.claims[{claim_index}]: expected str, got {type(claim).__name__}")
    return ids


def _validate_evidence_ids(owner_prefix: str, evidence_ids: Any, known_ids: set[str], errors: list[str]) -> None:
    if not isinstance(evidence_ids, list):
        errors.append(f"{owner_prefix}.evidence_ids: expected list")
        return
    for eid in evidence_ids:
        if eid not in known_ids:
            errors.append(f"{owner_prefix}.evidence_ids: unknown evidence id '{eid}'")


def _known_claim_ids(evidence_items: Any) -> set[str]:
    known: set[str] = set()
    if not isinstance(evidence_items, list):
        return known
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("id")
        claims = item.get("claims", [])
        if not isinstance(evidence_id, str) or not isinstance(claims, list):
            continue
        for index, claim in enumerate(claims, start=1):
            if isinstance(claim, str):
                known.add(f"{evidence_id}.C{index}")
    return known


def _validate_claim_ids(
    owner_prefix: str,
    claim_ids: Any,
    known_evidence_ids: set[str],
    known_claim_ids: set[str],
    errors: list[str],
) -> None:
    if not isinstance(claim_ids, list):
        errors.append(f"{owner_prefix}.claim_ids: expected list")
        return
    if not claim_ids:
        errors.append(f"{owner_prefix}.claim_ids: at least one claim id is required")
        return
    for index, claim_id in enumerate(claim_ids):
        path = f"{owner_prefix}.claim_ids[{index}]"
        if not isinstance(claim_id, str):
            errors.append(f"{path}: expected str, got {type(claim_id).__name__}")
            continue
        evidence_id, separator, suffix = claim_id.partition(".")
        if not separator:
            errors.append(f"{path}: expected '<evidence_id>.C<n>' or '<evidence_id>.Q<n>'")
            continue
        if evidence_id not in known_evidence_ids:
            errors.append(f"{path}: unknown evidence id '{evidence_id}'")
            continue
        if suffix.startswith("C") and suffix[1:].isdigit():
            if claim_id not in known_claim_ids:
                errors.append(f"{path}: unknown applied claim id '{claim_id}'")
        elif suffix.startswith("Q") and suffix[1:].isdigit():
            # Q ids refer to quote-verified candidate records in the evidence store sidecar.
            continue
        else:
            errors.append(f"{path}: expected '<evidence_id>.C<n>' or '<evidence_id>.Q<n>'")


def _validate_optional_id(item: dict[str, Any], prefix: str, errors: list[str]) -> None:
    if "id" in item:
        _check_type(item["id"], str, f"{prefix}.id", errors)


def _validate_unique_ids(items: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(items, list):
        return
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        if item_id in seen:
            errors.append(f"{prefix}[{index}].id: duplicate id '{item_id}'")
        seen.add(item_id)


def _validate_bottlenecks(items: Any, ontology: dict[str, Any], known_evidence_ids: set[str], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("bottlenecks: expected list")
        return
    if not items:
        errors.append("bottlenecks: at least one bottleneck is required")
    _validate_unique_ids(items, "bottlenecks", errors)
    bottleneck_types = set(ontology.get("bottleneck_types", []))
    for index, item in enumerate(items):
        prefix = f"bottlenecks[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _validate_optional_id(item, prefix, errors)
        _check_required_fields(
            item,
            {"name": str, "types": list, "technical_reason": str, "scorecard": dict, "evidence_ids": list},
            prefix,
            errors,
        )
        if isinstance(item.get("types"), list):
            for type_index, type_name in enumerate(item.get("types", [])):
                if not isinstance(type_name, str):
                    errors.append(f"{prefix}.types[{type_index}]: expected str, got {type(type_name).__name__}")
                elif type_name not in bottleneck_types:
                    errors.append(f"{prefix}.types: unknown bottleneck type '{type_name}'")
        scorecard = item.get("scorecard", {})
        if isinstance(scorecard, dict):
            missing = sorted(set(SCORECARD_FIELDS) - set(scorecard))
            unexpected = sorted(set(scorecard) - set(SCORECARD_FIELDS))
            for key in missing:
                errors.append(f"{prefix}.scorecard.{key}: missing")
            for key in unexpected:
                errors.append(f"{prefix}.scorecard.{key}: unexpected dimension")
            for key, value in scorecard.items():
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(f"{prefix}.scorecard.{key}: expected numeric value")
                elif not 0 <= value <= 5:
                    errors.append(f"{prefix}.scorecard.{key}: {value} outside 0-5 scale")
        _validate_evidence_ids(prefix, item.get("evidence_ids", []), known_evidence_ids, errors)


def _validate_causal_map(
    items: Any,
    known_evidence_ids: set[str],
    known_claim_ids: set[str],
    errors: list[str],
) -> None:
    if not isinstance(items, list):
        errors.append("causal_map: expected list")
        return
    _validate_unique_ids(items, "causal_map", errors)
    for index, item in enumerate(items):
        prefix = f"causal_map[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _check_required_fields(
            item,
            {
                "id": str,
                "source": str,
                "target": str,
                "relationship": str,
                "transmission": str,
                "direction": str,
                "lag": str,
                "confidence": str,
                "claim_ids": list,
            },
            prefix,
            errors,
        )
        direction = item.get("direction")
        if isinstance(direction, str) and direction not in CAUSAL_DIRECTIONS:
            errors.append(f"{prefix}.direction: unknown value '{direction}'")
        confidence = item.get("confidence")
        if isinstance(confidence, str) and confidence not in CAUSAL_CONFIDENCE_VALUES:
            errors.append(f"{prefix}.confidence: unknown value '{confidence}'")
        _validate_claim_ids(prefix, item.get("claim_ids", []), known_evidence_ids, known_claim_ids, errors)


def _validate_segments(items: Any, ontology: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("segments: expected list")
        return
    _validate_unique_ids(items, "segments", errors)
    beneficiary_layers = set(ontology.get("beneficiary_layers", []))
    for index, item in enumerate(items):
        prefix = f"segments[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _validate_optional_id(item, prefix, errors)
        _check_required_fields(
            item,
            {"name": str, "layer": str, "role": str, "beneficiary_class": str, "representative_companies": list},
            prefix,
            errors,
        )
        beneficiary_class = item.get("beneficiary_class")
        if isinstance(beneficiary_class, str) and beneficiary_class not in beneficiary_layers:
            errors.append(f"{prefix}.beneficiary_class: unknown value '{beneficiary_class}'")
        if isinstance(item.get("representative_companies"), list):
            for company_index, company in enumerate(item["representative_companies"]):
                if not isinstance(company, str):
                    errors.append(f"{prefix}.representative_companies[{company_index}]: expected str, got {type(company).__name__}")


def _validate_profit_pools(items: Any, ontology: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("profit_pools: expected list")
        return
    _validate_unique_ids(items, "profit_pools", errors)
    capture_qualities = set(ontology.get("capture_qualities", []))
    for index, item in enumerate(items):
        prefix = f"profit_pools[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _validate_optional_id(item, prefix, errors)
        _check_required_fields(
            item,
            {"name": str, "rationale": str, "capture_quality": str, "beneficiaries": list},
            prefix,
            errors,
        )
        capture_quality = item.get("capture_quality")
        if capture_qualities and isinstance(capture_quality, str) and capture_quality not in capture_qualities:
            errors.append(f"{prefix}.capture_quality: unknown value '{capture_quality}'")
        if isinstance(item.get("beneficiaries"), list):
            for beneficiary_index, beneficiary in enumerate(item["beneficiaries"]):
                if not isinstance(beneficiary, str):
                    errors.append(f"{prefix}.beneficiaries[{beneficiary_index}]: expected str, got {type(beneficiary).__name__}")


def _validate_companies(items: Any, ontology: dict[str, Any], known_evidence_ids: set[str], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("companies: expected list")
        return
    _validate_unique_ids(items, "companies", errors)
    positioning_labels = set(ontology.get("company_positioning_labels", []))
    for index, item in enumerate(items):
        prefix = f"companies[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _validate_optional_id(item, prefix, errors)
        _check_required_fields(
            item,
            {
                "name": str,
                "product": str,
                "stack_position": str,
                "positioning_label": str,
                "exposure_quality": str,
                "moat": list,
                "risks": list,
                "evidence_ids": list,
            },
            prefix,
            errors,
        )
        label = item.get("positioning_label")
        if isinstance(label, str) and label not in positioning_labels:
            errors.append(f"{prefix}.positioning_label: unknown value '{label}'")
        for field in ["moat", "risks"]:
            if isinstance(item.get(field), list):
                for value_index, value in enumerate(item[field]):
                    if not isinstance(value, str):
                        errors.append(f"{prefix}.{field}[{value_index}]: expected str, got {type(value).__name__}")
        _validate_evidence_ids(prefix, item.get("evidence_ids", []), known_evidence_ids, errors)


def _validate_scenarios(items: Any, known_evidence_ids: set[str], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("scenarios: expected list")
        return
    _validate_unique_ids(items, "scenarios", errors)
    for index, item in enumerate(items):
        prefix = f"scenarios[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _validate_optional_id(item, prefix, errors)
        _check_required_fields(item, {"name": str, "description": str, "implications": list, "triggers": list}, prefix, errors)
        for field in ["implications", "triggers"]:
            if isinstance(item.get(field), list):
                for value_index, value in enumerate(item[field]):
                    if not isinstance(value, str):
                        errors.append(f"{prefix}.{field}[{value_index}]: expected str, got {type(value).__name__}")
        if "evidence_ids" in item:
            _validate_evidence_ids(prefix, item["evidence_ids"], known_evidence_ids, errors)


def validate_theme_dict(data: dict[str, Any], ontology: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["theme: expected a JSON object"]

    _check_required_fields(data, _REQUIRED_TOP_LEVEL, "theme", errors)

    as_of = data.get("as_of")
    if isinstance(as_of, str) and not _DATE_RE.match(as_of):
        errors.append(f"theme.as_of: '{as_of}' is not in YYYY-MM-DD format")

    theme_type = data.get("theme_type")
    theme_types = ontology.get("theme_types", [])
    if isinstance(theme_type, str) and theme_types and theme_type not in theme_types:
        errors.append(f"theme.theme_type: unknown value '{theme_type}'")

    hype_stage = data.get("hype_stage")
    hype_stages = ontology.get("hype_stages", [])
    if isinstance(hype_stage, str) and hype_stages and hype_stage not in hype_stages:
        errors.append(f"theme.hype_stage: unknown value '{hype_stage}'")

    trl = data.get("technology_readiness_level")
    if isinstance(trl, int) and not isinstance(trl, bool) and not 1 <= trl <= 9:
        errors.append(f"theme.technology_readiness_level: {trl} outside 1-9 range")

    for field in _LIST_FIELDS:
        if field in data and not isinstance(data[field], list):
            errors.append(f"theme.{field}: expected list")
    for field in ["drivers", "counter_theses", "tracking_signals"]:
        if isinstance(data.get(field), list):
            for index, value in enumerate(data[field]):
                if not isinstance(value, str):
                    errors.append(f"theme.{field}[{index}]: expected str, got {type(value).__name__}")

    evidence_items = data.get("evidence", [])
    known_evidence_ids = _validate_evidence(evidence_items, errors)
    known_claim_ids = _known_claim_ids(evidence_items)
    _validate_causal_map(data.get("causal_map", []), known_evidence_ids, known_claim_ids, errors)
    _validate_bottlenecks(data.get("bottlenecks", []), ontology, known_evidence_ids, errors)
    _validate_segments(data.get("segments", []), ontology, errors)
    _validate_profit_pools(data.get("profit_pools", []), ontology, errors)
    _validate_companies(data.get("companies", []), ontology, known_evidence_ids, errors)
    _validate_scenarios(data.get("scenarios", []), known_evidence_ids, errors)

    if "thesis_evidence_ids" in data:
        _validate_evidence_ids("theme", data["thesis_evidence_ids"], known_evidence_ids, errors)

    return errors


class ThemeValidationError(ValueError):
    def __init__(self, path: str, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        message = f"Theme config {path} failed validation:\n" + "\n".join(f"- {item}" for item in errors)
        super().__init__(message)
