from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import AdapterError, ManualCompletionPending, get_adapter
from .calibration import build_calibration, register_predictions, resolve_prediction
from .claims import claim_texts, extract_claims, validate_claims_shape, verify_quotes
from .critique import summarize_critique, validate_critique_shape
from .diff import default_diff_dir, diff_analysis, find_runs_for_theme, resolve_analysis_path
from .corpus import build_corpus, default_fetch_text
from .edgar import filing_to_evidence, search_filings
from .evidence import build_evidence_audit, default_fetch, write_evidence_store
from .io import read_json, write_json, write_text
from .models import Evidence, Theme
from .llm_json import complete_json_with_retry as _complete_json_with_retry
from .pipeline import (
    build_analysis,
    default_ontology_path,
    default_rules_path,
    load_claim_provenance,
    load_and_validate_theme,
    run_pipeline,
)
from .prompts import (
    default_methodology_path,
    render_critique_prompt,
    render_quality_review_prompt,
    render_stage_prompt,
)
from .provenance import build_provenance_records, write_provenance_store
from .quality import build_quality_scorecard, validate_quality_review_shape
from .radar import build_radar, register_radar_predictions
from .render import render_diff
from .watch import (
    build_digest,
    render_digest_md,
    summarize_analysis_diff,
    theme_result,
    validate_watchlist,
)
from .stages import (
    OPTIONAL_STAGE_ORDER,
    STAGE_ORDER,
    load_theme_source,
    merge_stage_dicts,
    next_missing_stage,
    read_stage_dir_partial,
    stage_path,
    validate_stage_shape,
    write_theme_stage_dir,
)
from .validation import validate_theme_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fre", description="Run a fundamental research pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage_choices = [*STAGE_ORDER, *OPTIONAL_STAGE_ORDER]

    run = subparsers.add_parser("run", help="Run analysis for a theme config.")
    run.add_argument("theme", type=Path, help="Path to a theme JSON config.")
    run.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")
    run.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to runs/<as_of>-<theme_id>.")

    validate = subparsers.add_parser("validate", help="Validate a theme config without running the pipeline.")
    validate.add_argument("theme", type=Path, help="Path to a theme JSON config or a stage directory.")
    validate.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")

    audit = subparsers.add_parser("audit", help="Build an evidence audit for a theme config.")
    audit.add_argument("theme", type=Path, help="Path to a theme JSON config or a stage directory.")
    audit.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")
    audit.add_argument("--out", type=Path, default=None, help="Optional output path for evidence_audit JSON.")

    evidence_sync = subparsers.add_parser("evidence-sync", help="Sync theme evidence into the local evidence store.")
    evidence_sync.add_argument("theme", type=Path, help="Path to a theme JSON config or a stage directory.")
    evidence_sync.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")
    evidence_sync.add_argument(
        "--store-root",
        type=Path,
        default=None,
        help="Root containing data/raw_sources, data/normalized, and data/evidence. Defaults to --project-root.",
    )
    evidence_sync.add_argument(
        "--fetch-sources",
        action="store_true",
        help=(
            "Actually fetch each evidence item's url (http/https only, robots.txt-checked) instead of only "
            "snapshotting the theme config record. Falls back to the config snapshot per item on any failure."
        ),
    )

    split = subparsers.add_parser("split", help="Split a monolithic theme JSON into per-stage files.")
    split.add_argument("theme", type=Path, help="Path to a monolithic theme JSON config.")
    split.add_argument("theme_dir", type=Path, help="Output directory for the per-stage JSON files.")

    merge = subparsers.add_parser("merge", help="Merge a theme stage directory into one monolithic JSON file.")
    merge.add_argument("theme_dir", type=Path, help="Directory containing theme stage JSON files.")
    merge.add_argument("out", type=Path, help="Output path for the merged theme JSON file.")

    diff = subparsers.add_parser("diff", help="Diff two analysis runs for the same theme.")
    diff.add_argument(
        "theme_id",
        nargs="?",
        default=None,
        help="Theme id; auto-discovers its two most recent runs under runs/ when --from/--to are omitted.",
    )
    diff.add_argument("--from", dest="from_path", type=Path, default=None, help="Older analysis.json or run directory.")
    diff.add_argument("--to", dest="to_path", type=Path, default=None, help="Newer analysis.json or run directory.")
    diff.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing runs/.")
    diff.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to runs/diffs/<...>.")

    fill = subparsers.add_parser("fill", help="Draft the next missing stage of a theme directory with a model adapter.")
    fill.add_argument("theme_dir", type=Path, help="Directory containing (partial) theme stage JSON files.")
    fill.add_argument("--stage", choices=stage_choices, default=None, help="Stage to fill. Defaults to the first missing one.")
    fill.add_argument("--model", choices=["manual", "openai", "claude"], default="manual", help="Model adapter to use.")
    fill.add_argument("--model-name", default=None, help="Model name/id for the openai/claude adapters.")
    fill.add_argument("--max-attempts", type=int, default=2, help="Maximum model attempts when JSON parsing or validation fails.")
    fill.add_argument("--max-tokens", type=int, default=None, help="Max output tokens for the openai/claude adapters (defaults to the adapter's own default).")
    fill.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/ and prompts/.")

    draft = subparsers.add_parser(
        "draft",
        help="Draft theme stages with a model adapter; stops after each stage for review unless --auto.",
    )
    draft.add_argument("theme_dir", type=Path, help="Directory containing (partial) theme stage JSON files.")
    draft.add_argument("--stage", choices=stage_choices, default=None, help="Stage to draft. Defaults to the first missing one. Not usable with --auto.")
    draft.add_argument("--model", choices=["manual", "openai", "claude"], default="manual", help="Model adapter to use.")
    draft.add_argument("--model-name", default=None, help="Model name/id for the openai/claude adapters.")
    draft.add_argument("--max-attempts", type=int, default=2, help="Maximum model attempts per stage when JSON parsing or validation fails.")
    draft.add_argument("--max-tokens", type=int, default=None, help="Max output tokens for the openai/claude adapters (defaults to the adapter's own default).")
    draft.add_argument(
        "--auto",
        action="store_true",
        help="Walk every remaining stage automatically instead of stopping after one (requires --model openai or claude).",
    )
    draft.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/ and prompts/.")

    critique = subparsers.add_parser("critique", help="Adversarially review an already-drafted theme stage.")
    critique.add_argument("theme_dir", type=Path, help="Directory containing theme stage JSON files.")
    critique.add_argument("--stage", choices=stage_choices, required=True, help="Stage to critique; it must already be drafted.")
    critique.add_argument("--model", choices=["manual", "openai", "claude"], default="manual", help="Model adapter to use.")
    critique.add_argument("--model-name", default=None, help="Model name/id for the openai/claude adapters.")
    critique.add_argument("--max-attempts", type=int, default=2, help="Maximum model attempts when JSON parsing or validation fails.")
    critique.add_argument("--max-tokens", type=int, default=None, help="Max output tokens for the openai/claude adapters (defaults to the adapter's own default).")
    critique.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/ and prompts/.")

    qc = subparsers.add_parser("qc", help="Run the quality gate (grounding + adversarial review) for a theme.")
    qc.add_argument("theme", type=Path, help="Theme config (monolithic JSON or stage directory).")
    qc.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/ and prompts/.")
    qc.add_argument("--out", type=Path, default=None, help="Write qc.json here (defaults to stdout).")
    qc.add_argument("--grounding-only", action="store_true", help="Deterministic grounding + scorecard only; no model call.")
    qc.add_argument("--review", type=Path, default=None, help="Use a pre-authored review JSON instead of calling a model.")
    qc.add_argument("--model", choices=["manual", "openai", "claude"], default="manual", help="Model adapter for the adversarial review.")
    qc.add_argument("--model-name", default=None, help="Model name/id for the openai/claude adapters.")
    qc.add_argument("--max-attempts", type=int, default=2, help="Maximum model attempts when JSON parsing or validation fails.")
    qc.add_argument("--max-tokens", type=int, default=None, help="Max output tokens for the openai/claude adapters.")
    qc.add_argument("--strict", action="store_true", help="Exit non-zero if grounding_score < threshold or any open critical concern.")
    qc.add_argument("--grounding-threshold", type=float, default=0.5, help="Minimum grounding_score for --strict to pass.")
    qc.add_argument("--track-record", type=Path, default=None, help="Track record JSON for calibration (defaults to track_records/<theme_id>.json).")

    calibrate = subparsers.add_parser("calibrate", help="Register/resolve dated predictions and score calibration over time.")
    calibrate.add_argument("theme", type=Path, help="Theme config (monolithic JSON or stage directory).")
    calibrate.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")
    calibrate.add_argument("--track-record", type=Path, default=None, help="Track record JSON path (defaults to track_records/<theme_id>.json).")
    calibrate.add_argument("--register", action="store_true", help="Extract predictions from the theme and merge into the track record.")
    calibrate.add_argument("--resolve", metavar="KEY", default=None, help="Resolve the prediction with this key.")
    calibrate.add_argument("--outcome", choices=["true", "false"], default=None, help="Outcome for --resolve.")
    calibrate.add_argument("--probability", type=float, default=None, help="Probability you had assigned (0-1), recorded on --resolve so Brier can be scored.")
    calibrate.add_argument("--as-of", default=None, help="Resolution date (YYYY-MM-DD); defaults to today.")
    calibrate.add_argument("--show", action="store_true", help="Print predictions and calibration summary (default action).")

    sources = subparsers.add_parser("sources", help="Discover real primary sources.")
    sources_sub = sources.add_subparsers(dest="sources_command", required=True)
    search = sources_sub.add_parser("search", help="Full-text search SEC EDGAR filings (keyless).")
    search.add_argument("query", help="Full-text query, e.g. 'high bandwidth memory qualification'.")
    search.add_argument("--forms", default=None, help="Comma-separated form types, e.g. 10-K,10-Q,8-K.")
    search.add_argument("--from", dest="date_from", default=None, help="Filed on/after (YYYY-MM-DD).")
    search.add_argument("--to", dest="date_to", default=None, help="Filed on/before (YYYY-MM-DD).")
    search.add_argument("--limit", type=int, default=10, help="Max filings to return.")
    search.add_argument("--out", type=Path, default=None, help="Write evidence-shaped results here (defaults to stdout).")

    corpus_cmd = sources_sub.add_parser("corpus", help="Build a dated document corpus from EDGAR for the consensus proxy (gear C).")
    corpus_cmd.add_argument("query", help="BROAD theme query (e.g. 'artificial intelligence accelerator'), not a per-constraint term.")
    corpus_cmd.add_argument("--forms", default=None, help="Comma-separated form types, e.g. 10-K,10-Q,8-K.")
    corpus_cmd.add_argument("--from", dest="date_from", default=None, help="Filed on/after (YYYY-MM-DD).")
    corpus_cmd.add_argument("--to", dest="date_to", default=None, help="Filed on/before (YYYY-MM-DD).")
    corpus_cmd.add_argument("--limit", type=int, default=40, help="Max filings to collect.")
    corpus_cmd.add_argument("--fetch-text", action="store_true", help="Fetch each filing's full text (heavy; needed for a real signal). Off = titles only.")
    corpus_cmd.add_argument("--out", type=Path, default=None, help="Write corpus JSON here (defaults to stdout).")

    extract = subparsers.add_parser("extract-claims", help="Extract quote-verified claims from a source.")
    extract.add_argument("theme", type=Path, help="Theme config (monolithic JSON or stage directory).")
    extract.add_argument("--source", required=True, help="Evidence id or URL to extract claims from.")
    extract.add_argument("--source-text", type=Path, default=None, help="Use this local source text instead of fetching.")
    extract.add_argument("--claims", type=Path, default=None, help="Use a pre-authored extraction JSON instead of calling a model.")
    extract.add_argument("--model", choices=["manual", "openai", "claude"], default="manual", help="Model adapter for extraction.")
    extract.add_argument("--model-name", default=None, help="Model name/id for the openai/claude adapters.")
    extract.add_argument("--max-attempts", type=int, default=2, help="Maximum model attempts when JSON parsing or validation fails.")
    extract.add_argument("--max-tokens", type=int, default=None, help="Max output tokens for the openai/claude adapters.")
    extract.add_argument("--apply", action="store_true", help="Append verified claim text back to the matched evidence item.")
    extract.add_argument("--store", action="store_true", help="Write rich quote provenance into data/evidence/<theme>/claims.json.")
    extract.add_argument(
        "--store-root",
        type=Path,
        default=None,
        help="Root for the evidence store when --store is used. Defaults to --project-root.",
    )
    extract.add_argument("--out", type=Path, default=None, help="Write extraction report here (defaults to stdout).")
    extract.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/ and prompts/.")

    build_provenance = subparsers.add_parser(
        "build-provenance",
        help="Build quote-verified claim provenance from a curated spec.",
    )
    build_provenance.add_argument("theme", type=Path, help="Theme config (monolithic JSON or stage directory).")
    build_provenance.add_argument("spec", type=Path, help="JSON spec containing records with claim_id, quote, confidence, bears_on.")
    build_provenance.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")
    build_provenance.add_argument(
        "--store-root",
        type=Path,
        default=None,
        help="Root for data/evidence/<theme>/claims.json. Defaults to --project-root.",
    )
    build_provenance.add_argument("--out", type=Path, default=None, help="Write build report here (defaults to stdout).")

    radar = subparsers.add_parser("radar", help="Rank candidate constraints by headroom and flag migration (constraint radar).")
    radar.add_argument("theme", type=Path, help="Theme config (monolithic JSON or stage directory).")
    radar.add_argument("spec", type=Path, help="Radar spec JSON (driver + candidate constraints with growth rates).")
    radar.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")
    radar.add_argument("--state", type=Path, default=None, help="Radar state time series (defaults to radar_state/<theme_id>.json).")
    radar.add_argument("--no-persist", action="store_true", help="Do not append this run to the radar state series.")
    radar.add_argument("--corpus", type=Path, default=None, help="Dated document corpus JSON for the consensus proxy (gear C).")
    radar.add_argument("--track-record", type=Path, default=None, help="Radar prediction track record (defaults to radar_state/<theme_id>.predictions.json).")
    radar.add_argument("--register-predictions", action="store_true", help="Register migration calls as dated predictions for later Brier scoring (gear D).")
    radar.add_argument("--horizon", default="2 quarters", help="Prediction horizon phrase for registered migration calls.")
    radar.add_argument("--out", type=Path, default=None, help="Write radar report here (defaults to stdout).")

    watch = subparsers.add_parser("watch", help="Weekly monitoring loop over a watchlist -> gated digest (radar + consensus + calibration + run diff).")
    watch.add_argument("watchlist", type=Path, help="Watchlist JSON (themes with theme/radar_spec/optional corpus).")
    watch.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root; relative entry paths resolve against it.")
    watch.add_argument("--as-of", default=None, help="Digest date (defaults to today, UTC).")
    watch.add_argument("--out-dir", type=Path, default=None, help="Digest output dir (defaults to reports/watch/<as_of>/).")
    watch.add_argument("--horizon", default="2 quarters", help="Prediction horizon phrase for registered migration calls.")
    watch.add_argument("--no-persist", action="store_true", help="Do not append radar state per theme.")
    watch.add_argument("--no-register", action="store_true", help="Do not register migration predictions.")
    watch.add_argument("--no-diff", action="store_true", help="Skip the analysis run-to-run diff enrichment.")

    return parser


