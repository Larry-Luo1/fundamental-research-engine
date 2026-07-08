# Project Context

This file is the handoff entry point for collaborators and for work resumed from another terminal. Update it whenever a meaningful design decision, implementation milestone, or next-step plan changes.

## Current Objective

Build a reusable, theme-agnostic fundamental research engine. The engine should support industry, theme, and trend analysis through fixed methodology, structured evidence, bottleneck/profit-pool scoring, company positioning, scenarios, and repeatable memo generation.

The project should not be limited to AI. AI is the first domain pack and first batch of sample themes.

## Latest Session Summary (2026-07-01)

Closed out all 5 items that were in "Next Recommended Work": schema
validation, run-to-run diff, stage-based theme input, LLM prompt templates,
and a model adapter interface (manual/offline, OpenAI, Claude). Details and
verification are in "Implemented So Far" below. Net effect: a theme can now
be authored stage-by-stage, with each stage optionally drafted by a model via
`fre fill`, validated (`fre validate`), run (`fre run`), and diffed against a
prior run (`fre diff`) — all through the CLI, still with zero external
dependencies. See "Candidate follow-ups" under Next Recommended Work for
what's open next; none of those are agreed/scoped yet, so check with the
user before starting one.

## Repository

- Local path: `/home/xpeng/luol11/fundamental-research-engine`
- Remote: `git@github.com:Larry-Luo1/fundamental-research-engine.git`
- Branch: `main`

## Current Architecture

