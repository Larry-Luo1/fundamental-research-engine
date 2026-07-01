from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import AdapterError, ManualCompletionPending, get_adapter
from .diff import default_diff_dir, diff_analysis, find_runs_for_theme, resolve_analysis_path
from .evidence import build_evidence_audit, write_evidence_store
from .io import read_json, write_json, write_text
from .pipeline import default_ontology_path, load_and_validate_theme, run_pipeline
from .prompts import default_methodology_path, render_stage_prompt
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

        ontology = read_json(default_ontology_path(args.project_root))
        theme_type = existing.get("theme_definition", {}).get("theme_type")
        methodology = None
        if theme_type:
            methodology_path = default_methodology_path(args.project_root, theme_type)
            if methodology_path.exists():
                methodology = read_json(methodology_path)

        prompt = render_stage_prompt(
            stage, args.project_root / "prompts", existing, ontology, methodology
        )
        adapter = get_adapter(args.model, args.model_name)

        try:
            response = adapter.complete(prompt)
        except ManualCompletionPending as pending:
            prompt_path = theme_dir / f"{stage}.prompt.md"
            write_text(prompt_path, pending.prompt)
            print(f"manual mode: wrote prompt to {prompt_path}")
            print(f"run it through a model, save the JSON reply to {stage_path(theme_dir, stage)}, then rerun")
            return 0
        except AdapterError as exc:
            print(f"{stage}: model adapter failed: {exc}")
            return 1

        max_attempts = max(1, args.max_attempts)
        attempt = 1
        last_response = response
        last_errors: list[str] = []
        while True:
            try:
                data = _parse_model_json(last_response)
            except ValueError as exc:
                last_errors = [str(exc)]
            else:
                last_errors = validate_stage_shape(stage, data, ontology)
                if not last_errors:
                    break

            if attempt >= max_attempts:
                print(f"{stage}: model response has problems after {attempt} attempt(s):")
                for error in last_errors:
                    print(f"- {error}")
                return 1
            attempt += 1
            try:
                last_response = adapter.complete(_retry_prompt(prompt, last_errors))
            except AdapterError as exc:
                print(f"{stage}: model adapter failed on retry {attempt}: {exc}")
                return 1

        write_json(stage_path(theme_dir, stage), data)
        _write_fill_metadata(theme_dir, stage, args.model, args.model_name, prompt, last_response, attempt)
        print(stage_path(theme_dir, stage))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
