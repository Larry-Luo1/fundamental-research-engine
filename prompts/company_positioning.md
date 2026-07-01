# Stage: company_positioning

You are drafting the **company positioning** stage. For each company, state
its product/exposure, its position in the stack, a positioning label, the
quality of its exposure, its moat, and its risks.

Positioning labels come from `company_positioning_labels` in the ontology
below: reserve `core bottleneck owner` for the single best-positioned
company, not everyone in the segment.

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

`companies` is a list of objects, each with:

- `id`: stable kebab-case identifier for this company/exposure; keep it
  unchanged across reruns even if the display name changes.
- `name`, `product`, `stack_position`, `positioning_label` (one of
  `company_positioning_labels` in the ontology below), `exposure_quality`
  (short phrase), `moat` (list of strings), `risks` (list of strings),
  `evidence_ids` (list, may be empty if no evidence stage exists yet).

## Ontology (valid enum values)

```json
{{ONTOLOGY_JSON}}
```

## Output contract

Return ONLY the JSON object for this stage. No prose, no markdown fences, no
commentary.
