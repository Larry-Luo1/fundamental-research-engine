from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io import read_json, write_json

STAGE_ORDER: list[str] = [
    "theme_definition",
    "mechanism_analysis",
    "bottleneck_diagnosis",
    "value_chain_map",
    "company_positioning",
    "scenario_analysis",
]

STAGE_FIELDS: dict[str, list[str]] = {
    "theme_definition": [
        "id",
        "title",
        "as_of",
        "theme_type",
        "domain",
        "core_question",
        "thesis",
        "hype_stage",
        "technology_readiness_level",
        "drivers",
    ],
    "mechanism_analysis": ["mechanism"],
    "bottleneck_diagnosis": ["bottlenecks"],
    "value_chain_map": ["segments", "profit_pools"],
    "company_positioning": ["companies"],
    "scenario_analysis": ["scenarios", "counter_theses", "tracking_signals", "evidence"],
}

SCORECARD_FIELDS: list[str] = [
    "demand_growth_speed",
    "capacity_expansion_difficulty",
    "technology_substitution_difficulty",
    "yield_material_equipment_constraint",
    "customer_qualification_lock_in",
    "supplier_pricing_power",
    "rapid_supply_release_risk",
    "architecture_bypass_risk",
]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StageError(ValueError):
    pass


def stage_path(theme_dir: Path, stage: str) -> Path:
    return theme_dir / f"{stage}.json"


