from __future__ import annotations

import re
from typing import Any

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
    return ids


def _validate_evidence_ids(owner_prefix: str, evidence_ids: Any, known_ids: set[str], errors: list[str]) -> None:
    if not isinstance(evidence_ids, list):
        errors.append(f"{owner_prefix}.evidence_ids: expected list")
        return
    for eid in evidence_ids:
        if eid not in known_ids:
            errors.append(f"{owner_prefix}.evidence_ids: unknown evidence id '{eid}'")


def _validate_bottlenecks(items: Any, ontology: dict[str, Any], known_evidence_ids: set[str], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("bottlenecks: expected list")
        return
    if not items:
        errors.append("bottlenecks: at least one bottleneck is required")
    bottleneck_types = set(ontology.get("bottleneck_types", []))
    for index, item in enumerate(items):
        prefix = f"bottlenecks[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _check_required_fields(
            item,
            {"name": str, "technical_reason": str, "scorecard": dict},
            prefix,
            errors,
        )
        for type_name in item.get("types", []):
            if type_name not in bottleneck_types:
                errors.append(f"{prefix}.types: unknown bottleneck type '{type_name}'")
        scorecard = item.get("scorecard", {})
        if isinstance(scorecard, dict):
            for key, value in scorecard.items():
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(f"{prefix}.scorecard.{key}: expected numeric value")
                elif not 0 <= value <= 5:
                    errors.append(f"{prefix}.scorecard.{key}: {value} outside 0-5 scale")
        _validate_evidence_ids(prefix, item.get("evidence_ids", []), known_evidence_ids, errors)


def _validate_segments(items: Any, ontology: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("segments: expected list")
        return
    beneficiary_layers = set(ontology.get("beneficiary_layers", []))
    for index, item in enumerate(items):
        prefix = f"segments[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _check_required_fields(
            item,
            {"name": str, "layer": str, "role": str, "beneficiary_class": str},
            prefix,
            errors,
        )
        beneficiary_class = item.get("beneficiary_class")
        if isinstance(beneficiary_class, str) and beneficiary_class not in beneficiary_layers:
            errors.append(f"{prefix}.beneficiary_class: unknown value '{beneficiary_class}'")


def _validate_profit_pools(items: Any, ontology: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("profit_pools: expected list")
        return
    capture_qualities = set(ontology.get("capture_qualities", []))
    for index, item in enumerate(items):
        prefix = f"profit_pools[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _check_required_fields(
            item,
            {"name": str, "rationale": str, "capture_quality": str},
            prefix,
            errors,
        )
        capture_quality = item.get("capture_quality")
        if capture_qualities and isinstance(capture_quality, str) and capture_quality not in capture_qualities:
            errors.append(f"{prefix}.capture_quality: unknown value '{capture_quality}'")


def _validate_companies(items: Any, ontology: dict[str, Any], known_evidence_ids: set[str], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("companies: expected list")
        return
    positioning_labels = set(ontology.get("company_positioning_labels", []))
    for index, item in enumerate(items):
        prefix = f"companies[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _check_required_fields(
            item,
            {
                "name": str,
                "product": str,
                "stack_position": str,
                "positioning_label": str,
                "exposure_quality": str,
            },
            prefix,
            errors,
        )
        label = item.get("positioning_label")
        if isinstance(label, str) and label not in positioning_labels:
            errors.append(f"{prefix}.positioning_label: unknown value '{label}'")
        _validate_evidence_ids(prefix, item.get("evidence_ids", []), known_evidence_ids, errors)


def _validate_scenarios(items: Any, errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("scenarios: expected list")
        return
    for index, item in enumerate(items):
        prefix = f"scenarios[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        _check_required_fields(item, {"name": str, "description": str}, prefix, errors)


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

    known_evidence_ids = _validate_evidence(data.get("evidence", []), errors)
    _validate_bottlenecks(data.get("bottlenecks", []), ontology, known_evidence_ids, errors)
    _validate_segments(data.get("segments", []), ontology, errors)
    _validate_profit_pools(data.get("profit_pools", []), ontology, errors)
    _validate_companies(data.get("companies", []), ontology, known_evidence_ids, errors)
    _validate_scenarios(data.get("scenarios", []), errors)

    return errors


class ThemeValidationError(ValueError):
    def __init__(self, path: str, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        message = f"Theme config {path} failed validation:\n" + "\n".join(f"- {item}" for item in errors)
        super().__init__(message)
