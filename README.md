# Fundamental Research Engine

A reusable research pipeline for industry, theme, and technology-trend fundamental analysis.

The project is designed to turn a research question into a repeatable chain:

```text
theme definition
  -> driver classification
  -> mechanism chain
  -> maturity assessment
  -> bottleneck diagnosis
  -> value-chain mapping
  -> profit-pool analysis
  -> company positioning
  -> evidence and counter-thesis tracking
  -> scenario analysis
  -> memo generation
  -> run-to-run diff
```

The first version started with AI infrastructure themes, but the core engine is theme-agnostic. AI, batteries, metals, healthcare, consumer, policy, macro, and geopolitics can be represented through domain packs and methodology packs. It intentionally avoids short-term price targets and detailed valuation.

## Web UI (browser front end)

An optional web layer lets you run the engine on one server and give everyone a
browser-based, guided workflow (describe a theme → the model drafts the 6 stages
→ pipeline runs → memo/scores/evidence render in the page, with per-stage
critique and refine). The core engine stays dependency-free; only the web layer
needs `fastapi`/`uvicorn`.

One-click deploy after `git clone` (Ubuntu/macOS `./deploy.sh` then `./run.sh`;
Windows `deploy.bat` then `run.bat`). See **`web/README.md`** for full setup,
`.env` configuration, and usage.

## Quick Start

Run the sample HBM4 analysis:

```bash
cd /home/xpeng/luol11/fundamental-research-engine
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/hbm4.json
```

Run all sample themes:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/hbm4.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/cowos.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/ai-liquid-cooling.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/solid-state-battery.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/copper-supply-demand.json
```

Outputs are written under `runs/<as_of>-<theme_id>/`:

- `analysis.json`: structured pipeline output
- `memo.md`: human-readable research memo

`analysis.json` includes an `evidence_audit` section with source inventory,
claim links, owner-level evidence coverage, missing evidence references, and a
coverage health score. The score is an audit signal, not a truth score for the
investment thesis.

Validate a theme config without running the pipeline:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes/hbm4.json
```

Build only the evidence audit for a theme:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine audit configs/themes/hbm4.json --out /tmp/hbm4-evidence-audit.json
```

Sync a theme's evidence into the local evidence store:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine evidence-sync configs/themes/hbm4.json
```

This writes deterministic local records under `data/`:

- `data/raw_sources/<theme_id>/<evidence_id>.json`: source snapshots from the theme config
- `data/normalized/<theme_id>/evidence.json`: normalized evidence records
- `data/evidence/<theme_id>/claims.json`: stable claim records such as `E1.C1`
- `data/evidence/<theme_id>/coverage.json`: owner-level evidence coverage
- `data/evidence/<theme_id>/audit.json`: full evidence audit report
- `data/evidence/<theme_id>/manifest.json`: generated file manifest

By default the raw source snapshot is just a copy of the evidence record
already in the theme config (`source_snapshot_type: "theme_config_record"`).
Add `--fetch-sources` to actually fetch each item's `url`:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine evidence-sync configs/themes/hbm4.json --fetch-sources
```

Fetching only happens for `http`/`https` URLs, checks `robots.txt` first and
skips (falling back to the config snapshot) if disallowed, and caps response
size and timeout. Any fetch failure — blocked by robots.txt, network error,
timeout — falls back to the config snapshot for that item rather than failing
the whole sync; `manifest.json`'s `fetch_results` records the outcome (and any
error) per evidence id, so you can see exactly what was actually retrieved
versus what's still only a hand-typed claim.

Once a theme has been run more than once (e.g. after updating its `as_of` date
and evidence), diff the two most recent runs to see what changed:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine diff hbm4
```

This compares theme fields, bottleneck scores, industry chain, profit pools,
company positioning, scenarios, evidence, counter-theses, and tracking signals,
and writes `runs/diffs/<theme_id>-<from_as_of>-to-<to_as_of>/diff.json` and
`diff.md`. Pass explicit `--from`/`--to` paths (to an `analysis.json` file or a
run directory) to diff arbitrary runs instead of auto-discovering the latest two.

## Stage-Based Theme Input

A theme can be authored as one monolithic JSON file (as above) or as a
directory of six per-stage JSON files, mirroring the universal pipeline:

- `theme_definition.json`: id, title, as_of, theme_type, domain, core_question, thesis, hype_stage, technology_readiness_level, drivers
- `mechanism_analysis.json`: mechanism
- `bottleneck_diagnosis.json`: bottlenecks
- `value_chain_map.json`: segments, profit_pools
- `company_positioning.json`: companies
- `scenario_analysis.json`: scenarios, counter_theses, tracking_signals, evidence

`run`, `validate`, and `diff` (via run directories) all accept either form.
`configs/themes_staged/hbm4/` is a worked example produced from
`configs/themes/hbm4.json` via:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine split configs/themes/hbm4.json configs/themes_staged/hbm4
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes_staged/hbm4
PYTHONPATH=src python3 -m fundamental_research_engine merge configs/themes_staged/hbm4 /tmp/hbm4-merged.json
```

Splitting a theme into stages is what makes LLM-assisted authoring possible:
each stage is a small, independently gradeable unit of work instead of one
large hand-written file. See the next section.

## LLM-Assisted Stage Drafting

Prompt templates for each stage live under `prompts/<stage>.md`. Each template
embeds the stage's required JSON schema, the relevant methodology pack
guidance for the theme's `theme_type`, and the already-completed upstream
stages as context, then instructs the model to return only that stage's JSON.

Use `fre fill` to draft the next missing stage of a theme directory with a
model adapter:

```bash
# Manual/offline mode (default): writes the prompt to <stage>.prompt.md for
# you to run through any model UI, then save the JSON reply as <stage>.json.
PYTHONPATH=src python3 -m fundamental_research_engine fill configs/themes_staged/hbm4

# Call a model directly (requires an API key in the environment).
PYTHONPATH=src python3 -m fundamental_research_engine fill configs/themes_staged/hbm4 \
  --model claude --model-name claude-sonnet-5
PYTHONPATH=src python3 -m fundamental_research_engine fill configs/themes_staged/hbm4 \
  --model openai --model-name gpt-4.1
```

The `claude`/`openai` adapters call the model with a sensible output-token
default (16000 for Claude — enough headroom for large stages like
`value_chain_map`/`company_positioning`). Override it per invocation with
`--max-tokens` on `fill`, `draft`, and `critique`:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine fill configs/themes_staged/hbm4 \
  --model claude --model-name claude-opus-4-8 --max-tokens 32000
```

`fre fill` picks the first stage file missing from the directory unless
`--stage` is given. Structured JSON stays the source of record: the model
never writes prose directly into a memo, only one stage's fixed-shape JSON,
which `fre validate`/`fre run` still check afterward. If the model's response
isn't clean JSON (e.g. it's wrapped in a markdown fence or has stray prose),
`fre fill` extracts the JSON object; if the shape is still wrong, it retries
with the validation errors appended to the prompt, up to `--max-attempts`
(default 2). Every accepted stage gets a `<stage>.meta.json` audit record
(model, attempts, prompt/response hashes, timestamp).

`fre draft` builds on `fre fill` to walk multiple stages in one command:

```bash
# Same as one `fre fill` call, but once every stage is present it also runs
# validate + run automatically and prints the memo path.
PYTHONPATH=src python3 -m fundamental_research_engine draft configs/themes_staged/hbm4 \
  --model claude --model-name claude-sonnet-5

# Unattended: walks every remaining stage back-to-back (no per-stage pause),
# then validates, runs, and prints the memo path. Requires a real adapter —
# manual mode can't proceed without a human, so --auto rejects it.
PYTHONPATH=src python3 -m fundamental_research_engine draft configs/themes_staged/hbm4 \
  --model claude --model-name claude-sonnet-5 --auto
```

Without `--auto`, `fre draft` is a checkpointed workflow: it drafts one stage,
then stops with a message telling you to review it before rerunning `fre
draft` for the next one. This is deliberate — for research content, a human
checkpoint after each stage catches problems before they compound into later
stages, rather than trusting a fully autonomous multi-step run.

To pressure-test an already-drafted stage instead of just accepting it,
`fre critique` runs a second, adversarial model pass over it:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine critique configs/themes_staged/hbm4 \
  --stage bottleneck_diagnosis --model claude --model-name claude-sonnet-5
