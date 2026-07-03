from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stages import STAGE_FIELDS, STAGE_ORDER


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def default_methodology_path(project_root: Path, theme_type: str) -> Path:
    return project_root / "knowledge" / "methodologies" / f"{theme_type}.json"


def render_stage_prompt(
    stage: str,
    prompts_dir: Path,
    completed_stages: dict[str, dict[str, Any]],
    ontology: dict[str, Any],
    methodology: dict[str, Any] | None = None,
) -> str:
    if stage not in STAGE_FIELDS:
        raise ValueError(f"unknown stage '{stage}'")

    template_path = prompts_dir / f"{stage}.md"
    if not template_path.exists():
        raise FileNotFoundError(f"no prompt template for stage '{stage}' at {template_path}")
    template = template_path.read_text(encoding="utf-8")

    upstream = {name: completed_stages[name] for name in STAGE_ORDER if name in completed_stages}

    substitutions = {
        "SCHEMA_FIELDS": ", ".join(STAGE_FIELDS[stage]),
        "UPSTREAM_CONTEXT_JSON": _json_block(upstream) if upstream else "{}",
        "ONTOLOGY_JSON": _json_block(ontology),
        "METHODOLOGY_JSON": _json_block(methodology) if methodology else "null",
    }

    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def render_quality_review_prompt(analysis: dict[str, Any], prompts_dir: Path) -> str:
    template_path = prompts_dir / "quality_review.md"
    if not template_path.exists():
        raise FileNotFoundError(f"no quality review template at {template_path}")
    template = template_path.read_text(encoding="utf-8")
    return template.replace("{{ANALYSIS_JSON}}", _json_block(analysis))


def render_claim_extraction_prompt(
    *,
    source_title: str,
    source_text: str,
    context: dict[str, Any],
    prompts_dir: Path,
    max_source_chars: int = 60_000,
) -> str:
    template_path = prompts_dir / "claim_extraction.md"
    if not template_path.exists():
        raise FileNotFoundError(f"no claim extraction template at {template_path}")
    template = template_path.read_text(encoding="utf-8")
    substitutions = {
        "SOURCE_TITLE": source_title or "Untitled source",
        "SOURCE_TEXT": source_text[:max_source_chars],
        "SOURCE_CONTEXT_JSON": _json_block(context),
    }
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def render_critique_prompt(
    stage: str,
    stage_data: dict[str, Any],
    prompts_dir: Path,
    completed_stages: dict[str, dict[str, Any]],
    ontology: dict[str, Any],
    methodology: dict[str, Any] | None = None,
) -> str:
    if stage not in STAGE_FIELDS:
        raise ValueError(f"unknown stage '{stage}'")

    template_path = prompts_dir / "critique.md"
    if not template_path.exists():
        raise FileNotFoundError(f"no critique template at {template_path}")
    template = template_path.read_text(encoding="utf-8")

    upstream = {
        name: completed_stages[name] for name in STAGE_ORDER if name in completed_stages and name != stage
    }

    substitutions = {
        "TARGET_STAGE": stage,
        "TARGET_STAGE_JSON": _json_block(stage_data),
        "UPSTREAM_CONTEXT_JSON": _json_block(upstream) if upstream else "{}",
        "ONTOLOGY_JSON": _json_block(ontology),
        "METHODOLOGY_JSON": _json_block(methodology) if methodology else "null",
    }

    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered
