# Prompt Templates

This folder holds the structured prompt templates for LLM-assisted pipeline
stages, one file per stage in `fundamental_research_engine.stages.STAGE_ORDER`:

- `theme_definition.md`
- `mechanism_analysis.md`
- `causal_map.md` (optional; explicit `--stage causal_map`)
- `bottleneck_diagnosis.md`
- `value_chain_map.md`
- `company_positioning.md`
- `scenario_analysis.md`

The contract is:

1. The engine provides a fixed schema, the ontology enums, the relevant
   methodology pack, and every already-completed upstream stage as context.
2. The model returns exactly one stage's JSON — nothing more.
3. The engine validates the output shape (`stages.validate_stage_shape`) and
   full referential integrity once every stage is present
   (`validation.validate_theme_dict`), then renders the final memo.

Model-specific free-form prose never becomes the source of record. Structured
JSON is written to `<stage>.json` first; prose (the memo) is rendered from it.

Templates use `{{PLACEHOLDER}}` tokens, substituted by
`fundamental_research_engine.prompts.render_stage_prompt`:

- `{{SCHEMA_FIELDS}}`: the top-level field names this stage must return.
- `{{UPSTREAM_CONTEXT_JSON}}`: JSON of every already-completed stage.
- `{{ONTOLOGY_JSON}}`: the full `knowledge/ontology.json` enum set.
- `{{METHODOLOGY_JSON}}`: the methodology pack for the theme's `theme_type`
  (`null` for the `theme_definition` stage, since `theme_type` is not chosen
  yet at that point).

Run `fre fill <theme_dir>` to render the next missing stage's prompt and
either send it to a model adapter directly or write it to disk for manual
completion. See the README's "LLM-Assisted Stage Drafting" section.