def default_radar_state_path(project_root: Path, theme_id: str) -> Path:
    safe_id = theme_id.replace("/", "-").replace(" ", "-")
    return project_root / "radar_state" / f"{safe_id}.json"


def default_radar_predictions_path(project_root: Path, theme_id: str) -> Path:
    safe_id = theme_id.replace("/", "-").replace(" ", "-")
    return project_root / "radar_state" / f"{safe_id}.predictions.json"


def _load_corpus(path: Path) -> list[dict]:
    data = read_json(path)
    documents = data.get("documents", data) if isinstance(data, dict) else data
    return documents if isinstance(documents, list) else []


def _resolve_watch_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def default_track_record_path(project_root: Path, theme_id: str) -> Path:
    safe_id = theme_id.replace("/", "-").replace(" ", "-")
    return project_root / "track_records" / f"{safe_id}.json"


def _safe_ref(value: str) -> str:
    safe = "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")
    return safe or "source"


def _find_evidence(theme: Theme, source_ref: str) -> Evidence | None:
    for item in theme.evidence:
        if item.id == source_ref or (item.url and item.url == source_ref):
            return item
    return None


def _claim_context(theme: Theme) -> dict[str, Any]:
    return {
        "theme": {
            "id": theme.id,
            "title": theme.title,
            "core_question": theme.core_question,
            "thesis": theme.thesis,
            "theme_type": theme.theme_type,
            "domain": theme.domain,
        },
        "owners": {
            "thesis": [{"id": "thesis", "name": "Thesis"}],
            "bottlenecks": [{"id": item.id, "name": item.name} for item in theme.bottlenecks],
            "companies": [{"id": item.id, "name": item.name} for item in theme.companies],
            "scenarios": [{"id": item.id, "name": item.name} for item in theme.scenarios],
        },
    }


