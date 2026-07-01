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

Validate a theme config without running the pipeline:

```bash
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes/hbm4.json
```

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

`fre fill` picks the first stage file missing from the directory unless
`--stage` is given. Structured JSON stays the source of record: the model
never writes prose directly into a memo, only one stage's fixed-shape JSON,
which `fre validate`/`fre run` still check afterward.

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
src/                    Pipeline implementation.
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
