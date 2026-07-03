# Claim Extraction

Extract atomic, checkable claims from the source text for the research theme.
Use only information that appears in the source text. Every claim must include
a verbatim quote copied from the source text.

## Research Context

```json
{{SOURCE_CONTEXT_JSON}}
```

## Source Title

{{SOURCE_TITLE}}

## Source Text

```text
{{SOURCE_TEXT}}
```

## Output Schema

Return one JSON object with exactly this field: `claims`.

`claims` is a list of objects. Each object has:

- `text`: one atomic, checkable claim.
- `quote`: a verbatim source-text excerpt supporting the claim. Do not use ellipses.
- `confidence`: `high`, `medium`, or `low`.
- `bears_on`: list of owner ids from the research context, such as bottleneck,
  company, scenario ids, or `thesis`.

## Rules

- Do not infer beyond the source text.
- Do not cite a quote unless it appears verbatim in the source text.
- Prefer fewer high-quality claims over broad summaries.
- Return `{"claims": []}` when the source text does not support relevant claims.
- Return only JSON. No prose, markdown fences, or commentary.
