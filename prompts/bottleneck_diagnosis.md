# Stage: bottleneck_diagnosis

You are drafting the **bottleneck diagnosis** stage. Score bottlenecks on:

- demand growth speed
- capacity expansion difficulty
- technology substitution difficulty
- yield, material, or equipment constraint
- customer qualification lock-in
- supplier pricing power
- rapid supply release risk (a risk dimension: high values hurt the score)
- architecture bypass risk (a risk dimension: high values hurt the score)

Each dimension is scored 0-5 (0 = not present, 5 = critical). At least one
bottleneck is required.

## Upstream context (already decided, do not restate or contradict)

```json
{{UPSTREAM_CONTEXT_JSON}}
```

## Methodology guidance for this theme_type

```json
{{METHODOLOGY_JSON}}
```

## Required output schema

Return a single JSON object with exactly this field: {{SCHEMA_FIELDS}}

`bottlenecks` is a non-empty list of objects, each with:

- `id`: stable kebab-case identifier for this bottleneck; keep it unchanged
  across reruns even if the display name changes.
- `name`: short bottleneck name.
- `types`: list of values from `bottleneck_types` in the ontology below.
- `technical_reason`: 1-3 sentences on why this is structurally scarce.
- `scorecard`: object mapping each of the 8 dimensions above (snake_case,
  e.g. `demand_growth_speed`) to a number 0-5.
- `evidence_ids`: list of evidence ids this bottleneck's scoring relies on.
  Only use ids that will exist in the `scenario_analysis` stage's evidence
  list — if that stage does not exist yet, leave this empty; it can be
  filled in once evidence ids are known.

## Ontology (valid enum values)

```json
{{ONTOLOGY_JSON}}
```

## Output contract

Return ONLY the JSON object for this stage. No prose, no markdown fences, no
commentary.
