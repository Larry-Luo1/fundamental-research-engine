# Stage: value_chain_map

You are drafting the **value-chain map** and **profit-pool** stage. Map
upstream, midstream, downstream, enablers, substitutes, and risk hedges, then
identify which parts of the chain actually capture value (profit pools)
versus merely participate.

Use a Porter-style lens for bargaining power: supplier power, buyer power,
substitution, new entrants, rivalry.

## Upstream context (already decided, do not restate or contradict)

```json
{{UPSTREAM_CONTEXT_JSON}}
```

## Methodology guidance for this theme_type

```json
{{METHODOLOGY_JSON}}
```

## Required output schema

Return a single JSON object with exactly these fields: {{SCHEMA_FIELDS}}

`segments` is a list of objects, each with:

- `name`, `layer` (a short slug for this part of the chain), `role` (1
  sentence), `beneficiary_class` (one of `beneficiary_layers` in the ontology
  below), `representative_companies` (list of company names).

`profit_pools` is a list of objects, each with:

- `name`, `rationale` (why value concentrates here), `capture_quality` (one
  of `capture_qualities` in the ontology below), `beneficiaries` (list of
  company or segment names).

## Ontology (valid enum values)

```json
{{ONTOLOGY_JSON}}
```

## Output contract

Return ONLY the JSON object for this stage. No prose, no markdown fences, no
commentary.
