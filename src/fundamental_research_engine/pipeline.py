from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .evidence import build_evidence_audit
from .io import read_json, write_json, write_text
from .models import Theme, theme_from_dict
from .quality import build_causal_quality, build_grounding, build_quality_scorecard
from .render import render_memo
from .scoring import score_bottleneck
from .stages import load_theme_source
from .validation import ThemeValidationError, validate_theme_dict


def default_rules_path(project_root: Path) -> Path:
    return project_root / "knowledge" / "scoring_rules.json"


def default_ontology_path(project_root: Path) -> Path:
    return project_root / "knowledge" / "ontology.json"


def default_run_dir(project_root: Path, theme: Theme) -> Path:
    safe_id = theme.id.replace("/", "-").replace(" ", "-")
    return project_root / "runs" / f"{theme.as_of}-{safe_id}"


def default_claim_provenance_path(project_root: Path, theme_id: str) -> Path:
    return project_root / "data" / "evidence" / theme_id / "claims.json"


def load_claim_provenance(project_root: Path, theme_id: str) -> list[dict[str, Any]]:
    path = default_claim_provenance_path(project_root, theme_id)
    if not path.exists():
        return []
    payload = read_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return [item for item in payload["records"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def build_analysis(
    theme: Theme,
    rules: dict[str, Any],
    claim_provenance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_by_id = {item.id: item for item in theme.evidence}
    bottleneck_scores = [score_bottleneck(item, rules) for item in theme.bottlenecks]
    evidence_audit = build_evidence_audit(
        theme.evidence,
        {
            "bottleneck": theme.bottlenecks,
            "company": theme.companies,
        },
    )
    thesis_owner = SimpleNamespace(id="thesis", name="Thesis", evidence_ids=theme.thesis_evidence_ids)
    grounding = build_grounding(
        theme.evidence,
        {
            "bottleneck": theme.bottlenecks,
            "company": theme.companies,
            "thesis": [thesis_owner],
            "scenario": theme.scenarios,
        },
    )
    causal_quality = build_causal_quality(theme.causal_map, theme.evidence, claim_provenance)
    quality_scorecard = build_quality_scorecard(grounding, causal_quality=causal_quality)

    return {
        "generated_on": date.today().isoformat(),
        "theme": {
            "id": theme.id,
            "title": theme.title,
            "as_of": theme.as_of,
            "theme_type": theme.theme_type,
            "domain": theme.domain,
            "core_question": theme.core_question,
            "thesis": theme.thesis,
            "mechanism": theme.mechanism,
            "hype_stage": theme.hype_stage,
            "technology_readiness_level": theme.technology_readiness_level,
            "drivers": theme.drivers,
        },
        "bottleneck_scores": [asdict(item) for item in bottleneck_scores],
        "causal_map": [asdict(item) for item in theme.causal_map],
        "segments": [asdict(item) for item in theme.segments],
        "profit_pools": [asdict(item) for item in theme.profit_pools],
        "companies": [asdict(item) for item in theme.companies],
        "scenarios": [asdict(item) for item in theme.scenarios],
        "evidence": [asdict(item) for item in theme.evidence],
        "evidence_coverage": {
            item.name: [evidence_by_id[eid].title for eid in item.evidence_ids if eid in evidence_by_id]
            for item in [*theme.bottlenecks, *theme.companies]
        },
        "evidence_audit": evidence_audit,
        "quality_scorecard": quality_scorecard,
        "counter_theses": theme.counter_theses,
        "tracking_signals": theme.tracking_signals,
    }


def load_and_validate_theme(theme_path: Path, project_root: Path) -> Theme:
    raw_theme = load_theme_source(theme_path)
    ontology = read_json(default_ontology_path(project_root))
    errors = validate_theme_dict(raw_theme, ontology)
    if errors:
        raise ThemeValidationError(str(theme_path), errors)
    return theme_from_dict(raw_theme)


def run_pipeline(theme_path: Path, project_root: Path, out_dir: Path | None = None) -> Path:
    theme = load_and_validate_theme(theme_path, project_root)
    rules = read_json(default_rules_path(project_root))
    claim_provenance = load_claim_provenance(project_root, theme.id)
    analysis = build_analysis(theme, rules, claim_provenance=claim_provenance)
    output_dir = out_dir or default_run_dir(project_root, theme)
    write_json(output_dir / "analysis.json", analysis)
    write_text(output_dir / "memo.md", render_memo(analysis))
    return output_dir
