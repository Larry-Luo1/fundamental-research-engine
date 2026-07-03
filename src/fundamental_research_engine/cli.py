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
from .critique import summarize_critique, validate_critique_shape
from .diff import default_diff_dir, diff_analysis, find_runs_for_theme, resolve_analysis_path
from .edgar import filing_to_evidence, search_filings
from .evidence import build_evidence_audit, write_evidence_store
from .io import read_json, write_json, write_text
from .llm_json import complete_json_with_retry as _complete_json_with_retry
from .pipeline import (
    build_analysis,
    default_ontology_path,
    default_rules_path,
    load_and_validate_theme,
    run_pipeline,
)
from .prompts import (
    default_methodology_path,
    render_critique_prompt,
    render_quality_review_prompt,
    render_stage_prompt,
)
from .quality import build_quality_scorecard, validate_quality_review_shape
from .render import render_diff
from .stages import (
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
    fill.add_argument("--stage", choices=STAGE_ORDER, default=None, help="Stage to fill. Defaults to the first missing one.")
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
    draft.add_argument("--stage", choices=STAGE_ORDER, default=None, help="Stage to draft. Defaults to the first missing one. Not usable with --auto.")
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
    critique.add_argument("--stage", choices=STAGE_ORDER, required=True, help="Stage to critique; it must already be drafted.")
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

    return parser


def default_track_record_path(project_root: Path, theme_id: str) -> Path:
    safe_id = theme_id.replace("/", "-").replace(" ", "-")
    return project_root / "track_records" / f"{safe_id}.json"


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
        analysis = build_analysis(theme, rules)
        grounding = analysis["quality_scorecard"]["grounding"]

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

        scorecard = build_quality_scorecard(grounding, review=review, calibration=calibration)
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
        parser.error(f"unknown sources command: {args.sources_command}")
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2