```text
configs/themes/        Monolithic theme inputs (one JSON file per theme).
configs/themes_staged/ Theme inputs split into per-stage JSON files.
knowledge/             Universal ontology, bottleneck scoring, methodology packs.
domains/               Domain-specific knowledge packs. AI is the first one.
prompts/               LLM-assisted stage prompt templates.
src/                   Deterministic local pipeline.
runs/                  Generated run artifacts, ignored except .gitkeep.
reports/               Curated outputs, ignored except .gitkeep.
docs/                  Methodology notes.
tests/                 Unit tests.
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
- Theme config schema validation (`src/fundamental_research_engine/validation.py`):
  - checks required fields/types, `as_of` date format, TRL range, referential
    integrity of `evidence_ids`, and enum values against `knowledge/ontology.json`.
  - `run_pipeline` now validates before building a `Theme` and raises
    `ThemeValidationError` with a readable list of problems.
  - new `fre validate <theme.json>` CLI command runs validation only.
  - `knowledge/ontology.json` gained `hype_stages` and `capture_qualities` enums,
    and `bottleneck_types`/`company_positioning_labels` were extended to match
    values already used by the sample themes (`advanced_packaging_dependency`,
    `risk hedge`).
- Run-to-run diff engine (`src/fundamental_research_engine/diff.py`):
  - `diff_analysis(old, new)` compares two `analysis.json`-shaped dicts: theme
    scalar fields, drivers, bottleneck scores, segments, profit pools,
    companies, scenarios, evidence, counter-theses, and tracking signals. Each
    section reports `added`/`removed`/`changed` (or added/removed for plain
    string lists), with field-level before/after values.
  - `find_runs_for_theme(project_root, theme_id)` discovers prior runs by
    parsing `runs/<as_of>-<theme_id>/` directory names.
  - new `fre diff <theme_id>` CLI command auto-discovers and diffs the two
    most recent runs for a theme; `--from`/`--to` accept explicit paths to an
    `analysis.json` file or a run directory instead.
  - Output goes to `runs/diffs/<theme_id>-<from_as_of>-to-<to_as_of>/` as
    `diff.json` (structured) and `diff.md` (rendered via `render_diff` in
    `render.py`).
- Stage-based theme input (`src/fundamental_research_engine/stages.py`):
  - `STAGE_ORDER`/`STAGE_FIELDS` define which theme fields belong to each of
    the 6 stages (`theme_definition`, `mechanism_analysis`,
    `bottleneck_diagnosis`, `value_chain_map`, `company_positioning`,
    `scenario_analysis`).
  - `split_theme_dict`/`merge_stage_dicts` convert between one monolithic
    theme dict and a `{stage: dict}` mapping; round-trips losslessly.
  - `load_theme_source(path)` accepts either a single theme JSON file or a
    directory of per-stage JSON files; `run_pipeline` and `fre validate` both
    go through it, so `fre run <theme.json>` and `fre run <theme_dir>/`
    produce identical output.
  - new CLI commands: `fre split <theme.json> <theme_dir>` and
    `fre merge <theme_dir> <out.json>`.
  - `configs/themes_staged/hbm4/` is a worked example produced by splitting
    `configs/themes/hbm4.json`; verified to produce byte-identical
    `analysis.json` output to the monolithic file.
- LLM prompt templates (`prompts/*.md`, `src/fundamental_research_engine/prompts.py`):
  - One template per stage, each embedding: the stage's required JSON schema,
    the ontology enums, the methodology pack for the theme's `theme_type`
    (`null` for `theme_definition`, since `theme_type` isn't chosen yet), and
    every already-completed upstream stage as context.
  - `render_stage_prompt(stage, prompts_dir, completed_stages, ontology,
    methodology)` fills `{{PLACEHOLDER}}` tokens via plain string replacement
    (safe with embedded JSON, unlike `str.format`).
  - Contract stays "structured JSON is the source of record": templates
    instruct the model to return only that stage's JSON, no prose.
- Model adapter interface (`src/fundamental_research_engine/adapters.py`):
  - `ModelAdapter` protocol (`complete(prompt) -> str`); `ManualAdapter`
    (offline mode — raises `ManualCompletionPending(prompt)` so the CLI can
    write the prompt to disk for a human to run through any model UI);
    `OpenAIAdapter` and `ClaudeAdapter` (real HTTP calls via stdlib
    `urllib`, no new dependencies, API key from `OPENAI_API_KEY` /
    `ANTHROPIC_API_KEY` unless passed explicitly). Both accept an injectable
    `transport` callable so tests never hit the network.
  - `get_adapter(name, model_name)` factory; `model_name` is required for
    `openai`/`claude` (no baked-in default model id, to avoid asserting a
    model that may not exist).
  - new `fre fill <theme_dir>` CLI command: finds the first stage file
    missing from the directory (or `--stage`), builds its prompt, and either
    calls the chosen adapter or (manual mode, the default) writes
    `<stage>.prompt.md` and tells the user where to save the reply as
    `<stage>.json`. Validates the model's response shape
    (`stages.validate_stage_shape`) before writing it.
  - Verified end-to-end by hand: a toy theme was walked through all 6 stages
    via manual-mode `fre fill` (prompt written -> reply saved -> rerun), then
    `fre validate`/`fre run` succeeded on the resulting stage directory.

## How to Verify

```bash
cd /home/xpeng/luol11/fundamental-research-engine
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes/hbm4.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/hbm4.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/solid-state-battery.json
PYTHONPATH=src python3 -m fundamental_research_engine run configs/themes/copper-supply-demand.json
PYTHONPATH=src python3 -m fundamental_research_engine diff hbm4
PYTHONPATH=src python3 -m fundamental_research_engine fill configs/themes_staged/hbm4
```

Generated outputs go under `runs/` and are intentionally ignored by git.

## Next Recommended Work

All 5 items originally listed here are done:

1. ~~Add schema validation for theme config files.~~ Done.
2. ~~Split current monolithic theme input into stage outputs.~~ Done.
3. ~~Add LLM prompt templates for each stage while keeping structured JSON as the source of record.~~ Done.
4. ~~Add model adapter interface for GPT, Claude, and manual/offline mode.~~ Done.
5. ~~Add run-to-run diff so repeated analyses show changes in evidence, score, scenarios, and thesis.~~ Done.

Candidate follow-ups (not yet scoped/agreed):

- Real evidence collection/storage into `data/raw_sources`, `data/normalized`,
  `data/evidence` (currently empty placeholders) — today all evidence is
  hand-authored in the `scenario_analysis` stage.
- A `fre run` mode that walks all 6 stages through a chosen model adapter in
  one command, instead of one `fre fill` call per stage.
- Migrate the remaining 4 sample themes (`cowos`, `ai-liquid-cooling`,
  `solid-state-battery`, `copper-supply-demand`) into `configs/themes_staged/`
  if the stage-directory format becomes the primary authoring path.

## Follow-Up Session Update (2026-07-01)

Started the next hardening pass after reviewing the Claude-authored commit:

- Strengthened `stages.validate_stage_shape` from top-level field checks into
  nested stage contract validation. It now checks scorecard dimensions,
  object/list element types, evidence quality fields, duplicate evidence ids,
  date formats, and ontology-backed enum values when ontology is provided.
- Strengthened full `validate_theme_dict` so monolithic theme files receive the
  same stricter contract for bottlenecks, segments, profit pools, companies,
  scenarios, evidence, and string-list fields.
- Made `fre fill` more robust for real model usage:
  - extracts JSON from plain JSON, fenced markdown JSON, or prose containing a
    JSON object;
  - retries failed model output with validation errors included in the retry
    prompt;
  - adds `--max-attempts`;
  - writes `<stage>.meta.json` with model, model name, attempts, timestamp,
    prompt hash, response hash, and response size.
- Added tests for nested stage validation, fenced JSON parsing, retry behavior,
  and metadata emission.

Verification:

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes/*.json
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes_staged/hbm4
```

Current result: 61 tests pass, and all sample themes validate.

Next recommended implementation steps:

- Introduce an evidence subsystem with source snapshots, normalized evidence,
  claim-to-evidence links, and evidence coverage scoring.
- Add a model generation/audit metadata layer to `fre run`, not only `fre fill`.
- Add a `fre draft`/`fre run-all` workflow that walks stages in order while
  preserving human review gates.
- Add CI checks for tests, sample validation, prompt rendering, and a golden
  memo snapshot.

## Stable ID / Diff Update (2026-07-01)

Implemented the next recommended step: stable ids for research objects and
id-aware diffs.

- Added optional stable `id` fields to bottlenecks, value-chain segments,
  profit pools, company positions, and scenarios. Existing configs without ids
  remain backward-compatible by falling back to `name` when loading models.
- Added stable ids to all sample monolithic themes and to
  `configs/themes_staged/hbm4/`.
- Propagated bottleneck ids into `BottleneckScore` so generated `analysis.json`
  keeps stable identity after scoring.
- Updated `fre diff` internals to match these objects by `id` first and fall
  back to display name only for legacy analyses without ids. Rename changes now
  show as field changes instead of add/remove churn.
- Updated diff markdown rendering to show human-readable labels plus ids, e.g.
  `SK hynix [co-sk-hynix]`.
- Updated stage prompt templates so future model-authored objects include
  stable kebab-case ids.
- Added tests covering id propagation, duplicate-id validation, and rename
  handling in diff.

Verification:

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes/*.json
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes_staged/hbm4
```

Current result: 63 tests pass, all sample themes validate, and a smoke run of
`configs/themes/hbm4.json` emits ids in bottleneck scores, companies, and
scenarios.

## Evidence Audit Update (2026-07-02)

Implemented the first evidence subsystem slice. This is intentionally an audit
layer, not an automated source collector yet.

- Added `src/fundamental_research_engine/evidence.py`.
- `build_evidence_audit` now produces:
  - source inventory by source type and reliability;
  - source manifest from theme evidence records;
  - claim links (`E1.C1`, etc.) from evidence items to their individual claims;
  - owner-level coverage for bottlenecks and companies;
  - missing evidence references;
  - a coverage health score and status (`missing`, `partial`, `thin`,
    `adequate`, `strong`).
- `run_pipeline` now embeds `evidence_audit` into `analysis.json`.
- `memo.md` now includes an `Evidence Audit` section with evidence count,
  claim count, average coverage score, and a coverage table.
- Added `fre audit <theme> [--out path]` to build the evidence audit without
  running the full pipeline.
- Updated README and tests.

Verification:

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes/*.json
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes_staged/hbm4
PYTHONPATH=src python -m fundamental_research_engine audit configs/themes/hbm4.json --out /tmp/hbm4-evidence-audit.json
```

Current result: 66 tests pass, all sample themes validate, HBM4 audit reports
4 evidence items, 4 claims, and 0.69 average owner coverage.

Direction check:

- The project is still moving in the right direction: deterministic core first,
  structured model outputs second, auditability before automation.
- The main risk is over-scoring qualitative research. Treat evidence coverage
  as process health only, not as thesis truth.
- The next best step is real evidence storage: raw source snapshots in
  `data/raw_sources`, normalized records in `data/normalized`, and stable
  claim ids linked back to thesis/bottleneck/company/scenario objects.

## Evidence Store Sync Update (2026-07-02)

Implemented the first local evidence store writer.

- Added `write_evidence_store` in `src/fundamental_research_engine/evidence.py`.
- Added `fre evidence-sync <theme> [--store-root <path>]`.
- `evidence-sync` writes:
  - `data/raw_sources/<theme_id>/<evidence_id>.json`
  - `data/normalized/<theme_id>/evidence.json`
  - `data/evidence/<theme_id>/claims.json`
  - `data/evidence/<theme_id>/coverage.json`
  - `data/evidence/<theme_id>/audit.json`
  - `data/evidence/<theme_id>/manifest.json`
- Raw source records are currently snapshots of evidence already present in
  theme configs. This deliberately avoids network collection until the storage
  and audit contracts are stable.
- Normalized evidence records include stable claim ids and linked owners
  (bottlenecks/companies that cite each evidence id).
- Generated data remains ignored by git under `data/`; only the writer,
  schemas-by-convention, docs, and tests are committed.

Verification:

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m fundamental_research_engine evidence-sync configs/themes/hbm4.json --store-root /tmp/fre-store
```

Current result: the sync command creates raw source snapshots, normalized
evidence, claims, coverage, audit, and manifest files for HBM4. The next step
is to add source collectors/fetchers that populate `raw_sources` from URLs
instead of only copying evidence already present in theme configs.

## Multi-Agent Hardening Pass (2026-07-01, Claude)

Reviewed the Codex commit above (`fee46fe`, "Harden research pipeline
evidence workflow") in full: fast-forward merged cleanly, 68 tests passed,
all sample themes and the staged HBM4 directory still validated, and a manual
smoke test of `audit`/`evidence-sync`/`diff`/`fill` confirmed the documented
behavior. No architectural conflicts with the prior Claude session — direction
assessed as on track (deterministic core -> structured model output ->
auditability, in that order, before automation).

Then implemented the agreed next steps, in priority order:

- **CI** (`.github/workflows/ci.yml`): matrix on Python 3.10/3.12, runs the
  full unit test suite, validates every monolithic sample theme and every
  staged theme directory, and runs the pipeline end to end on each monolithic
  sample. This is the safety net two independently-committing agents (Claude
  and Codex) were missing.
- **Golden memo snapshot** (`tests/golden/hbm4_memo.md`,
  `tests/test_golden_memo.py`): regression guard for `render_memo`. Confirmed
  `memo.md` is fully deterministic run-to-run (no leaked timestamps) before
  relying on an exact-match test. Regeneration steps are in the test's
  docstring.
- **`fre draft`** (`cli.py`): builds on `fre fill`'s per-stage primitive
  (extracted into `_fill_stage`/`_report_fill_result`) to add a multi-stage
  orchestrator. Default behavior drafts one stage and stops with a checkpoint
  message (same as calling `fre fill` once, but auto-runs `validate`+`run`
  once every stage is present); `--auto` walks every remaining stage
  unattended (rejects `--model manual`, since manual mode can't proceed
  without a human) and still auto-finishes at the end. Verified with a fake
  adapter end to end: 5 stages drafted, `.meta.json` written per stage, memo
  produced.
- **`fre critique`** (`prompts/critique.md`, `critique.py`, `cli.py`):
  standalone adversarial review of one already-drafted stage. A second model
  call, explicitly told to default to skepticism, flags ungrounded scorecard
  numbers, strawman counter-theses, unverifiable tracking signals, and
  inconsistencies with upstream stages. Writes `<stage>.critique.json`
  (`concerns` with severity/field/issue/suggested_fix, `overall_assessment`,
  `recommendation`: `accept`/`revise`). Deliberately does not block or modify
  `fre fill`/`fre draft` output — a human acts on it or doesn't. The shared
  `_complete_json_with_retry` retry-on-validation-error helper was factored
  out of `_fill_stage` so `critique` reuses the same JSON-extraction and
  retry behavior instead of duplicating it.
- **Real evidence fetching** (`evidence.py`): `default_fetch(url)` is a real,
  stdlib-only (`urllib`) fetcher — http/https only, checks `robots.txt` via
  `urllib.robotparser` before fetching (defaults to allow if robots.txt is
  unreachable, matching standard crawler convention), caps timeout and
  response size, strips HTML to text with no external dependencies. Wired
  into `write_evidence_store`/`fre evidence-sync` behind a new
  `--fetch-sources` flag (default off, so existing behavior and tests are
  unchanged). Any fetch failure (robots-disallowed, network error, timeout)
  falls back to the existing config-snapshot behavior for that evidence item
  rather than failing the whole sync; `manifest.json` records per-item fetch
  outcomes. Manually verified against real URLs (anthropic.com/robots.txt,
  api.github.com, example.com, and 3 of 4 real URLs in `configs/themes/hbm4.json`
  — the 4th timed out and fell back cleanly, exactly as designed). No test
  depends on live network (only `_strip_html` and the scheme-rejection path,
  plus `write_evidence_store` with an injected fake fetcher, are unit tested),
  so CI stays hermetic.

Verification:

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes/*.json
PYTHONPATH=src python -m fundamental_research_engine validate configs/themes_staged/hbm4
```

Current result: 94 tests pass.

Not done in this pass (deliberately deferred, not forgotten):

- Branch protection / required-status-check settings on the GitHub repo
  itself were not changed — that's a shared-infrastructure setting, not a
  code change, and should be confirmed with the repo owner before flipping.
  The Collaboration Rule below documents the recommended practice in the
  meantime.
- No claim-extraction LLM stage yet (turning fetched raw text into structured
  claims automatically) — `evidence-sync --fetch-sources` only stores the
  fetched text; a human or a future stage still has to turn it into
  `evidence[].claims` entries in `scenario_analysis.json`.

## Quality Gate + Web Layer + Calibration (2026-07-02, Claude)

Two threads landed this session, committed on a **feature branch** (not `main`)
because a second agent session was reported active concurrently.

**LLM adapter + Web layer (earlier in session):**
- `adapters.ClaudeAdapter.max_tokens` default bumped 4096 -> 16000; `OpenAIAdapter`
  gained an optional `max_tokens`; `get_adapter(name, model_name, max_tokens)` threads it.
- Optional web app under `web/` (FastAPI + uvicorn, `[web]` extra): shared-password
  HMAC cookie auth, server-side single API key, guided analysis flow with SSE
  streaming, per-session lock + global semaphore for small-team concurrency,
  one-click `deploy.sh`/`deploy.bat` + `run.*` + `.env.example`. The engine stays
  zero-dependency; web is a separate optional layer. NOTE: this VPS has no
  pip/venv, so the live FastAPI HTTP path is only `py_compile`-verified; the
  engine-through-service path is offline-smoke-verified.

**Quality gate (design in `docs/quality-gate-design.md`, build steps 1-6 done):**
- Step 1 — extracted the JSON-extract/retry helpers from `cli.py` into
  `llm_json.py` (`parse_model_json`, `complete_json_with_retry`, `CompletionAttempt`).
  `cli` imports them aliased; `web.service` unaffected. Pure move.
- Step 2 — `quality.py`: `build_grounding` scores each claim owner as
  grounded / corroborated (>=2 independent sources) / thin (single source) /
  ungrounded, with reliability-weighted coverage; `build_quality_scorecard`
  aggregates into a scorecard (grounding_score, disconfirmation, calibration,
  flags, "process-health not truth" note). Embedded in `build_analysis` (no LLM,
  offline/CI-safe) and rendered as a `## Quality Scorecard` memo section.
- Step 3/4 — adversarial QC: `prompts/quality_review.md` (pre-mortem / steelman-bear /
  consistency / unsupported-claims lenses), `validate_quality_review_shape`, and a
  new `fre qc <theme>` command (`--grounding-only` deterministic; full run calls a
  model; `--review <file>` for offline/manual; `--strict` gates on
  grounding_score/open-critical; default non-blocking, matching `critique`).
- Step 5 — schema extension: optional `thesis_evidence_ids` (theme) and per-scenario
  `evidence_ids`, so the thesis and each scenario are graded for grounding too.
  Backward-compatible (default empty); `OPTIONAL_STAGE_FIELDS` added to `stages.py`
  so optional fields are allowed-but-not-required by `validate_stage_shape`;
  validation cross-references them against known evidence ids. `hbm4.json` updated
  to demonstrate (thesis + bull grounded; bear scenario left ungrounded and now
  correctly flagged).
- Step 6 — calibration loop (`calibration.py`): register a theme's tracking
  signals / counter-theses / scenario triggers as dated predictions, resolve them
  over time (optionally with an assigned probability), and score
  counts + resolution rate + Brier. New `fre calibrate <theme>`
  (`--register` / `--resolve KEY --outcome` / `--show`) over a per-theme
  `track_records/<theme_id>.json`; `fre qc --track-record` folds calibration into
  the scorecard. This is the "keep quality high over time" half.

**Verification (all offline; this VPS has no API key / no pip):**
```bash
PYTHONPATH=src python3 -m unittest discover -s tests   # 118 pass
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes/*.json
PYTHONPATH=src python3 -m fundamental_research_engine qc configs/themes/hbm4.json --grounding-only
PYTHONPATH=src python3 -m fundamental_research_engine calibrate configs/themes/hbm4.json --register --track-record /tmp/tr.json
```
118 tests pass; all samples validate; golden memo regenerated (now includes the
scorecard + the flagged ungrounded bear scenario). The adversarial-QC model path
is covered by fake-adapter tests only — real-model qc needs an environment with
`ANTHROPIC_API_KEY` (network egress from this box works; only the key is missing).

Deferred (not forgotten): auto claim-extraction from fetched text; splitting the
QC lenses into independent adversarial verifiers with majority vote; wiring
`grounding_score` into `fre diff` for drift tracking; per-lens web UI surfacing.

## Theme Primer — fuzzy-topic entry point (2026-07-03, Claude)

Closed the biggest entry-point gap: the pipeline assumed a well-formed theme, but
real users often start fuzzy ("HBM", "solid-state batteries", "GLP-1 drugs"). Added
a **primer** layer that turns a fuzzy topic into a fast, structured orientation +
2–4 candidate framings the user picks to enter the existing pipeline. Chosen shape:
**web guided page** + **live source fetching** (per the user's two decisions).

- `src/fundamental_research_engine/primer.py` (engine, zero-dep, injectable):
  - `wikipedia_source(topic, http_get)` — keyless, predictable seed via Wikipedia
    opensearch + REST summary (real live fetch works from this box; verified against
    HBM / solid-state battery / GLP-1).
  - `build_primer(topic, adapter, *, ontology, prompts_dir, http_get, fetch, ...)` —
    fetch seed → model organizes into structured primer JSON → best-effort fetch of
    model-suggested primary-source URLs (robots-aware `default_fetch`). All HTTP and
    the adapter are injectable so tests stay hermetic.
  - `validate_primer_shape` (load-bearing fields; ≥1 candidate framing required),
    `render_primer_prompt`, and `framing_to_theme_definition` (a chosen framing →
    a valid `theme_definition` stage dict — asserted against `validate_stage_shape`).
  - `prompts/primer.md`: enum-constrained (theme_type/hype_stage), honesty rules —
    every factual claim carries a `verify` flag unless a seed source supports it.
- Web layer:
  - `web/service.py`: `create_primer` / `generate_primer` (SSE) / `get_primer` /
    `promote_framing` (seeds a fresh analysis session's `theme_definition.json`,
    then the normal `draft_and_run` completes the rest). Primers carry
    `meta.kind == "primer"` and are excluded from `list_analyses`.
  - `web/app.py`: `POST /api/primers`, `GET /api/primers/{sid}`,
    `GET .../stream` (SSE), `POST .../promote`.
  - `web/static/index.html`: Primer is now the default landing screen — topic box →
    streamed progress → rendered explainer/glossary/landscape/debates/claims/sources
    + clickable framing cards → "进入深度分析" promotes into the existing analysis view.
- Promotion deliberately does NOT set `thesis_evidence_ids` (the primer's fetched
  sources aren't yet in the theme's `evidence[]`, which is authored later in
  `scenario_analysis`); the thesis therefore shows as ungrounded and the quality
  scorecard correctly flags it — honest, and it drives the evidence work.

Verification (offline; this VPS has no pip/fastapi and no API key):
```bash
PYTHONPATH=src python3 -m unittest discover -s tests            # 130 pass
PYTHONPATH=src python3 -c "from fundamental_research_engine.primer import wikipedia_source; print(wikipedia_source('HBM')['title'])"
python3 -m py_compile web/app.py web/service.py                 # compiles
```
130 tests pass (test_primer.py: 9, test_web_primer.py: 3). Live Wikipedia lookup
verified for real topics. Web `service` path tested offline with `build_primer`
patched; `app.py` only `py_compile`-verified (no fastapi on this box); the
frontend JS passed `node --check`. NOT verifiable here: the live HTTP server and
real-model primer generation — both need an environment with `fastapi` + a key.

Deferred: broader keyless source discovery (SEC EDGAR full-text, industry bodies)
beyond Wikipedia + model-suggested URLs; a Socratic scoping step to refine a
chosen framing before drafting; carrying primer sources into the theme's evidence
so a promoted thesis starts partially grounded.

## EDGAR Source Discovery (2026-07-03, Claude)

Implemented Design 1 of `docs/data-sources-design.md` (real primary-source
discovery). Design 2 (auto claim extraction) is designed but not yet built.

- `src/fundamental_research_engine/edgar.py` (engine, zero-dep, injectable HTTP):
  - `search_filings(query, *, forms, date_from, date_to, limit, http_get)` — SEC
    EDGAR keyless full-text search (`efts.sec.gov/LATEST/search-index`), paginates,
    returns normalized hits `{adsh, cik, company, form, filed, period_ending,
    primary_doc, title, url}`.
  - `filing_to_evidence(hit, *, evidence_id, reliability)` — evidence-shaped record
    (`source_type: regulatory_filing`) that drops straight into `evidence[]`.
  - `fetch_filing_text(hit, fetch)` — pulls the primary document text (for the
    future claim-extraction step), via the shared robots-aware `default_fetch`.
  - `default_edgar_get` carries the SEC-required User-Agent (`FRE_SEC_USER_AGENT`,
    with a safe default) and a simple <=8 rps throttle; injectable so tests are hermetic.
- `fre sources search "<query>" [--forms 10-K,10-Q] [--from/--to] [--limit] [--out]`
  (nested subcommand). Prints/writes evidence-shaped candidates; does NOT auto-write
  into a theme (human curates, consistent with critique/qc).
- Verified REAL end-to-end from this box (EDGAR is keyless; network works):
  `sources search '"high bandwidth memory"' --forms 10-K` returned real 10-Ks
  (FormFactor, Veeco, MoSys); `fetch_filing_text` resolved the constructed
  Archives URL and pulled the 301K-char FormFactor 10-K with the query phrase in it.
- Tests: `tests/test_edgar.py` (6, injected http_get) + a CLI test (patched
  `search_filings`). Full suite: 137 pass. CI stays hermetic (no live network).

Design 2 from this note has since been implemented in the next section:
`claims.py` + `prompts/claim_extraction.md` + `fre extract-claims` with
deterministic quote verification. Still open: wire EDGAR hits into primer
`suggested_sources`; optional `source_types` controlled vocabulary in the
ontology; persist rich quote provenance into the evidence store sidecar.

## Quote-Backed Claim Extraction (2026-07-03, Codex)

Implemented Design 2 of `docs/data-sources-design.md`: source text can now be
converted into quote-verified candidate evidence claims.

- `src/fundamental_research_engine/claims.py`:
  - `validate_claims_shape(data)` enforces `{claims:[{text, quote, confidence, bears_on}]}` with `confidence` in `high|medium|low`.
  - `verify_quotes(claims, source_text)` normalizes whitespace and keeps only claims whose `quote` is found verbatim in the source text; kept claims get `verified: true`.
  - `extract_claims(...)` renders `prompts/claim_extraction.md`, calls the adapter with JSON retry, then applies deterministic quote verification.
- `prompts/claim_extraction.md` tells the model to extract atomic, checkable claims and include a source-text quote for every claim.
- `fre extract-claims <theme> --source <evidence_id|url>`:
  - supports `--source-text` for local text or URL fetching through `default_fetch`;
  - default/manual mode writes `<theme>-<source>.claim_extraction.prompt.md`;
  - model mode emits a verified report with `claims`, `claim_texts`, `dropped_unverified`, and source metadata;
  - `--claims <json>` accepts raw model output or a prior extraction report, strips stale `verified`, and re-verifies against current source text;
  - `--apply` appends only verified claim text back to the matched `evidence[].claims`.
- Docs updated: README now has a quote-backed claim extraction section; `docs/data-sources-design.md` marks Design 2 complete and calls out the remaining evidence-store sidecar work.

Verification:
```bash
PYTHONPATH=src python3 -m py_compile src/fundamental_research_engine/claims.py src/fundamental_research_engine/prompts.py src/fundamental_research_engine/cli.py
PYTHONPATH=src python3 -m unittest tests.test_claims tests.test_prompts tests.test_cli
PYTHONPATH=src python3 -m unittest discover -s tests            # 144 pass
for f in configs/themes/*.json; do PYTHONPATH=src python3 -m fundamental_research_engine validate "$f" || exit 1; done
```

Known limitations / next steps:
- The verified rich fields (`quote`, `confidence`, `bears_on`, `verified`) still do not change the theme schema (`evidence[].claims` remains `list[str]`), but the next section implements sidecar persistence in `data/evidence/<theme>/claims.json`.
- EDGAR source search and claim extraction are still separate commands; next step is a controlled batch path (`evidence-sync --discover-edgar` / `--extract-claims`) that defaults to candidate reports, not automatic theme mutation.
- Real model extraction still needs `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`; CI remains hermetic through fake adapters and pre-authored JSON fixtures.

## Rich Claim Provenance Sidecar (2026-07-04, Codex)

Implemented the first post-review hardening step: quote-verified claim metadata
can now be persisted in the evidence store, not just returned in an extraction
report.

- `src/fundamental_research_engine/evidence.py`:
  - `claim_records(..., rich_claims=...)` now accepts rich claim metadata and merges it into `data/evidence/<theme>/claims.json`.
  - Existing theme claims keep stable ids like `E1.C1` with `status: "applied"`.
  - Verified rich claims not yet present in the theme are retained as candidate sidecar records like `E1.Q1` with `status: "candidate"`.
  - Claim records now carry optional provenance fields: `quote`, `confidence`, `bears_on`, `verified`, `source_title`, `source_url`, `source_sha256`, `extracted_at`, `extraction_model`, `extraction_model_name`, and `extraction_attempts`.
  - `manifest.json` now includes `quote_verified_claim_count` and `candidate_claim_count`.
- `fre extract-claims`:
  - added `--store` to write rich provenance into `data/evidence/<theme>/claims.json`;
  - added `--store-root` to place the evidence store outside the project root when needed;
  - `--apply --store` reloads the updated theme so rich metadata attaches to the stable `E*.C*` claim ids.
- Docs updated: README and `docs/data-sources-design.md` now describe applied vs candidate claim provenance.

Verification:
```bash
PYTHONPATH=src python3 -m py_compile src/fundamental_research_engine/evidence.py src/fundamental_research_engine/cli.py
PYTHONPATH=src python3 -m unittest tests.test_evidence tests.test_cli
PYTHONPATH=src python3 -m unittest discover -s tests            # 146 pass
for f in configs/themes/*.json; do PYTHONPATH=src python3 -m fundamental_research_engine validate "$f" || exit 1; done
```

Next recommended step: add a `causal_map` stage whose edges must cite claim ids
from this provenance store. That is the bridge from evidence collection to real
industry-chain insight.

## Causal Map Stage (2026-07-04, Codex)

Implemented the next research-depth layer: an optional `causal_map` stage that
turns mechanism narrative into explicit, evidence-backed causal edges.

- Schema/model:
  - Added `CausalEdge` and `Theme.causal_map` in `models.py`.
  - Each edge carries `id`, `source`, `target`, `relationship`, `transmission`,
    `direction`, `lag`, `confidence`, and non-empty `claim_ids`.
  - `direction` is `positive|negative|mixed`; `confidence` is `high|medium|low`.
- Stage system:
  - `causal_map` is optional for backward compatibility. Existing themes without
    it still validate and run.
  - `prompts/causal_map.md` supports explicit `fre fill --stage causal_map`.
  - `draft --auto` still walks only the required stages, so old workflows are not
    forced to author causal maps.
- Validation:
  - Stage validation checks causal-edge shape and enum values.
  - Full theme validation checks `E*.C*` claim ids against actual
    `evidence[].claims`; `E*.Q*` candidate ids are allowed when the evidence id
    exists, because they live in the provenance sidecar.
- Pipeline/output:
  - `analysis.json` now includes `causal_map`.
  - `memo.md` renders a `Causal Map` table only when edges exist.
  - `diff` tracks causal edge additions/removals/changes.
- Sample:
  - `configs/themes/hbm4.json` and `configs/themes_staged/hbm4/causal_map.json`
    now include three evidence-backed edges: AI capex → HBM demand, HBM demand →
    memory supplier mix, and HBM attach → advanced packaging utilization.

Verification:
```bash
PYTHONPATH=src python3 -m unittest discover -s tests            # 152 pass
for f in configs/themes/*.json; do PYTHONPATH=src python3 -m fundamental_research_engine validate "$f" || exit 1; done
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes_staged/hbm4
```

Next recommended step: make quality scoring aware of causal maps. The quality
gate should flag causal edges with weak evidence, missing quote provenance, too
many single-source links, or low-confidence edges that drive high-conviction
theses.

## Causal Map Quality Gate (2026-07-04, Codex)

Implemented the next recommended step: causal maps are now first-class inputs
to the deterministic quality gate.

- `quality.build_causal_quality(...)` evaluates every causal edge's cited
  `claim_ids`:
  - resolves applied theme claims such as `E1.C1`;
  - resolves candidate sidecar claims such as `E1.Q1` when present in
    `data/evidence/<theme>/claims.json`;
  - flags missing claim ids, missing quote-verified provenance, single-source
    causal links, weak evidence coverage, and low-confidence causal edges.
- `pipeline.load_claim_provenance(...)` reads the optional claim provenance
  sidecar. If no sidecar exists, the engine still runs and surfaces the missing
  quote provenance as a quality flag.
- `build_analysis(...)`, `run_pipeline(...)`, and `fre qc` now all include
  `quality_scorecard.causal_quality`, so the normal run path and standalone QC
  command stay consistent.
- `render.py` adds a compact causal edge summary to the Quality Scorecard and
  keeps detailed causal issues in Quality Flags.
- README, `docs/quality-gate-design.md`, unit tests, and the HBM4 golden memo
  snapshot were updated.

Verification:
```bash
PYTHONPATH=src python3 -m py_compile src/fundamental_research_engine/quality.py src/fundamental_research_engine/pipeline.py src/fundamental_research_engine/cli.py src/fundamental_research_engine/render.py
PYTHONPATH=src python3 -m unittest tests.test_quality tests.test_pipeline tests.test_cli
PYTHONPATH=src python3 -m unittest discover -s tests            # 157 pass
for f in configs/themes/*.json; do PYTHONPATH=src python3 -m fundamental_research_engine validate "$f" || exit 1; done
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes_staged/hbm4
git diff --check
```

At this point, HBM4 still had no committed `data/evidence/hbm4/claims.json`
sidecar, so it correctly reported `quote-verified` causal edges as `0` and
flagged missing quote provenance. That gap is closed in the next section.

## HBM4 Claim Provenance Sample (2026-07-04, Codex)

Completed the HBM4 evidence sidecar as the first committed sample of the
evidence-to-causal-map loop.

- Fixed `fre extract-claims --store` so repeated source extractions preserve
  existing `data/evidence/<theme>/claims.json` records instead of overwriting
  prior rich provenance.
- Updated `.gitignore` to allow committed
  `data/evidence/<theme>/claims.json` sidecars while still ignoring generated
  raw source snapshots, normalized evidence, audit, coverage, and manifest
  files.
- Added `data/evidence/hbm4/claims.json` with quote-verified provenance for
  `E1.C1`, `E2.C1`, `E3.C1`, and `E4.C1`.
- Regenerated the HBM4 golden memo: causal quality now reports
  `quote-verified 3/3` for causal edges. The remaining causal quality flag is
  the advanced-packaging edge being supported by a single source (`E3.C1`).
- Added a CLI regression test proving sequential `extract-claims --store`
  calls preserve prior sidecar records.

Verification:
```bash
PYTHONPATH=src python3 -m unittest tests.test_cli.ExtractClaimsCliTest tests.test_quality tests.test_pipeline
PYTHONPATH=src python3 -m fundamental_research_engine qc configs/themes/hbm4.json --grounding-only --out /tmp/hbm4-qc.json
```

Next recommended step: add a second independent source for the advanced
packaging causal edge (for example a foundry/packaging company disclosure or a
second credible industry source) so `edge-hbm-attach-to-packaging-capacity`
is no longer single-source. Completed in the next section.

## Multi-Theme Provenance + Quality Tier Batch (2026-07-04, Codex)

Completed the six-action batch that turns the engine from an HBM4-only worked
example into a reusable, theme-level causal research loop.

- Added `provenance.py` plus `fre build-provenance`, a re-entrant command that
  reads curated specs from `configs/provenance/<theme>.json`, verifies quotes,
  and writes `data/evidence/<theme>/claims.json`.
- Added process-quality tiers to `quality_scorecard.quality_status`:
  `draft`, `evidence-backed`, `quote-verified`,
  `multi-source causal map`, and `publishable memo`. `publishable memo`
  requires completed adversarial review, not just deterministic checks.
- Upgraded HBM4 with a second advanced-packaging source (`E5`, TSMC 2025 annual
  report) and moved `edge-hbm-attach-to-packaging-capacity` from single-source
  support to `E3.C1` + `E5.C1`.
- Added causal maps, thesis/scenario evidence ids, and quote-provenance sidecars
  for all current sample themes:
  - `hbm4`
  - `cowos`
  - `ai-liquid-cooling`
  - `copper-supply-demand`
  - `solid-state-battery`
- Strengthened the model workflow prompts so future GPT/Claude runs follow the
  evidence-first sequence: mechanism -> claim provenance -> causal map ->
  bottlenecks/profit pools -> company positioning -> scenarios/QC.
- README and `docs/quality-gate-design.md` now document
  `build-provenance`, the evidence sidecar contract, and the quality-tier gate.

Verification targets for this batch:

```bash
PYTHONPATH=src python3 -m py_compile src/fundamental_research_engine/provenance.py src/fundamental_research_engine/quality.py src/fundamental_research_engine/cli.py src/fundamental_research_engine/render.py
for theme in hbm4 cowos ai-liquid-cooling copper-supply-demand solid-state-battery; do PYTHONPATH=src python3 -m fundamental_research_engine validate "configs/themes/${theme}.json" --project-root . || exit 1; done
PYTHONPATH=src python3 -m fundamental_research_engine validate configs/themes_staged/hbm4 --project-root .
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

Next recommended direction:

1. Add CI checks that fail when a sample theme has unresolved causal claim ids
   or missing quote provenance.
2. Add one non-AI domain pack with the same standard (for example copper or
   solid-state battery) to prove the methodology is not AI-specific.
3. Build source-collector adapters beyond EDGAR for official reports, investor
   relations pages, and regulator/statistical datasets, so provenance specs can
   be refreshed with less manual source-text handling.

## Review Hardening of Codex's Claim/Causal Work (2026-07-04, Claude)

Reviewed Codex's 6 commits (claim extraction + the causal_map stage + provenance +
readiness tiers). Verdict: reasonable and high-quality, in-spirit with
auditability-first. Landed two of the review's improvement points:

- **#1 Quote-verification robustness** (`claims.py:_normalize_quote_text`): now
  folds curly quotes/primes/guillemets, the various dashes, and ellipsis, and
  matches case-insensitively (whitespace incl. NBSP already collapsed). Reduces
  false-negative drops of genuine quotes (filings render punctuation differently
  from how a model retypes a "verbatim" quote) without weakening the substring
  requirement that blocks fabricated quotes. Folding only widens matching, so no
  previously-verified claim regresses. Also benefits `provenance.py` (shares
  `verify_quotes`). New test: `test_verify_quotes_folds_unicode_punctuation_and_case`.
- **#2 Provenance anti-drift guard** (`tests/test_provenance_drift.py`): the
  committed `data/evidence/<theme>/claims.json` sidecars are a scoring input
  (`build_causal_quality` trusts their `verified` flag). New test re-runs
  `build_provenance_records` against every `configs/provenance/<theme>.json` spec
  (specs embed `source_text`, so it's offline) and asserts every claim_id still
  exists and every quote still verifies. Catches silent drift if a theme's
  evidence is edited without regenerating provenance.

162 tests pass. Open review items not yet actioned (product-positioning calls,
awaiting user): #3 causal_map is opt-in and absent from the guided/`--auto` flow;
#4 rename the `publishable_memo` readiness tier to something process-neutral
(e.g. `review-ready`); #5 quote-presence != entailment (document + rely on
adversarial QC / human review).

## Monitoring / Constraint Radar Discussion Update (2026-07-04, Codex)

User asked how to upgrade the engine from "static theme analysis" to
"forecasting binding-constraint migration" and pointed to
`docs/monitoring-and-constraint-radar.md`.

Updated that document with Codex's provisional answers:

- **Cadence**: use event discovery + weekly radar recomputation + quarterly deep
  re-underwriting. Do not start with daily full reruns or a heavyweight daemon.
- **Latent bottleneck sourcing**: combine human domain seeds, automatic
  derivation from `causal_map` / value chain / profit pools, and model-generated
  candidates that stay in `candidate` state until validated.
- **Alert taxonomy**: split alerts into `constraint_migration_alert`,
  `driver_slope_alert`, `signpost_alert`, and `thesis_degradation_alert`.
  Each alert should include quote-backed evidence, old/new scores, causal
  impact path, disconfirming condition, and cooldown.
- **Implementation sequence**: start with `fre radar`, then `fre watch --weekly`,
  then digest / internal-control alert outputs. Web/message integration should
  come after the batch loop is auditable.
- **Naming recommendation**: rename `publishable memo` to `review-ready` or
  `decision-review-ready` later, because monitoring should emit process signals,
  not imply tradable conclusions.

Suggested next implementation units for Claude:

1. Add `radar.py` and a `fre radar` CLI command that builds current + latent
   constraint rankings from a theme.
2. Add `configs/watchlists/*.json` only after the radar output contract is
   stable.
3. Keep generated watch reports under ignored `reports/watch/<date>/`.

## Constraint Radar v1 (2026-07-04, Claude)

Implemented the first increment of the monitoring layer designed in
`docs/monitoring-and-constraint-radar.md` (Claude+Codex discussion; Section 9 has
Claude's four "gears" and the v1 scope). This box has no key/pip; radar v1 is
deterministic + offline + hermetically tested, and does not touch the pipeline.

- `src/fundamental_research_engine/radar.py` + `fre radar <theme> <spec.json>`:
  gears A (headroom-ratio erosion), B (driver slope surprise), F (persisted
  `radar_state/<theme>.json` time series). Candidate constraints in three rings
  (current_binding / adjacent_latent / second_order_external; the exogenous ring
  uses a signpost, not a ratio). Ranks by `capacity_growth/demand_growth`, detects
  migration vs the prior run, emits `driver_slope_alert` / `constraint_migration_alert`
  at watch/investigate/action with old/new ratio, driver_path, and a disconfirming
  condition. `uncovered_candidates` surfaces theme-derived constraints not yet in
  the spec. `configs/radar/hbm4.json` is a worked example; `radar_state/` is gitignored.
- Verified: 170 tests pass (test_radar.py: 8). Demo: HBM headroom 0.79 is the
  acknowledged binding constraint, but rack power/cooling at 0.65 is already tighter
  → action migration alert; a second run shows it eroding 0.65→0.575 (delta −0.075)
  off the persisted state.

Gears C + D added (2026-07-04, Claude):
- Gear C consensus proxy (`consensus.py`): `fre radar --corpus <dated docs>` scores
  each candidate's recent-vs-earlier mention rate → `{level, trend, pre_consensus}`.
  A migration alert on a constraint whose mentions are still low+flat is tagged
  `pre_consensus` (the alpha window — migrating but not yet priced); a rising trend
  is tagged "likely already priced". Constraints declare `terms` for matching;
  `configs/radar/hbm4.corpus.json` is a worked corpus.
- Gear D radar self-calibration (`radar.py`: radar_migration_predictions /
  register_radar_predictions): `fre radar --register-predictions` writes each
  migration call as a dated, falsifiable prediction (action/investigate/watch →
  prob 0.75/0.55/0.35) into `radar_state/<theme>.predictions.json`; the report
  embeds a `calibration` summary. Resolve later with the existing
  `fre calibrate <theme> --track-record <preds> --resolve <key> --outcome true|false`
  → Brier. Demo: power/cooling resolved true at prob 0.75 → Brier 0.0625.
- Verified: 181 tests pass (test_radar.py 15, test_consensus.py 6). Demo: rack
  power/cooling is tightest (0.65) AND low/flat mentions → pre-consensus action
  alert, while HBM/CoWoS are already rising in the corpus (priced).

Weekly closed loop `fre watch` added (2026-07-04, Claude): `watch.py` +
`configs/watchlists/*.json`. `fre watch <watchlist.json>` runs the radar (A+B+C)
per theme, gates for material change (driver slope surprise / action|investigate
migration / pre-consensus window / headroom erosion; everything else is "quiet", no
noise), optionally registers migration predictions (D) and embeds calibration, adds
a best-effort analysis run-to-run diff summary, and writes one gated digest to
`reports/watch/<as_of>/digest.{json,md}` (gitignored). Flags: --as-of, --out-dir,
--horizon, --no-persist, --no-register, --no-diff. One bad theme is captured as an
error row, not a crash. `configs/watchlists/ai-compute.json` is a worked example.
Verified: 189 tests pass (test_watch.py 8). All four gears (A headroom / B slope /
C consensus / D calibration) are now wired into the standing weekly loop.

Consensus corpus auto-collection added (2026-07-04, Claude): `corpus.py` +
`fre sources corpus "<broad query>" --forms --from --to --limit [--fetch-text] --out`.
Builds a dated document corpus from EDGAR full-text search
(`{documents:[{id,date,text,url,company,form}]}`) that feeds `fre radar --corpus` /
a watchlist `corpus` field. `--fetch-text` pulls full filing text (heavy, one GET per
filing — offload it); without it, documents fall back to title metadata (light, for
wiring/smoke). Guidance baked into the docstring: use a BROAD theme query, not a
per-constraint term, or the signal is meaningless. Also hardened `default_edgar_get`
with 5xx retry + linear backoff (extracted testable `_retry`) — EDGAR EFTS
intermittently 500s under load. Verified: 197 tests pass (test_corpus.py 5,
test_edgar.py retry 3); live keyless smoke collected real Micron/Netlist/Credo 10-Ks
and fed them through the radar consensus proxy end to end.

Monitoring follow-ups completed (2026-07-04, Claude):
- Candidate auto-derivation: `fre radar-scaffold <theme>` (radar.derive_candidate_spec)
  scaffolds a radar spec from bottlenecks (current_binding) + causal_map targets /
  segments / profit_pools (adjacent_latent), growth/driver left null to fill.
- Corpus auto-collection wired into `fre watch`: a watchlist entry can carry
  `corpus_query` (+ corpus_forms/from/to/limit/fetch_text) and watch builds the corpus
  from EDGAR, feeds the consensus proxy, and writes reports/watch/<as_of>/corpus-<theme>.json
  as an audit trail. `--no-corpus-fetch` skips it; EDGAR failure degrades to no-consensus
  (theme still scanned), never crashes the sweep. Live-verified end to end.
- Digest into the web layer: Service.list_watch_digests / get_watch_digest (path-traversal
  guarded) + routes GET /api/watch/digests and /api/watch/digests/{as_of}.
- Readiness tier renamed publishable_memo -> review_ready (process-neutral; the human
  still judges the memo).
- Verified: 204 tests pass (test_radar scaffold, test_watch corpus_query, test_web_watch).

Still open (lower priority): a front-end UI card / push notification for digests (Codex
8.4 step 3 push part); extend the consensus corpus to non-filing sources (news).

## China Source Collector — cninfo (2026-07-08, Claude)

Added a free, zero-dependency China-market source collector as the counterpart to
`edgar.py`, so the "both US + China" research universe is covered without any paid
data subscription (US enterprise feeds like FactSet/S&P are not accessible).

- `src/fundamental_research_engine/cninfo.py`: keyless full-text search over
  official cninfo (巨潮资讯) Shenzhen/Shanghai disclosures via the public
  `hisAnnouncement/query` JSON POST endpoint. Stdlib-only (`urllib`), injectable
  `http_post` so tests are hermetic, <=8 rps throttle + browser UA, `<em>` strip,
  Beijing (UTC+8) ms-timestamp → date, `finalpage` PDF URL build.
  `announcement_to_evidence` emits the same evidence shape as `filing_to_evidence`
  (`source_type: regulatory_filing`).
- `fre sources cn-search "<query>" [--from --to] [--limit] [--column] [--out]`,
  mirroring `sources search`. Full-text is cross-market (default `--column szse`
  still returns Shanghai issuers); date range applied only when both bounds given.
- `tests/test_cninfo.py` (7 tests, injected `http_post`, real-shape fixture).

Verified LIVE from this box (cninfo is keyless; network works): `cn-search 固态电池`
returned 3 real official disclosures (格林美/广东建工/金龙羽) with correct dates and
`static.cninfo.com.cn` document URLs; grafting those evidence records onto
`configs/themes/solid-state-battery.json` passes `validate_theme_dict` (schema +
referential integrity).

Context: this session also installed Anthropic's `financial-services` plugin
marketplace (all 20 plugins) globally at the user level. Recommended low-cost data
stack: EDGAR + cninfo + (future) AkShare/FRED/USGS collectors feeding the existing
extract-claims/provenance/quality flow; US enterprise MCP connectors skipped.
Financial skills (dcf/comps/earnings/initiating-coverage) used as offline
methodology + Excel/deck output, not as data feeds.

Next recommended step: add AkShare-style fundamentals and a macro/commodity source
(FRED/USGS) as further stdlib-friendly collectors, and wire cninfo/EDGAR hits into
the primer's `suggested_sources`. PDF body extraction for cninfo adjuncts remains
out of scope for the zero-dependency core.

## Eastmoney Fundamentals Collector (2026-07-08, Claude)

Second free collector, after cninfo: an "AkShare-style" fundamentals layer built
stdlib-only (no akshare/pandas), so the financial-analysis skills (comps/DCF) get
the numeric inputs they need on the same evidence rail as edgar/cninfo.

- `src/fundamental_research_engine/eastmoney.py`: keyless Eastmoney (东方财富)
  endpoints. `search_security` (searchadapter suggest → resolve name/ticker to a
  `MktNum.Code` secid), `quote` (push2delay delayed snapshot: price, total/circ
  market cap, PE(TTM), PB), `security_to_evidence` → evidence record with
  `source_type: market_data`, metrics in `claims[]`, quote-page `url`, `as_of`
  date. Stdlib `urllib`, injectable `http_get`, <=8 rps, browser UA + Referer.
  Note: `push2.eastmoney.com` dropped connections from this box; `push2delay`
  works — used it deliberately (delayed data is fine for research).
- `fre sources quote "<name|ticker>" [--as-of] [--out]`.
- `tests/test_eastmoney.py` (6 tests, injected http_get, real-shape fixtures).

Verified LIVE from this box (all keyless): `quote 宁德时代` → 0.300750, PE 20.14 /
PB 5.11; `quote AAPL` → 105.AAPL (苹果); `quote 腾讯控股` → 116.00700 — A-share +
US + HK all resolve. The `market_data` evidence record passes `validate_theme_dict`
when grafted onto a theme (`source_type` is not enum-restricted; reliability is).

Data collectors now cover both heads of the "中美两头" universe:
- US filings: `edgar.py` (`sources search`)
- China disclosures: `cninfo.py` (`sources cn-search`)
- Fundamentals A/HK/US: `eastmoney.py` (`sources quote`)

Update (same session): generalized `quote` to also cover **commodity futures**
(added daily change/pct-change fields; equity-only mktcap/PE/PB come back as `"-"`
for futures and are dropped). `sources quote 沪铜主连` returns a live keyless SHFE
copper price snapshot, so the copper/supply-demand theme now has a commodity
source. Verified live (宁德时代 equity + 沪铜主连 future).

Macro time-series (FRED/World Bank) is deferred: FRED needs a free API key, and
`api.worldbank.org` data paths return 502 from this box (metadata path works, so
it's egress/proxy-specific, not a code issue). Commodity price snapshots via
Eastmoney cover the near-term supply/demand need without a keyed/blocked source.

## Primer Auto-Discovery Wiring (2026-07-08, Claude)

Completed the final route item: the primer now auto-discovers **real primary
sources** for a fuzzy topic instead of relying only on model-suggested URLs.

- `primer.default_discover(topic)`: queries EDGAR (US filings) + cninfo (China
  disclosures), returns evidence-shaped records tagged `discovery: edgar|cninfo`.
  Best-effort/network-robust — each collector is independent and swallows request
  errors, so a flaky feed never breaks primer generation.
- `build_primer(..., discover=None)`: new opt-in param. When a discoverer is
  passed, its records are merged into `fetched_sources` (marked
  `fetch_status: "discovered"`) and also returned as `discovered_sources`. Default
  stays off, so existing hermetic tests are unchanged.
- `web/service.py` passes `discover=default_discover` on the live primer path, so
  the web Primer surfaces real China+US filings.
- `tests/test_primer.py`: +2 tests (discovery folds records in; off by default).

Verified LIVE from this box: `default_discover("high bandwidth memory")` returned
real EDGAR filings (cninfo empty for the English term); `default_discover("固态电池")`
returned 3 real cninfo disclosures (格林美/广东建工/金龙羽). 228 tests pass.

Route status ("先按记忆里的路线完成"): DONE.
- US filings collector (`edgar.py`) — pre-existing.
- China disclosures collector (`cninfo.py` / `sources cn-search`).
- Fundamentals + commodity collector (`eastmoney.py` / `sources quote`, A/HK/US +
  SHFE futures).
- Primer auto-discovery wiring (this section).
Deferred with documented reason: macro time-series (FRED needs a key; World Bank
data paths 502 from this box) — revisit when a keyless/reachable macro series
source or a FRED key is available. Eastmoney commodity snapshots cover the
near-term supply/demand need.

Eastmoney fundamentals eastmoney hits are not yet wired into `default_discover`
(it takes a topic, and quote needs a resolved ticker); a future step could add a
company-name → quote discovery path.

## Collaboration Rule

Before ending a meaningful work session:

1. Run tests when practical.
2. Update this file with current state and next steps.
3. Commit and push to `origin/main` unless there is a reason to keep work local.
4. Mention any known failing tests, unresolved assumptions, or uncommitted local artifacts.

### Multi-agent note

Both Codex and Claude now run **locally on the same host**, so work is
effectively single-writer and sequential. Decision (2026-07-08, per the user):
**work directly on `main`, no feature branches.** Before pushing, pull/rebase on
`origin/main`, re-run the full test suite + sample validation, and resolve
conflicts by reading both sides. The earlier feature-branch-per-session guidance
is retired now that concurrency is no longer a real risk.
