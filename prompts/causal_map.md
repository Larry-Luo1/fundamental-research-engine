# Stage: causal_map

You are drafting the **causal map** stage: convert the mechanism narrative into
explicit, evidence-backed causal edges.

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

`causal_map` is a list of causal edge objects. Each edge has:

- `id`: stable kebab-case identifier for this causal edge.
- `source`: concise source node, such as a technical bottleneck, demand driver,
  policy action, supply constraint, customer behavior, or macro variable.
- `target`: concise target node, such as price, volume, margin, capex, adoption,
  company earnings driver, or risk variable.
- `relationship`: short label for the causal relationship.
- `transmission`: 1-2 sentences explaining how source transmits to target.
- `direction`: `positive`, `negative`, or `mixed`.
- `lag`: expected time lag, such as `0-2 quarters`, `1-2 years`, or `unknown`.
- `confidence`: `high`, `medium`, or `low`.
- `claim_ids`: non-empty list of claim ids supporting the edge, such as `E1.C1`.
  Use only claim ids that exist in the theme evidence. If claim extraction has
  created quote-verified candidate records in the evidence sidecar, `E1.Q1`
  style ids may be used for candidates.

## Rules

- Every edge must cite at least one claim id.
- Prefer a few high-signal causal edges over a dense graph.
- Make each edge directional; do not write generic association.
- Include lag even when uncertain; use `unknown` rather than omitting it.
- Do not invent claim ids. If evidence is missing, return fewer edges.

## Output contract

Return ONLY the JSON object for this stage. No prose, no markdown fences, no
commentary.
