from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_analysis_path(path: Path) -> Path:
    return path / "analysis.json" if path.is_dir() else path


def find_runs_for_theme(project_root: Path, theme_id: str) -> list[tuple[str, Path]]:
    runs_dir = project_root / "runs"
    if not runs_dir.exists():
        return []
    suffix = f"-{theme_id}"
    matches: list[tuple[str, Path]] = []
    for entry in sorted(runs_dir.iterdir()):
        if not entry.is_dir() or not entry.name.endswith(suffix):
            continue
        as_of = entry.name[: -len(suffix)]
        if _DATE_RE.match(as_of) and (entry / "analysis.json").exists():
            matches.append((as_of, entry))
    matches.sort(key=lambda item: item[0])
    return matches


def default_diff_dir(project_root: Path, theme_id: str, from_as_of: str, to_as_of: str) -> Path:
    return project_root / "runs" / "diffs" / f"{theme_id}-{from_as_of}-to-{to_as_of}"


def _diff_scalar_fields(old: dict[str, Any], new: dict[str, Any], fields: list[str]) -> list[dict[str, Any]]:
    changes = []
    for field in fields:
        old_value = old.get(field)
        new_value = new.get(field)
        if old_value != new_value:
            changes.append({"field": field, "from": old_value, "to": new_value})
    return changes


def _diff_keyed_list(
    old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    key: str,
    track_fields: list[str] | None = None,
    display_field: str | None = None,
) -> dict[str, Any]:
    display_field = display_field or key

    def item_key(item: dict[str, Any]) -> Any:
        return item.get(key) or item.get(display_field)

    def display_name(item: dict[str, Any]) -> str:
        value = item.get(display_field) or item_key(item)
        return str(value)

    old_by_key = {item_key(item): item for item in old_items}
    new_by_key = {item_key(item): item for item in new_items}

    added = [item for k, item in new_by_key.items() if k not in old_by_key]
    removed = [item for k, item in old_by_key.items() if k not in new_by_key]

    changed = []
    for k, new_item in new_by_key.items():
        old_item = old_by_key.get(k)
        if old_item is None:
            continue
        fields = track_fields or sorted(set(old_item) | set(new_item))
        field_changes = [
            {"field": field, "from": old_item.get(field), "to": new_item.get(field)}
            for field in fields
            if old_item.get(field) != new_item.get(field)
        ]
        if field_changes:
            changed.append(
                {
                    key: k,
                    "display_name": display_name(new_item),
                    "previous_display_name": display_name(old_item),
                    "changes": field_changes,
                }
            )

    return {
        "key": key,
        "display_field": display_field,
        "added": sorted(added, key=lambda item: str(item_key(item))),
        "removed": sorted(removed, key=lambda item: str(item_key(item))),
        "changed": sorted(changed, key=lambda item: str(item[key])),
    }


def _diff_string_list(old_items: list[str], new_items: list[str]) -> dict[str, Any]:
    old_set, new_set = set(old_items), set(new_items)
    return {
        "added": sorted(new_set - old_set),
        "removed": sorted(old_set - new_set),
    }


def diff_analysis(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    theme_changes = _diff_scalar_fields(
        old["theme"],
        new["theme"],
        [
            "title",
            "core_question",
            "thesis",
            "mechanism",
            "hype_stage",
            "technology_readiness_level",
            "theme_type",
            "domain",
        ],
    )
    return {
        "theme_id": new["theme"]["id"],
        "from_as_of": old["theme"]["as_of"],
        "to_as_of": new["theme"]["as_of"],
        "theme_changes": theme_changes,
        "drivers": _diff_string_list(old["theme"].get("drivers", []), new["theme"].get("drivers", [])),
        "bottleneck_scores": _diff_keyed_list(
            old["bottleneck_scores"],
            new["bottleneck_scores"],
            "id",
            ["name", "score", "rating", "positive_score", "risk_penalty"],
            "name",
        ),
        "causal_map": _diff_keyed_list(
            old.get("causal_map", []),
            new.get("causal_map", []),
            "id",
            ["source", "target", "relationship", "direction", "lag", "confidence", "claim_ids"],
            "relationship",
        ),
        "segments": _diff_keyed_list(old["segments"], new["segments"], "id", display_field="name"),
        "profit_pools": _diff_keyed_list(old["profit_pools"], new["profit_pools"], "id", display_field="name"),
        "companies": _diff_keyed_list(old["companies"], new["companies"], "id", display_field="name"),
        "scenarios": _diff_keyed_list(old["scenarios"], new["scenarios"], "id", display_field="name"),
        "evidence": _diff_keyed_list(old["evidence"], new["evidence"], "id"),
        "counter_theses": _diff_string_list(old["counter_theses"], new["counter_theses"]),
        "tracking_signals": _diff_string_list(old["tracking_signals"], new["tracking_signals"]),
    }


def has_changes(report: dict[str, Any]) -> bool:
    if report["theme_changes"]:
        return True
    for key in ["drivers", "counter_theses", "tracking_signals"]:
        section = report[key]
        if section["added"] or section["removed"]:
            return True
    for key in ["bottleneck_scores", "causal_map", "segments", "profit_pools", "companies", "scenarios", "evidence"]:
        section = report[key]
        if section["added"] or section["removed"] or section["changed"]:
            return True
    return False
