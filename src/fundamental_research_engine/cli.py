from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import AdapterError, ManualCompletionPending, get_adapter
from .critique import summarize_critique, validate_critique_shape
from .diff import default_diff_dir, diff_analysis, find_runs_for_theme, resolve_analysis_path
from .evidence import build_evidence_audit, write_evidence_store
from .io import read_json, write_json, write_text
from .pipeline import default_ontology_path, load_and_validate_theme, run_pipeline
from .prompts import default_methodology_path, render_critique_prompt, render_stage_prompt
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
    critique.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/ and prompts/.")

    return parser


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_model_json(response: str) -> dict[str, Any]:
    text = response.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates: list[str] = []
    if "```" in text:
        parts = text.split("```")
        candidates.extend(part.strip().removeprefix("json").strip() for part in parts[1::2])
    candidates.append(text)

    for candidate in candidates:
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
            raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
    raise ValueError("model response did not contain a valid JSON object")


def _retry_prompt(prompt: str, errors: list[str]) -> str:
    details = "\n".join(f"- {error}" for error in errors)
    return (
        f"{prompt}\n\n"
        "The previous response was rejected for these issues:\n"
        f"{details}\n\n"
        "Return only one corrected JSON object for the requested stage."
    )


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
class CompletionAttempt:
    data: dict[str, Any] | None
    response: str
    errors: list[str]
    attempts: int
    adapter_error: bool = False


def _complete_json_with_retry(
    adapter: Any,
    initial_response: str,
    prompt: str,
    validate: Any,
    max_attempts: int,
) -> CompletionAttempt:
    max_attempts = max(1, max_attempts)
    attempt = 1
    last_response = initial_response
    while True:
        try:
            data = _parse_model_json(last_response)
            errors = validate(data)
        except ValueError as exc:
            data = None
            errors = [str(exc)]

        if data is not None and not errors:
            return CompletionAttempt(data=data, response=last_response, errors=[], attempts=attempt)

        if attempt >= max_attempts:
            return CompletionAttempt(data=None, response=last_response, errors=errors, attempts=attempt)
        attempt += 1
        try:
            last_response = adapter.complete(_retry_prompt(prompt, errors))
        except AdapterError as exc:
            return CompletionAttempt(
                data=None, response=last_response, errors=[str(exc)], attempts=attempt, adapter_error=True
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
    adapter = get_adapter(model, model_name)

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

        result = _fill_stage(theme_dir, stage, args.project_root, args.model, args.model_name, args.max_attempts)
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
            result = _fill_stage(theme_dir, stage, args.project_root, args.model, args.model_name, args.max_attempts)
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
        adapter = get_adapter(args.model, args.model_name)

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

    parser.error(f"unknown command: {args.command}")
    return 2