def _source_payload(theme: Theme, source_ref: str, source_text_path: Path | None) -> tuple[Evidence | None, str, str, str]:
    evidence = _find_evidence(theme, source_ref)
    title = evidence.title if evidence else source_ref
    url = evidence.url if evidence else (source_ref if source_ref.startswith(("http://", "https://")) else "")

    if source_text_path is not None:
        return evidence, title, url, source_text_path.read_text(encoding="utf-8")

    if not url:
        raise ValueError(f"source '{source_ref}' has no URL; provide --source-text")

    result = default_fetch(url)
    if not result.ok or not result.text:
        detail = result.error or result.status
        raise ValueError(f"failed to fetch source '{source_ref}': {detail}")
    return evidence, title, url, result.text


def _normalize_claims_file_payload(candidate: Any) -> Any:
    """Accept raw model output or a prior extraction report as --claims input."""
    if not isinstance(candidate, dict):
        return candidate
    normalized = dict(candidate)
    if isinstance(normalized.get("claims"), list):
        normalized["claims"] = [
            {key: value for key, value in item.items() if key != "verified"}
            if isinstance(item, dict)
            else item
            for item in normalized["claims"]
        ]
    return normalized


def _apply_claim_texts(theme_path: Path, source_ref: str, texts: list[str], project_root: Path) -> None:
    if not texts:
        return

    ontology = read_json(default_ontology_path(project_root))
    if theme_path.is_dir():
        scenario_path = stage_path(theme_path, "scenario_analysis")
        data = read_json(scenario_path)
        evidence_items = data.get("evidence", [])
        target_path = scenario_path
    else:
        data = read_json(theme_path)
        evidence_items = data.get("evidence", [])
        target_path = theme_path

    matched = None
    for item in evidence_items:
        if isinstance(item, dict) and (item.get("id") == source_ref or item.get("url") == source_ref):
            matched = item
            break
    if matched is None:
        raise ValueError(f"--apply requires --source to match an existing evidence id or URL: {source_ref}")

    existing = [str(item) for item in matched.get("claims", [])]
    for text in texts:
        if text not in existing:
            existing.append(text)
    matched["claims"] = existing

    if theme_path.is_dir():
        stages = read_stage_dir_partial(theme_path)
        stages["scenario_analysis"] = data
        merged = merge_stage_dicts(stages)
    else:
        merged = data
    errors = validate_theme_dict(merged, ontology)
    if errors:
        raise ValueError("updated theme failed validation: " + "; ".join(errors))
    write_json(target_path, data)


