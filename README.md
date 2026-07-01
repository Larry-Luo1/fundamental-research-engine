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
configs/themes/     Theme inputs.
knowledge/          Ontology, scoring rules, and methodology packs.
domains/            Domain-specific knowledge packs.
prompts/            Future LLM-assisted stage prompts.
src/                Pipeline implementation.
data/               Future source snapshots and normalized evidence.
runs/               Generated run artifacts.
reports/            Curated report outputs.
docs/               Methodology and design notes.
tests/              Unit tests.
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
