# Stage: theme_definition

You are drafting the **theme definition** stage of a fundamental research
memo using this project's fixed pipeline:

theme definition -> mechanism chain -> bottleneck diagnosis -> value-chain map
-> company positioning -> scenario analysis -> memo generation.

## Your job

Define the theme boundary: what is included, what is excluded, and what would
be a false mapping. Classify the driver type. State the core question the
research is trying to answer and a falsifiable thesis.

Write all human-readable natural-language values in Simplified Chinese. Keep
JSON keys, ids, slugs, enum values, and dates in the required English/ISO form.

Every conclusion in this project answers four questions — keep them in mind
even though this stage only fills part of the answer:

1. What changed in technology, workload, regulation, supply, or demand?
2. Which scarce resource or bottleneck does that change create?
3. Which part of the value chain can capture value from the bottleneck?
4. What evidence would confirm or falsify the thesis?

## Required output schema

Return a single JSON object with exactly these fields: {{SCHEMA_FIELDS}}

- `id`: short kebab-case identifier, stable across reruns.
- `title`: human-readable title.
- `as_of`: date in `YYYY-MM-DD` format.
- `theme_type`: one of the values in `theme_types` in the ontology below.
- `domain`: a short domain slug (e.g. `ai`, `metals_mining`, `energy_storage`).
- `core_question`: the single question this research answers.
- `thesis`: 2-4 sentences, falsifiable, stating both the bull case and what
  would weaken it.
- `hype_stage`: one of `hype_stages` in the ontology below.
- `technology_readiness_level`: integer 1-9.
- `drivers`: list of short strings, each a specific structural driver (not a
  vague label like "AI stock").

## Ontology (valid enum values)

```json
{{ONTOLOGY_JSON}}
```

## Output contract

Return ONLY the JSON object for this stage. No prose, no markdown fences, no
commentary. The engine will validate the shape and reject anything else.
