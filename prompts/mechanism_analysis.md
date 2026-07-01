# Stage: mechanism_analysis

You are drafting the **mechanism chain** stage: explain how the theme's
driver transmits into orders, price, volume, margins, budgets, or adoption.

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

- `mechanism`: 3-6 sentences tracing the causal chain from the driver to the
  bottleneck or profit pool it creates. Be concrete about the transmission
  mechanism (e.g. "X increases Y which forces Z to expand capacity"), not a
  restatement of the thesis.

## Output contract

Return ONLY the JSON object for this stage. No prose, no markdown fences, no
commentary.
