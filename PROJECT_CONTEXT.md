# Project Context

This file is the handoff entry point for collaborators and for work resumed from another terminal. Update it whenever a meaningful design decision, implementation milestone, or next-step plan changes.

## Current Objective

Build a reusable, theme-agnostic fundamental research engine. The engine should support industry, theme, and trend analysis through fixed methodology, structured evidence, bottleneck/profit-pool scoring, company positioning, scenarios, and repeatable memo generation.

The project should not be limited to AI. AI is the first domain pack and first batch of sample themes.

## Latest Session Summary (2026-07-01)

Closed out all 5 items that were in "Next Recommended Work": schema
validation, run-to-run diff, stage-based theme input, LLM prompt templates,
and a model adapter interface (manual/offline, OpenAI, Claude). Details and
verification are in "Implemented So Far" below. Net effect: a theme can now
be authored stage-by-stage, with each stage optionally drafted by a model via
`fre fill`, validated (`fre validate`), run (`fre run`), and diffed against a
prior run (`fre diff`) — all through the CLI, still with zero external
dependencies. See "Candidate follow-ups" under Next Recommended Work for
what's open next; none of those are agreed/scoped yet, so check with the
user before starting one.

## Repository

- Local path: `/home/xpeng/luol11/fundamental-research-engine`
- Remote: `git@github.com:Larry-Luo1/fundamental-research-engine.git`
- Branch: `main`

## Current Architecture

```text
configs/themes/        Monolithic theme inputs (one JSON file per theme).
configs/themes_staged/ Theme inputs split into per-stage JSON files.
knowledge/             Universal ontology, bottleneck scoring, methodology packs.
domains/               Domain-specific knowledge packs. AI is the first one.
prompts/               LLM-assisted stage prompt templates.
src/                   Deterministic local pipeline.
runs/                  Generated run artifacts, ignored except .gitkeep.
reports/               Curated outputs, ignored except .gitkeep.
docs/                  Methodology notes.
tests/                 Unit tests.
```

## Methodology Direction

Use a universal pipeline:

```text
theme definition
  -> driver classification
  -> mechanism chain
  -> maturity assessment
  -> bottleneck diagnosis
  -> value-chain mapping
  -> profit-pool analysis
  -> company positioning
  -> scenario analysis
  -> evidence and counter-thesis tracking
  -> memo generation
```

Supported theme types:

- `technology_adoption`
- `supply_demand_cycle`
- `policy_driven`
- `consumer_adoption`
- `healthcare_clinical`
- `macro_cycle`
- `geopolitics_security`

## Implemented So Far

- Initial deterministic CLI pipeline.
- Structured dataclasses for themes, bottlenecks, segments, profit pools, company positions, scenarios, and evidence.
- Bottleneck scoring from `knowledge/scoring_rules.json`.
- Markdown memo rendering.
- Methodology packs under `knowledge/methodologies/`.
- AI domain pack under `domains/ai/ontology.json`.
- Sample themes:
  - `hbm4`
  - `cowos`
  - `ai-liquid-cooling`
  - `solid-state-battery`
  - `copper-supply-demand`
- Theme config schema validation (`src/fundamental_research_engine/validation.py`):
  - checks required fields/types, `as_of` date format, TRL range, referential
    integrity of `evidence_ids`, and enum values against `knowledge/ontology.json`.
  - `run_pipeline` now validates before building a `Theme` and raises
    `ThemeValidationError` with a readable list of problems.
  - new `fre validate <theme.json>` CLI command runs validation only.
  - `knowledge/ontology.json` gained `hype_stages` and `capture_qualities` enums,
    and `bottleneck_types`/`company_positioning_labels` were extended to match
    values already used by the sample themes (`advanced_packaging_dependency`,
    `risk hedge`).
- Run-to-run diff engine (`src/fundamental_research_engine/diff.py`):
  - `diff_analysis(old, new)` compares two `analysis.json`-shaped dicts: theme
    scalar fields, drivers, bottleneck scores, segments, profit pools,
    companies, scenarios, evidence, counter-theses, and tracking signals. Each
    section reports `added`/`removed`/`changed` (or added/removed for plain
    string lists), with field-level before/after values.
  - `find_runs_for_theme(project_root, theme_id)` discovers prior runs by
    parsing `runs/<as_of>-<theme_id>/` directory names.
  - new `fre diff <theme_id>` CLI command auto-discovers and diffs the two
    most recent runs for a theme; `--from`/`--to` accept explicit paths to an
    `analysis.json` file or a run directory instead.
  - Output goes to `runs/diffs/<theme_id>-<from_as_of>-to-<to_as_of>/` as
    `diff.json` (structured) and `diff.md` (rendered via `render_diff` in
    `render.py`).