def _store_owners(theme: Theme) -> dict[str, list[Any]]:
    return {
        "bottleneck": theme.bottlenecks,
        "company": theme.companies,
    }


def _rich_claims_for_store(
    theme: Theme,
    evidence: Evidence,
    claims: list[dict[str, Any]],
    *,
    source_title: str,
    source_url: str,
    source_text: str,
    model: str,
    model_name: str | None,
    attempts: int,
) -> list[dict[str, Any]]:
    extracted_at = datetime.now(timezone.utc).isoformat()
    source_sha256 = _sha256_text(source_text)
    records: list[dict[str, Any]] = []
    for claim in claims:
        text = str(claim.get("text", "")).strip()
        if not text:
            continue
        records.append(
            {
                "theme_id": theme.id,
                "evidence_id": evidence.id,
                "claim": text,
                "quote": claim.get("quote"),
                "confidence": claim.get("confidence"),
                "bears_on": [str(item) for item in claim.get("bears_on", [])],
                "verified": bool(claim.get("verified")),
                "source_type": evidence.source_type,
                "date": evidence.date,
                "reliability": evidence.reliability,
                "source_title": source_title,
                "source_url": source_url,
                "source_sha256": source_sha256,
                "extracted_at": extracted_at,
                "extraction_model": model,
                "extraction_model_name": model_name,
                "extraction_attempts": attempts,
            }
        )
    return records


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_fill_metadata(
    theme_dir: Path,
    stage: str,
    model: str,
    model_name: str | None,
    prompt: str,
    response: str,
    attempts: int,
) -> None:
    write_json(
        theme_dir / f"{stage}.meta.json",
        {
            "stage": stage,
            "model": model,
            "model_name": model_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "attempts": attempts,
            "prompt_sha256": _sha256_text(prompt),
            "response_sha256": _sha256_text(response),
            "response_chars": len(response),
        },
    )


@dataclass
class FillResult:
    status: str  # "written" | "manual_pending" | "invalid" | "adapter_error"
    stage: str
    path: Path | None = None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0


def _fill_stage(
    theme_dir: Path,
    stage: str,
    project_root: Path,
    model: str,
    model_name: str | None,
    max_attempts: int,
    max_tokens: int | None = None,
    prompt_prefix: str | None = None,
) -> FillResult:
    existing = read_stage_dir_partial(theme_dir)
    ontology = read_json(default_ontology_path(project_root))
    theme_type = existing.get("theme_definition", {}).get("theme_type")
    methodology = None
    if theme_type:
        methodology_path = default_methodology_path(project_root, theme_type)
        if methodology_path.exists():
            methodology = read_json(methodology_path)

    prompt = render_stage_prompt(stage, project_root / "prompts", existing, ontology, methodology)
    if prompt_prefix:
        prompt = f"{prompt_prefix}\n\n{prompt}"
    adapter = get_adapter(model, model_name, max_tokens)

    try:
        response = adapter.complete(prompt)
    except ManualCompletionPending as pending:
        prompt_path = theme_dir / f"{stage}.prompt.md"
        write_text(prompt_path, pending.prompt)
        return FillResult(status="manual_pending", stage=stage, path=prompt_path)
    except AdapterError as exc:
        return FillResult(status="adapter_error", stage=stage, errors=[str(exc)])

    completion = _complete_json_with_retry(
        adapter, response, prompt, lambda data: validate_stage_shape(stage, data, ontology), max_attempts
    )
    if completion.data is None:
        status = "adapter_error" if completion.adapter_error else "invalid"
        return FillResult(status=status, stage=stage, errors=completion.errors, attempts=completion.attempts)

    written_path = stage_path(theme_dir, stage)
    write_json(written_path, completion.data)
    _write_fill_metadata(theme_dir, stage, model, model_name, prompt, completion.response, completion.attempts)
    return FillResult(status="written", stage=stage, path=written_path, attempts=completion.attempts)