```

The critique model is told to default to skepticism — unsupported scorecard
numbers, strawman counter-theses, vague tracking signals, and inconsistencies
with the upstream stages are all in scope. It writes `<stage>.critique.json`
(`concerns` with a severity, the specific field, the issue, and a suggested
fix; an `overall_assessment`; and a `recommendation` of `accept` or `revise`)
next to the stage file. This is a standalone check — it never blocks or
rewrites `fre fill`/`fre draft` output on its own; a human decides whether to
act on it.

## Quality Gate

`fre qc` scores the *research process*, not the thesis. It has a deterministic
half (grounding: is each bottleneck / company / the thesis / each scenario
backed by evidence, corroborated by independent sources, and how reliable are
they?) and an optional adversarial half (a model runs pre-mortem, steelman-bear,
cross-stage consistency, and unsupported-claim lenses):

```bash
# Deterministic only — no model, offline/CI-safe:
PYTHONPATH=src python3 -m fundamental_research_engine qc configs/themes/hbm4.json --grounding-only

# Full quality gate with an adversarial model pass:
PYTHONPATH=src python3 -m fundamental_research_engine qc configs/themes/hbm4.json \
  --model claude --model-name claude-opus-4-8 --out qc.json
```

The grounding scorecard is also embedded in every `fre run` (`analysis.json` +
a `Quality Scorecard` memo section). `qc` is non-blocking by default; `--strict`
exits non-zero when the grounding score is below `--grounding-threshold` or an
open critical concern exists. Optional `thesis_evidence_ids` (theme-level) and
per-scenario `evidence_ids` let the thesis and scenarios be graded too.

To keep quality honest *over time*, `fre calibrate` turns a theme's tracking
signals, counter-theses, and scenario triggers into dated predictions, lets you
resolve them as outcomes arrive, and scores calibration (resolution rate +
Brier):

```bash
PYTHONPATH=src python3 -m fundamental_research_engine calibrate configs/themes/hbm4.json --register
PYTHONPATH=src python3 -m fundamental_research_engine calibrate configs/themes/hbm4.json \
  --resolve <key> --outcome true --probability 0.7
PYTHONPATH=src python3 -m fundamental_research_engine qc configs/themes/hbm4.json --grounding-only \
  --track-record track_records/hbm4.json
```

## Methodology

The engine adapts several industry frameworks:

- Mosaic research: evidence-backed synthesis from multiple lawful sources.
- Gartner Hype Cycle: separates narrative temperature from deployment maturity.
- NASA TRL: scores technical readiness from lab concept to proven deployment.
- Porter Five Forces: judges value capture and bargaining power.
- Thematic investing: distinguishes structural trends from short-term fads.
- Wright's Law: reasons about cost decline and scale effects.

See `docs/methodology.md` for the working interpretation used in this project.

## Theme Types

The engine currently recognizes these methodology packs:

- `technology_adoption`
- `supply_demand_cycle`
- `policy_driven`
- `consumer_adoption`
- `healthcare_clinical`
- `macro_cycle`
- `geopolitics_security`

## Repository Layout

```text
configs/themes/         Monolithic theme inputs (one JSON file per theme).
configs/themes_staged/  Theme inputs split into per-stage JSON files.
knowledge/              Ontology, scoring rules, and methodology packs.
domains/                Domain-specific knowledge packs.
prompts/                LLM-assisted stage prompt templates.
src/                    Pipeline implementation, diff, validation, and evidence audit.
data/                   Future source snapshots and normalized evidence.
runs/                   Generated run artifacts.
reports/                Curated report outputs.
docs/                   Methodology and design notes.
tests/                  Unit tests.
```

## Current Scope

The first milestone is a deterministic local pipeline:

1. Read a theme config.
2. Compute bottleneck strength from a fixed scorecard.
3. Classify value-chain segments, profit pools, and company exposure.
4. Generate a memo with thesis, evidence, scenarios, risks, and tracking signals.

Later milestones can add source collectors, document parsers, a local evidence database, model adapters, structured prompt stages, and run-to-run change detection.

## Collaboration Handoff

Read `PROJECT_CONTEXT.md` before starting work in a new terminal or handing the project to another collaborator. Keep it updated whenever a meaningful design decision, milestone, or next-step change occurs.