- Stage-based theme input (`src/fundamental_research_engine/stages.py`):
  - `STAGE_ORDER`/`STAGE_FIELDS` define which theme fields belong to each of
    the 6 stages (`theme_definition`, `mechanism_analysis`,
    `bottleneck_diagnosis`, `value_chain_map`, `company_positioning`,
    `scenario_analysis`).
  - `split_theme_dict`/`merge_stage_dicts` convert between one monolithic
    theme dict and a `{stage: dict}` mapping; round-trips losslessly.
  - `load_theme_source(path)` accepts either a single theme JSON file or a
    directory of per-stage JSON files; `run_pipeline` and `fre validate` both
    go through it, so `fre run <theme.json>` and `fre run <theme_dir>/`
    produce identical output.
  - new CLI commands: `fre split <theme.json> <theme_dir>` and
    `fre merge <theme_dir> <out.json>`.
  - `configs/themes_staged/hbm4/` is a worked example produced by splitting
    `configs/themes/hbm4.json`; verified to produce byte-identical
    `analysis.json` output to the monolithic file.
- LLM prompt templates (`prompts/*.md`, `src/fundamental_research_engine/prompts.py`):
  - One template per stage, each embedding: the stage's required JSON schema,
    the ontology enums, the methodology pack for the theme's `theme_type`
    (`null` for `theme_definition`, since `theme_type` isn't chosen yet), and
    every already-completed upstream stage as context.
  - `render_stage_prompt(stage, prompts_dir, completed_stages, ontology,
    methodology)` fills `{{PLACEHOLDER}}` tokens via plain string replacement
    (safe with embedded JSON, unlike `str.format`).
  - Contract stays "structured JSON is the source of record": templates
    instruct the model to return only that stage's JSON, no prose.
- Model adapter interface (`src/fundamental_research_engine/adapters.py`):
  - `ModelAdapter` protocol (`complete(prompt) -> str`); `ManualAdapter`
    (offline mode — raises `ManualCompletionPending(prompt)` so the CLI can
    write the prompt to disk for a human to run through any model UI);
    `OpenAIAdapter` and `ClaudeAdapter` (real HTTP calls via stdlib
    `urllib`, no new dependencies, API key from `OPENAI_API_KEY` /
    `ANTHROPIC_API_KEY` unless passed explicitly). Both accept an injectable
    `transport` callable so tests never hit the network.
  - `get_adapter(name, model_name)` factory; `model_name` is required for
    `openai`/`claude` (no baked-in default model id, to avoid asserting a
    model that may not exist).
  - new `fre fill <theme_dir>` CLI command: finds the first stage file
    missing from the directory (or `--stage`), builds its prompt, and either
    calls the chosen adapter or (manual mode, the default) writes
    `<stage>.prompt.md` and tells the user where to save the reply as
    `<stage>.json`. Validates the model's response shape
    (`stages.validate_stage_shape`) before writing it.
  - Verified end-to-end by hand: a toy theme was walked through all 6 stages
    via manual-mode `fre fill` (prompt written -> reply saved -> rerun), then
    `fre validate`/`fre run` succeeded on the resulting stage directory.

## How to Verify

```bash
cd /home/xpeng/luol11/fundamental-research-engine
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes/hbm4.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/hbm4.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/solid-state-battery.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/copper-supply-demand.json
PYTHONPATH=src python3 -m fundamental_research_engine diff hbm4
PYTHONPATH=src python3 -m fundamental_research_engine fill configs/themes_staged/hbm4
```

Generated outputs go under `runs/` and are intentionally ignored by git.

## Next Recommended Work

All 5 items originally listed here are done:

1. ~~Add schema validation for theme config files.~~ Done.
2. ~~Split current monolithic theme input into stage outputs.~~ Done.
3. ~~Add LLM prompt templates for each stage while keeping structured JSON as the source of record.~~ Done.
4. ~~Add model adapter interface for GPT, Claude, and manual/offline mode.~~ Done.
5. ~~Add run-to-run diff so repeated analyses show changes in evidence, score, scenarios, and thesis.~~ Done.

Candidate follow-ups (not yet scoped/agreed):

- Real evidence collection/storage into `data/raw_sources`, `data/normalized`,
  `data/evidence` (currently empty placeholders) — today all evidence is
  hand-authored in the `scenario_analysis` stage.
- A `fre run` mode that walks all 6 stages through a chosen model adapter in
  one command, instead of one `fre fill` call per stage.
- Migrate the remaining 4 sample themes (`cowos`, `ai-liquid-cooling`,
  `solid-state-battery`, `copper-supply-demand`) into `configs/themes_staged/`
  if the stage-directory format becomes the primary authoring path.

## Collaboration Rule

Before ending a meaningful work session:

1. Run tests when practical.
2. Update this file with current state and next steps.
3. Commit and push to `origin/main` unless there is a reason to keep work local.
4. Mention any known failing tests, unresolved assumptions, or uncommitted local artifacts.
