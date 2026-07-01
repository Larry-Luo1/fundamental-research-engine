from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fre", description="Run a fundamental research pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run analysis for a theme config.")
    run.add_argument("theme", type=Path, help="Path to a theme JSON config.")
    run.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root containing knowledge/.")
    run.add_argument("--out", type=Path, default=None, help="Output directory. Defaults to runs/<as_of>-<theme_id>.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        output_dir = run_pipeline(args.theme, args.project_root, args.out)
        print(output_dir)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