def _report_fill_result(theme_dir: Path, result: FillResult) -> int:
    if result.status == "manual_pending":
        print(f"manual mode: wrote prompt to {result.path}")
        print(f"run it through a model, save the JSON reply to {stage_path(theme_dir, result.stage)}, then rerun")
        return 0
    if result.status == "adapter_error":
        print(f"{result.stage}: model adapter failed: {result.errors[0]}")
        return 1
    if result.status == "invalid":
        print(f"{result.stage}: model response has problems after {result.attempts} attempt(s):")
        for error in result.errors:
            print(f"- {error}")
        return 1
    print(result.path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        output_dir = run_pipeline(args.theme, args.project_root, args.out)
        print(output_dir)
        return 0

    if args.command == "validate":
        ontology = read_json(default_ontology_path(args.project_root))
        errors = validate_theme_dict(load_theme_source(args.theme), ontology)
        if errors:
            print(f"{args.theme}: INVALID")
            for error in errors:
                print(f"- {error}")
            return 1
        print(f"{args.theme}: OK")
        return 0

    if args.command == "audit":
        theme = load_and_validate_theme(args.theme, args.project_root)
        report = build_evidence_audit(
            theme.evidence,
            {
                "bottleneck": theme.bottlenecks,
                "company": theme.companies,
            },
        )
        if args.out:
            write_json(args.out, report)
            print(args.out)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "evidence-sync":
        theme = load_and_validate_theme(args.theme, args.project_root)
        paths = write_evidence_store(
            theme.id,
            theme.evidence,
            {
                "bottleneck": theme.bottlenecks,
                "company": theme.companies,
            },
            args.store_root or args.project_root,
            fetch_sources=args.fetch_sources,
        )
        print(json.dumps(paths, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "split":
        write_theme_stage_dir(args.theme_dir, read_json(args.theme))
        print(args.theme_dir)
        return 0

    if args.command == "merge":
        stages = read_stage_dir_partial(args.theme_dir)
        write_json(args.out, merge_stage_dicts(stages))
        print(args.out)
        return 0

    if args.command == "diff":
        if args.from_path and args.to_path:
            old_analysis = read_json(resolve_analysis_path(args.from_path))
            new_analysis = read_json(resolve_analysis_path(args.to_path))
        elif args.theme_id:
            runs = find_runs_for_theme(args.project_root, args.theme_id)
            if len(runs) < 2:
                parser.error(
                    f"need at least 2 runs for theme '{args.theme_id}' under runs/, found {len(runs)}"
                )
            (_, from_dir), (_, to_dir) = runs[-2], runs[-1]
            old_analysis = read_json(from_dir / "analysis.json")
            new_analysis = read_json(to_dir / "analysis.json")
        else:
            parser.error("provide either a theme_id or both --from and --to")
            return 2

        report = diff_analysis(old_analysis, new_analysis)
        output_dir = args.out or default_diff_dir(
            args.project_root, report["theme_id"], report["from_as_of"], report["to_as_of"]
        )
        write_json(output_dir / "diff.json", report)
        write_text(output_dir / "diff.md", render_diff(report))
        print(output_dir)
        return 0

    if args.command == "fill":
        theme_dir = args.theme_dir
        theme_dir.mkdir(parents=True, exist_ok=True)
        existing = read_stage_dir_partial(theme_dir)

        stage = args.stage or next_missing_stage(existing)
        if stage is None:
            print("all stages already present")
            return 0
        if stage != STAGE_ORDER[0] and STAGE_ORDER[0] not in existing:
            parser.error(f"fill '{STAGE_ORDER[0]}' before filling '{stage}'")
            return 2

        result = _fill_stage(
            theme_dir, stage, args.project_root, args.model, args.model_name, args.max_attempts, args.max_tokens
        )
        return _report_fill_result(theme_dir, result)

    if args.command == "draft":
        theme_dir = args.theme_dir
        theme_dir.mkdir(parents=True, exist_ok=True)

        if args.auto and args.model == "manual":
            parser.error("--auto requires --model openai or --model claude (manual mode cannot proceed unattended)")
            return 2
        if args.auto and args.stage:
            parser.error("--auto walks all remaining stages; --stage cannot be combined with --auto")
            return 2

        existing = read_stage_dir_partial(theme_dir)
        stage = args.stage or next_missing_stage(existing)
        if stage is not None and stage != STAGE_ORDER[0] and STAGE_ORDER[0] not in existing:
            parser.error(f"fill '{STAGE_ORDER[0]}' before drafting '{stage}'")
            return 2

        while stage is not None:
            result = _fill_stage(
                theme_dir, stage, args.project_root, args.model, args.model_name, args.max_attempts, args.max_tokens
            )
            exit_code = _report_fill_result(theme_dir, result)
            if exit_code != 0 or result.status != "written":
                return exit_code
            if not args.auto:
                break
            existing = read_stage_dir_partial(theme_dir)
            stage = next_missing_stage(existing)

        existing = read_stage_dir_partial(theme_dir)
        remaining_stage = next_missing_stage(existing)
        if remaining_stage is not None:
            print(f"checkpoint: review the drafted stage, then rerun `fre draft {theme_dir}` to continue with '{remaining_stage}'")
            return 0

        ontology = read_json(default_ontology_path(args.project_root))
        errors = validate_theme_dict(merge_stage_dicts(existing), ontology)
        if errors:
            print(f"{theme_dir}: all stages present but validation failed:")
            for error in errors:
                print(f"- {error}")
            return 1

        output_dir = run_pipeline(theme_dir, args.project_root)
        print(f"all stages complete; wrote {output_dir}")
        return 0

    if args.command == "critique":
        theme_dir = args.theme_dir
        existing = read_stage_dir_partial(theme_dir)
        stage = args.stage
        if stage not in existing:
            parser.error(f"'{stage}' has not been drafted yet in {theme_dir}; run fill/draft first")
            return 2

        ontology = read_json(default_ontology_path(args.project_root))
        theme_type = existing.get("theme_definition", {}).get("theme_type")
        methodology = None
        if theme_type:
            methodology_path = default_methodology_path(args.project_root, theme_type)
            if methodology_path.exists():
                methodology = read_json(methodology_path)

        prompt = render_critique_prompt(
            stage, existing[stage], args.project_root / "prompts", existing, ontology, methodology
        )
        adapter = get_adapter(args.model, args.model_name, args.max_tokens)

        try:
            response = adapter.complete(prompt)
        except ManualCompletionPending as pending:
            prompt_path = theme_dir / f"{stage}.critique.prompt.md"
            write_text(prompt_path, pending.prompt)
            print(f"manual mode: wrote critique prompt to {prompt_path}")
            print(f"run it through a model, save the JSON reply to {theme_dir / f'{stage}.critique.json'}")
            return 0
        except AdapterError as exc:
            print(f"{stage}: model adapter failed: {exc}")
            return 1

        completion = _complete_json_with_retry(adapter, response, prompt, validate_critique_shape, args.max_attempts)
        if completion.data is None:
            print(f"{stage}: critique response has problems after {completion.attempts} attempt(s):")
            for error in completion.errors:
                print(f"- {error}")
            return 1

        critique_path = theme_dir / f"{stage}.critique.json"
        write_json(critique_path, completion.data)
        print(critique_path)
        print(summarize_critique(completion.data))
        return 0

    if args.command == "qc":
        theme = load_and_validate_theme(args.theme, args.project_root)
        rules = read_json(default_rules_path(args.project_root))
        claim_provenance = load_claim_provenance(args.project_root, theme.id)
        analysis = build_analysis(theme, rules, claim_provenance=claim_provenance)
        grounding = analysis["quality_scorecard"]["grounding"]
        causal_quality = analysis["quality_scorecard"].get("causal_quality")

        review = None
        if not args.grounding_only:
            if args.review is not None:
                review = read_json(args.review)
                errors = validate_quality_review_shape(review)
                if errors:
                    print(f"qc: review file {args.review} is invalid:")
                    for error in errors:
                        print(f"- {error}")
                    return 1
            else:
                prompt = render_quality_review_prompt(analysis, args.project_root / "prompts")
                adapter = get_adapter(args.model, args.model_name, args.max_tokens)
                try:
                    response = adapter.complete(prompt)
                except ManualCompletionPending as pending:
                    prompt_path = (args.out.parent if args.out else Path.cwd()) / f"{theme.id}.qc.prompt.md"
                    write_text(prompt_path, pending.prompt)
                    print(f"manual mode: wrote quality-review prompt to {prompt_path}")
                    print("run it through a model, save the JSON reply, then rerun with --review <file>")
                    return 0
                except AdapterError as exc:
                    print(f"qc: model adapter failed: {exc}")
                    return 1

                completion = _complete_json_with_retry(
                    adapter, response, prompt, validate_quality_review_shape, args.max_attempts
                )
                if completion.data is None:
                    print(f"qc: review response has problems after {completion.attempts} attempt(s):")
                    for error in completion.errors:
                        print(f"- {error}")
                    return 1
                review = completion.data

        calibration = None
        track_record_path = args.track_record or default_track_record_path(args.project_root, theme.id)
        if track_record_path.exists():
            calibration = build_calibration(read_json(track_record_path))

        scorecard = build_quality_scorecard(
            grounding,
            review=review,
            calibration=calibration,
            causal_quality=causal_quality,
        )
        report = {
            "theme_id": theme.id,
            "as_of": theme.as_of,
            "quality_scorecard": scorecard,
            "review": review,
        }
        if args.out is not None:
            write_json(args.out, report)
            print(args.out)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

        gs = scorecard["grounding_score"]
        open_critical = scorecard["disconfirmation"]["open_critical"]
        print(f"grounding_score={gs} open_critical={open_critical} flags={len(scorecard['flags'])}")
        if args.strict and (gs < args.grounding_threshold or open_critical > 0):
            print(f"quality gate FAILED (grounding_score {gs} < {args.grounding_threshold} or open_critical {open_critical} > 0)")
            return 1
        return 0

    if args.command == "calibrate":
        theme = load_and_validate_theme(args.theme, args.project_root)
        track_record_path = args.track_record or default_track_record_path(args.project_root, theme.id)
        record = read_json(track_record_path) if track_record_path.exists() else {"theme_id": theme.id, "predictions": []}

        if args.register:
            before = len(record.get("predictions", []))
            record = register_predictions(record, theme)
            write_json(track_record_path, record)
            added = len(record["predictions"]) - before
            print(f"{track_record_path}: registered {added} new prediction(s), {len(record['predictions'])} total")
            return 0

        if args.resolve is not None:
            if args.outcome is None:
                parser.error("--resolve requires --outcome true|false")
                return 2
            if args.probability is not None:
                for prediction in record.get("predictions", []):
                    if prediction["key"] == args.resolve:
                        prediction["probability"] = args.probability
            resolved_as_of = args.as_of or datetime.now(timezone.utc).date().isoformat()
            found = resolve_prediction(record, args.resolve, args.outcome == "true", resolved_as_of)
            if not found:
                print(f"calibrate: no prediction with key '{args.resolve}' in {track_record_path}")
                return 1
            write_json(track_record_path, record)
            print(f"{track_record_path}: resolved {args.resolve} -> outcome={args.outcome}")
            return 0

        # Default action: show.
        summary = build_calibration(record)
        listing = [
            {"key": item["key"], "kind": item["kind"], "resolved": item["resolved"], "outcome": item["outcome"], "statement": item["statement"]}
            for item in record.get("predictions", [])
        ]
        print(json.dumps({"calibration": summary, "predictions": listing}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "extract-claims":
        theme = load_and_validate_theme(args.theme, args.project_root)
        try:
            evidence, source_title, source_url, source_text = _source_payload(theme, args.source, args.source_text)
        except ValueError as exc:
            print(f"extract-claims: {exc}")
            return 1

        if args.claims is not None:
            candidate = _normalize_claims_file_payload(read_json(args.claims))
            errors = validate_claims_shape(candidate)
            if errors:
                print(f"extract-claims: claims file {args.claims} is invalid:")
                for error in errors:
                    print(f"- {error}")
                return 1
            kept, dropped = verify_quotes(candidate["claims"], source_text)
            extraction = {"claims": kept, "dropped_unverified": dropped, "attempts": 0}
        else:
            adapter = get_adapter(args.model, args.model_name, args.max_tokens)
            try:
                extraction = extract_claims(
                    source_text,
                    adapter,
                    context=_claim_context(theme),
                    prompts_dir=args.project_root / "prompts",
                    source_title=source_title,
                    max_attempts=args.max_attempts,
                )
            except ManualCompletionPending as pending:
                prompt_dir = args.out.parent if args.out else Path.cwd()
                prompt_path = prompt_dir / f"{theme.id}-{_safe_ref(args.source)}.claim_extraction.prompt.md"
                write_text(prompt_path, pending.prompt)
                print(f"manual mode: wrote claim-extraction prompt to {prompt_path}")
                print("run it through a model, save the JSON reply, then rerun with --claims <file>")
                return 0
            except (AdapterError, ValueError) as exc:
                print(f"extract-claims: {exc}")
                return 1

        report = {
            "theme_id": theme.id,
            "source": {
                "evidence_id": evidence.id if evidence else None,
                "title": source_title,
                "url": source_url,
            },
            "claims": extraction["claims"],
            "claim_texts": claim_texts(extraction["claims"]),
            "dropped_unverified": extraction["dropped_unverified"],
            "attempts": extraction["attempts"],
            "applied": False,
            "stored": False,
            "store": None,
        }

        if args.apply:
            try:
                _apply_claim_texts(args.theme, args.source, report["claim_texts"], args.project_root)
            except ValueError as exc:
                print(f"extract-claims: {exc}")
                return 1
            report["applied"] = True

        if args.store:
            if evidence is None:
                print("extract-claims: --store requires --source to match an existing evidence id or URL")
                return 1
            store_theme = load_and_validate_theme(args.theme, args.project_root) if args.apply else theme
            store_evidence = _find_evidence(store_theme, args.source)
            if store_evidence is None:
                print("extract-claims: --store could not resolve the source evidence after applying claims")
                return 1
            rich_claims = _rich_claims_for_store(
                store_theme,
                store_evidence,
                report["claims"],
                source_title=source_title,
                source_url=source_url,
                source_text=source_text,
                model=args.model,
                model_name=args.model_name,
                attempts=report["attempts"],
            )
            store_root = args.store_root or args.project_root
            rich_claims = [*load_claim_provenance(store_root, store_theme.id), *rich_claims]
            paths = write_evidence_store(
                store_theme.id,
                store_theme.evidence,
                _store_owners(store_theme),
                store_root,
                rich_claims=rich_claims,
            )
            report["stored"] = True
            report["store"] = paths

        if args.out is not None:
            write_json(args.out, report)
            print(args.out)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        print(
            f"verified_claims={len(report['claims'])} "
            f"dropped_unverified={report['dropped_unverified']} "
            f"applied={report['applied']} stored={report['stored']}"
        )
        return 0

    if args.command == "build-provenance":
        theme = load_and_validate_theme(args.theme, args.project_root)
        spec = read_json(args.spec)
        store_root = args.store_root or args.project_root

        def make_records(evidence: Evidence, claims: list[dict[str, Any]], source_text: str) -> list[dict[str, Any]]:
            return _rich_claims_for_store(
                theme,
                evidence,
                claims,
                source_title=evidence.title,
                source_url=evidence.url,
                source_text=source_text,
                model="curated",
                model_name=None,
                attempts=0,
            )

        result = build_provenance_records(theme, spec, spec_dir=args.spec.parent, make_record=make_records)
        if result.errors:
            print(f"build-provenance: spec {args.spec} has problems:")
            for error in result.errors:
                print(f"- {error}")
            return 1

        records = [*load_claim_provenance(store_root, theme.id), *result.records]
        paths = write_provenance_store(theme, records, _store_owners(theme), store_root)
        stored_records = load_claim_provenance(store_root, theme.id)
        report = {
            "theme_id": theme.id,
            "record_count": len(result.records),
            "stored_record_count": len(stored_records),
            "store": paths,
        }
        if args.out is not None:
            write_json(args.out, report)
            print(args.out)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        print(f"provenance_records={len(result.records)} stored={paths['claims_path']}")
        return 0

    if args.command == "sources":
        if args.sources_command == "search":
            forms = [f.strip() for f in args.forms.split(",") if f.strip()] if args.forms else None
            try:
                hits = search_filings(
                    args.query, forms=forms, date_from=args.date_from, date_to=args.date_to, limit=args.limit
                )
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
                print(f"sources search: EDGAR request failed: {exc}")
                return 1
            found = [filing_to_evidence(hit, evidence_id=f"S{index}") for index, hit in enumerate(hits, start=1)]
            report = {"query": args.query, "count": len(found), "sources": found}
            if args.out is not None:
                write_json(args.out, report)
                print(args.out)
            else:
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            print(f"found {len(found)} filing(s)")
            return 0
        if args.sources_command == "corpus":
            forms = [f.strip() for f in args.forms.split(",") if f.strip()] if args.forms else None
            try:
                corpus = build_corpus(
                    args.query,
                    forms=forms,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    limit=args.limit,
                    fetch_text=default_fetch_text if args.fetch_text else None,
                )
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
                print(f"sources corpus: EDGAR request failed: {exc}")
                return 1
            if args.out is not None:
                write_json(args.out, corpus)
                print(args.out)
            else:
                print(json.dumps(corpus, ensure_ascii=False, indent=2, sort_keys=True))
            print(f"corpus: {corpus['count']} document(s)")
            return 0
        parser.error(f"unknown sources command: {args.sources_command}")
        return 2

    if args.command == "radar":
        theme = load_and_validate_theme(args.theme, args.project_root)
        spec = read_json(args.spec)
        state_path = args.state or default_radar_state_path(args.project_root, theme.id)
        state = read_json(state_path) if state_path.exists() else {"theme_id": theme.id, "history": []}
        prev_entry = state["history"][-1] if state.get("history") else None
        corpus = _load_corpus(args.corpus) if args.corpus is not None else None

        radar = build_radar(theme, spec, prev_entry, corpus=corpus)
        if radar.get("errors"):
            print(f"radar: spec {args.spec} has problems:")
            for error in radar["errors"]:
                print(f"- {error}")
            return 1

        if not args.no_persist:
            state.setdefault("history", []).append(radar["state_entry"])
            write_json(state_path, state)

        # gear D: register migration calls as predictions, and score past calls.
        track_path = args.track_record or default_radar_predictions_path(args.project_root, theme.id)
        record = read_json(track_path) if track_path.exists() else {"theme_id": theme.id, "predictions": []}
        if args.register_predictions:
            before = len(record.get("predictions", []))
            record = register_radar_predictions(record, radar, horizon=args.horizon)
            write_json(track_path, record)
            radar["registered_predictions"] = len(record["predictions"]) - before
        if record.get("predictions"):
            radar["calibration"] = build_calibration(record)

        if args.out is not None:
            write_json(args.out, radar)
            print(args.out)
        else:
            print(json.dumps(radar, ensure_ascii=False, indent=2, sort_keys=True))

        migration = [a for a in radar["alerts"] if a["type"] == "constraint_migration_alert"]
        action = [a for a in radar["alerts"] if a.get("level") == "action"]
        pre = [a for a in migration if a.get("pre_consensus")]
        tightest = radar["ranking"][0] if radar["ranking"] else "n/a"
        print(f"tightest={tightest} migration_alerts={len(migration)} action={len(action)} pre_consensus={len(pre)}")
        return 0

    if args.command == "watch":
        watchlist = read_json(args.watchlist)
        errors = validate_watchlist(watchlist)
        if errors:
            print(f"watch: watchlist {args.watchlist} has problems:")
            for error in errors:
                print(f"- {error}")
            return 1

        root = args.project_root
        as_of = args.as_of or datetime.now(timezone.utc).date().isoformat()
        results = []
        for entry in watchlist["themes"]:
            theme_path = _resolve_watch_path(root, entry["theme"])
            hint = entry.get("theme_id") or str(theme_path)
            try:
                theme = load_and_validate_theme(theme_path, root)
                spec = read_json(_resolve_watch_path(root, entry["radar_spec"]))
                corpus = _load_corpus(_resolve_watch_path(root, entry["corpus"])) if entry.get("corpus") else None

                state_path = default_radar_state_path(root, theme.id)
                state = read_json(state_path) if state_path.exists() else {"theme_id": theme.id, "history": []}
                prev_entry = state["history"][-1] if state.get("history") else None

                radar = build_radar(theme, spec, prev_entry, corpus=corpus)
                if radar.get("errors"):
                    results.append({"theme_id": theme.id, "error": "; ".join(radar["errors"])})
                    continue

                if not args.no_persist:
                    state.setdefault("history", []).append(radar["state_entry"])
                    write_json(state_path, state)
                if not args.no_register:
                    track_path = default_radar_predictions_path(root, theme.id)
                    record = read_json(track_path) if track_path.exists() else {"theme_id": theme.id, "predictions": []}
                    record = register_radar_predictions(record, radar, horizon=args.horizon)
                    write_json(track_path, record)
                    radar["calibration"] = build_calibration(record)

                analysis_diff = None
                if not args.no_diff:
                    runs = sorted(find_runs_for_theme(root, theme.id), key=lambda item: item[0])
                    if len(runs) >= 2:
                        try:
                            old = read_json(resolve_analysis_path(runs[-2][1]))
                            new = read_json(resolve_analysis_path(runs[-1][1]))
                            analysis_diff = summarize_analysis_diff(diff_analysis(old, new))
                        except (OSError, KeyError, ValueError):
                            analysis_diff = None

                results.append(theme_result(radar, analysis_diff=analysis_diff))
            except Exception as exc:  # one bad theme must not sink the whole digest
                results.append({"theme_id": hint, "error": str(exc)})

        digest = build_digest(results, as_of=as_of, watchlist_name=watchlist.get("name"))
        out_dir = args.out_dir or (root / "reports" / "watch" / as_of)
        write_json(out_dir / "digest.json", digest)
        write_text(out_dir / "digest.md", render_digest_md(digest))

        summary = digest["summary"]
        print(f"{out_dir / 'digest.md'}")
        print(
            f"scanned={digest['themes_scanned']} flagged={summary['flagged']} "
            f"action={summary['action']} pre_consensus={summary['pre_consensus']} "
            f"quiet={summary['quiet']} errored={summary['errored']}"
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
