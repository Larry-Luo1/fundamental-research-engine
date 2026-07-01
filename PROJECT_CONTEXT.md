# Project Context

This file is the handoff entry point for collaborators and for work resumed from another terminal. Update it whenever a meaningful design decision, implementation milestone, or next-step plan changes.

## Current Objective

Build a reusable, theme-agnostic fundamental research engine. The engine should support industry, theme, and trend analysis through fixed methodology, structured evidence, bottleneck/profit-pool scoring, company positioning, scenarios, and repeatable memo generation.

The project should not be limited to AI. AI is the first domain pack and first batch of sample themes.

## Repository

- Local path: `/home/xpeng/luol11/fundamental-research-engine`
- Remote: `git@github.com:Larry-Luo1/fundamental-research-engine.git`
- Branch: `main`

## Current Architecture

```text
configs/themes/       Concrete theme inputs.
knowledge/            Universal ontology, bottleneck scoring, methodology packs.
domains/              Domain-specific knowledge packs. AI is the first one.
prompts/              Placeholder for future LLM stage prompts.
src/                  Deterministic local pipeline.
runs/                 Generated run artifacts, ignored except .gitkeep.
reports/              Curated outputs, ignored except .gitkeep.
docs/                 Methodology notes.
tests/                Unit tests.
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

## How to Verify

```bash
cd /home/xpeng/luol11/fundamental-research-engine
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/hbm4.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/solid-state-battery.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/copper-supply-demand.json
```

Generated outputs go under `runs/` and are intentionally ignored by git.

## Next Recommended Work

1. Add schema validation for theme config files.
2. Split current monolithic theme input into stage outputs:
   - `theme_definition.json`
   - `mechanism_analysis.json`
   - `bottleneck_diagnosis.json`
   - `value_chain_map.json`
   - `company_positioning.json`
   - `scenario_analysis.json`
3. Add LLM prompt templates for each stage while keeping structured JSON as the source of record.
4. Add model adapter interface for GPT, Claude, and manual/offline mode.
5. Add run-to-run diff so repeated analyses show changes in evidence, score, scenarios, and thesis.

## Collaboration Rule

Before ending a meaningful work session:

1. Run tests when practical.
2. Update this file with current state and next steps.
3. Commit and push to `origin/main` unless there is a reason to keep work local.
4. Mention any known failing tests, unresolved assumptions, or uncommitted local artifacts.
