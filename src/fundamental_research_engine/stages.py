from __future__ import annotations

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


def validate_stage_shape(stage: str, data: Any) -> list[str]:
    if stage not in STAGE_FIELDS:
        return [f"unknown stage '{stage}'"]
    if not isinstance(data, dict):
        return [f"{stage}: expected a JSON object"]

    expected_fields = set(STAGE_FIELDS[stage])
    errors = [f"{stage}.{field}: missing" for field in sorted(expected_fields - set(data))]
    errors += [f"{stage}.{field}: unexpected field for this stage" for field in sorted(set(data) - expected_fields)]
    return errors