def split_theme_dict(theme: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stages: dict[str, dict[str, Any]] = {}
    for stage, fields in STAGE_FIELDS.items():
        stages[stage] = {field: theme[field] for field in fields if field in theme}
    return stages


def merge_stage_dicts(stages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing_stages = [stage for stage in STAGE_ORDER if stage not in stages]
    if missing_stages:
        raise StageError(f"missing stage(s): {', '.join(missing_stages)}")

    theme: dict[str, Any] = {}
    for stage in STAGE_ORDER:
        theme.update(stages[stage])
    return theme


def write_theme_stage_dir(theme_dir: Path, theme: dict[str, Any]) -> None:
    for stage, data in split_theme_dict(theme).items():
        write_json(stage_path(theme_dir, stage), data)


def read_stage_dir_partial(theme_dir: Path) -> dict[str, dict[str, Any]]:
    stages: dict[str, dict[str, Any]] = {}
    for stage in STAGE_ORDER:
        path = stage_path(theme_dir, stage)
        if path.exists():
            stages[stage] = read_json(path)
    return stages


def load_theme_stage_dir(theme_dir: Path) -> dict[str, Any]:
    stages = read_stage_dir_partial(theme_dir)
    missing_stages = [stage for stage in STAGE_ORDER if stage not in stages]
    if missing_stages:
        raise StageError(
            f"theme directory {theme_dir} is missing stage file(s): "
            + ", ".join(f"{stage}.json" for stage in missing_stages)
        )
    return merge_stage_dicts(stages)


def next_missing_stage(stages: dict[str, dict[str, Any]]) -> str | None:
    for stage in STAGE_ORDER:
        if stage not in stages:
            return stage
    return None


def load_theme_source(path: Path) -> dict[str, Any]:
    if path.is_dir():
        return load_theme_stage_dir(path)
    return read_json(path)


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
            errors.append(f"{prefix}.{field}: missing")
        else:
            _check_type(data[field], expected_type, f"{prefix}.{field}", errors)


def _check_string_list(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: expected list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{path}[{index}]: expected str, got {type(item).__name__}")


def _check_enum(value: Any, valid_values: set[str], path: str, errors: list[str]) -> None:
    if valid_values and isinstance(value, str) and value not in valid_values:
        errors.append(f"{path}: unknown value '{value}'")


def _check_object_list(value: Any, path: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{path}: expected list")
        return []
    objects: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{path}[{index}]: expected object")
        else:
            objects.append(item)
    return objects


def _check_optional_id(data: dict[str, Any], path: str, errors: list[str]) -> None:
    if "id" in data:
        _check_type(data["id"], str, f"{path}.id", errors)


def _check_unique_ids(items: list[dict[str, Any]], path: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        if item_id in seen:
            errors.append(f"{path}[{index}].id: duplicate id '{item_id}'")
        seen.add(item_id)


def _validate_theme_definition_stage(data: dict[str, Any], ontology: dict[str, Any] | None, errors: list[str]) -> None:
    _check_required_fields(
        data,
        {
            "id": str,
            "title": str,
            "as_of": str,
            "theme_type": str,
            "domain": str,
            "core_question": str,
            "thesis": str,
            "hype_stage": str,
            "technology_readiness_level": int,
            "drivers": list,
        },
        "theme_definition",
        errors,
    )
    as_of = data.get("as_of")
    if isinstance(as_of, str) and not _DATE_RE.match(as_of):
        errors.append(f"theme_definition.as_of: '{as_of}' is not in YYYY-MM-DD format")
    trl = data.get("technology_readiness_level")
    if isinstance(trl, int) and not isinstance(trl, bool) and not 1 <= trl <= 9:
        errors.append(f"theme_definition.technology_readiness_level: {trl} outside 1-9 range")
    _check_string_list(data.get("drivers", []), "theme_definition.drivers", errors)
    ontology = ontology or {}
    _check_enum(data.get("theme_type"), set(ontology.get("theme_types", [])), "theme_definition.theme_type", errors)
    _check_enum(data.get("hype_stage"), set(ontology.get("hype_stages", [])), "theme_definition.hype_stage", errors)


def _validate_mechanism_stage(data: dict[str, Any], errors: list[str]) -> None:
    _check_required_fields(data, {"mechanism": str}, "mechanism_analysis", errors)


def _validate_bottleneck_stage(data: dict[str, Any], ontology: dict[str, Any] | None, errors: list[str]) -> None:
    items = _check_object_list(data.get("bottlenecks", []), "bottleneck_diagnosis.bottlenecks", errors)
    _check_unique_ids(items, "bottleneck_diagnosis.bottlenecks", errors)
    if "bottlenecks" in data and isinstance(data["bottlenecks"], list) and not data["bottlenecks"]:
        errors.append("bottleneck_diagnosis.bottlenecks: at least one bottleneck is required")
    bottleneck_types = set((ontology or {}).get("bottleneck_types", []))
    for index, item in enumerate(items):
        prefix = f"bottleneck_diagnosis.bottlenecks[{index}]"
        _check_optional_id(item, prefix, errors)
        _check_required_fields(
            item,
            {"name": str, "types": list, "technical_reason": str, "scorecard": dict, "evidence_ids": list},
            prefix,
            errors,
        )
        _check_string_list(item.get("types", []), f"{prefix}.types", errors)
        if isinstance(item.get("types", []), list):
            for type_name in item.get("types", []):
                _check_enum(type_name, bottleneck_types, f"{prefix}.types", errors)
        _check_string_list(item.get("evidence_ids", []), f"{prefix}.evidence_ids", errors)
        scorecard = item.get("scorecard", {})
        if isinstance(scorecard, dict):
            missing = sorted(set(SCORECARD_FIELDS) - set(scorecard))
            unexpected = sorted(set(scorecard) - set(SCORECARD_FIELDS))
            for field in missing:
                errors.append(f"{prefix}.scorecard.{field}: missing")
            for field in unexpected:
                errors.append(f"{prefix}.scorecard.{field}: unexpected dimension")
            for field, value in scorecard.items():
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(f"{prefix}.scorecard.{field}: expected numeric value")
                elif not 0 <= value <= 5:
                    errors.append(f"{prefix}.scorecard.{field}: {value} outside 0-5 scale")


def _validate_value_chain_stage(data: dict[str, Any], ontology: dict[str, Any] | None, errors: list[str]) -> None:
    beneficiary_layers = set((ontology or {}).get("beneficiary_layers", []))
    capture_qualities = set((ontology or {}).get("capture_qualities", []))
    segments = _check_object_list(data.get("segments", []), "value_chain_map.segments", errors)
    profit_pools = _check_object_list(data.get("profit_pools", []), "value_chain_map.profit_pools", errors)
    _check_unique_ids(segments, "value_chain_map.segments", errors)
    _check_unique_ids(profit_pools, "value_chain_map.profit_pools", errors)
    for index, item in enumerate(segments):
        prefix = f"value_chain_map.segments[{index}]"
        _check_optional_id(item, prefix, errors)
        _check_required_fields(
            item,
            {"name": str, "layer": str, "role": str, "beneficiary_class": str, "representative_companies": list},
            prefix,
            errors,
        )
        _check_enum(item.get("beneficiary_class"), beneficiary_layers, f"{prefix}.beneficiary_class", errors)
        _check_string_list(item.get("representative_companies", []), f"{prefix}.representative_companies", errors)
    for index, item in enumerate(profit_pools):
        prefix = f"value_chain_map.profit_pools[{index}]"
        _check_optional_id(item, prefix, errors)
        _check_required_fields(
            item,
            {"name": str, "rationale": str, "capture_quality": str, "beneficiaries": list},
            prefix,
            errors,
        )
        _check_enum(item.get("capture_quality"), capture_qualities, f"{prefix}.capture_quality", errors)
        _check_string_list(item.get("beneficiaries", []), f"{prefix}.beneficiaries", errors)


def _validate_company_stage(data: dict[str, Any], ontology: dict[str, Any] | None, errors: list[str]) -> None:
    labels = set((ontology or {}).get("company_positioning_labels", []))
    companies = _check_object_list(data.get("companies", []), "company_positioning.companies", errors)
    _check_unique_ids(companies, "company_positioning.companies", errors)
    for index, item in enumerate(companies):
        prefix = f"company_positioning.companies[{index}]"
        _check_optional_id(item, prefix, errors)
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
        _check_enum(item.get("positioning_label"), labels, f"{prefix}.positioning_label", errors)
        _check_string_list(item.get("moat", []), f"{prefix}.moat", errors)
        _check_string_list(item.get("risks", []), f"{prefix}.risks", errors)
        _check_string_list(item.get("evidence_ids", []), f"{prefix}.evidence_ids", errors)


def _validate_scenario_stage(data: dict[str, Any], errors: list[str]) -> None:
    scenarios = _check_object_list(data.get("scenarios", []), "scenario_analysis.scenarios", errors)
    _check_unique_ids(scenarios, "scenario_analysis.scenarios", errors)
    for index, item in enumerate(scenarios):
        prefix = f"scenario_analysis.scenarios[{index}]"
        _check_optional_id(item, prefix, errors)
        _check_required_fields(item, {"name": str, "description": str, "implications": list, "triggers": list}, prefix, errors)
        _check_string_list(item.get("implications", []), f"{prefix}.implications", errors)
        _check_string_list(item.get("triggers", []), f"{prefix}.triggers", errors)
    _check_string_list(data.get("counter_theses", []), "scenario_analysis.counter_theses", errors)
    _check_string_list(data.get("tracking_signals", []), "scenario_analysis.tracking_signals", errors)
    seen_ids: set[str] = set()
    for index, item in enumerate(_check_object_list(data.get("evidence", []), "scenario_analysis.evidence", errors)):
        prefix = f"scenario_analysis.evidence[{index}]"
        _check_required_fields(
            item,
            {"id": str, "title": str, "source_type": str, "date": str, "reliability": str, "claims": list},
            prefix,
            errors,
        )
        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in seen_ids:
                errors.append(f"{prefix}.id: duplicate evidence id '{item_id}'")
            seen_ids.add(item_id)
        date = item.get("date")
        if isinstance(date, str) and not _DATE_RE.match(date):
            errors.append(f"{prefix}.date: '{date}' is not in YYYY-MM-DD format")
        reliability = item.get("reliability")
        if isinstance(reliability, str) and reliability not in {"high", "medium", "low"}:
            errors.append(f"{prefix}.reliability: unknown value '{reliability}'")
        if "url" in item:
            _check_type(item["url"], str, f"{prefix}.url", errors)
        _check_string_list(item.get("claims", []), f"{prefix}.claims", errors)


def validate_stage_shape(stage: str, data: Any, ontology: dict[str, Any] | None = None) -> list[str]:
    if stage not in STAGE_FIELDS:
        return [f"unknown stage '{stage}'"]
    if not isinstance(data, dict):
        return [f"{stage}: expected a JSON object"]

    expected_fields = set(STAGE_FIELDS[stage])
    errors = [f"{stage}.{field}: missing" for field in sorted(expected_fields - set(data))]
    errors += [f"{stage}.{field}: unexpected field for this stage" for field in sorted(set(data) - expected_fields)]
    if errors:
        return errors

    if stage == "theme_definition":
        _validate_theme_definition_stage(data, ontology, errors)
    elif stage == "mechanism_analysis":
        _validate_mechanism_stage(data, errors)
    elif stage == "bottleneck_diagnosis":
        _validate_bottleneck_stage(data, ontology, errors)
    elif stage == "value_chain_map":
        _validate_value_chain_stage(data, ontology, errors)
    elif stage == "company_positioning":
        _validate_company_stage(data, ontology, errors)
    elif stage == "scenario_analysis":
        _validate_scenario_stage(data, errors)
    return errors
