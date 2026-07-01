# Stage: scenario_analysis

You are drafting the final **scenario analysis** stage: bull/bear (and any
other relevant) scenarios, counter-theses, tracking signals, and the evidence
that backs the whole memo.

Evidence must be lawful, attributable, and dated (Mosaic-research style):
keep source type, date, and reliability attached to each item.
Counter-theses should be the strongest reasonable case against the thesis,
not strawmen. Tracking signals should be concrete and checkable at the next
update, not vague ("watch the market").

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

- `scenarios`: list of objects with `name` (e.g. `bull`, `bear`),
  `description`, `implications` (list), `triggers` (list of what would
  confirm this scenario is playing out).
- `counter_theses`: list of strings, each a specific reason the thesis could
  be wrong.
- `tracking_signals`: list of strings, each a concrete, checkable signal.
- `evidence`: list of objects with `id` (short stable id like `E1`), `title`,
  `source_type`, `date` (`YYYY-MM-DD`), `url` (optional), `reliability`
  (`high`/`medium`/`low`), `claims` (list of the specific claims this source
  supports).

If any bottleneck or company in the upstream context references an
`evidence_ids` value, make sure a matching `id` exists in this stage's
`evidence` list.

## Output contract

Return ONLY the JSON object for this stage. No prose, no markdown fences, no
commentary.
