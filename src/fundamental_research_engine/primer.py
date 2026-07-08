"""Theme primer: turn a fuzzy topic into a fast, structured orientation.

The primer is the missing *entry point* to the pipeline. A user who is not yet
sure what they want to analyze ("HBM", "solid-state batteries", "GLP-1 drugs")
gets back a plain-language explainer, a glossary, a landscape/value-chain sketch,
the current state of play and maturity, the key debates, and — most importantly —
a handful of concrete *candidate framings* they can pick from to enter the
structured analysis pipeline.

Design constraints, consistent with the rest of the engine:
- A primer is an *unverified map*, not truth. Claims are surfaced with an
  explicit "verify" flag and handed to the grounding layer, not asserted.
- Live sources are fetched to seed the primer (Wikipedia as a keyless,
  predictable first-order source; plus any URLs the model suggests, best-effort
  and robots-aware via the shared evidence fetcher).
- Zero new dependencies; the model adapter and all HTTP are injectable so tests
  stay hermetic.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .cninfo import announcement_to_evidence, search_announcements
from .edgar import filing_to_evidence, search_filings
from .evidence import DEFAULT_FETCH_TIMEOUT_SECONDS, FetchResult, default_fetch
from .llm_json import complete_json_with_retry

WIKI_OPENSEARCH = "https://en.wikipedia.org/w/api.php?action=opensearch&limit=1&format=json&search="
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
PRIMER_USER_AGENT = "fundamental-research-engine-primer/0.1 (+lawful-sources-only)"

HttpGet = Callable[[str], Any]
Fetcher = Callable[[str], FetchResult]
Discoverer = Callable[[str], list]

_DISCOVERY_ERRORS = (urllib.error.URLError, urllib.error.HTTPError, ValueError)


def default_discover(topic: str, *, edgar_limit: int = 3, cninfo_limit: int = 3) -> list[dict[str, Any]]:
    """Discover real primary sources for a topic from EDGAR (US) + cninfo (China).

    Best-effort and network-robust: each collector is tried independently and any
    request failure yields no records from that source rather than raising, so a
    flaky feed never breaks primer generation. Records are evidence-shaped and
    tagged with the discovering collector.
    """
    records: list[dict[str, Any]] = []
    try:
        for i, hit in enumerate(search_filings(topic, limit=edgar_limit), start=1):
            rec = filing_to_evidence(hit, evidence_id=f"US{i}")
            rec["discovery"] = "edgar"
            records.append(rec)
    except _DISCOVERY_ERRORS:
        pass
    try:
        for i, hit in enumerate(search_announcements(topic, limit=cninfo_limit), start=1):
            rec = announcement_to_evidence(hit, evidence_id=f"CN{i}")
            rec["discovery"] = "cninfo"
            records.append(rec)
    except _DISCOVERY_ERRORS:
        pass
    return records


def default_http_get(url: str, timeout: float = DEFAULT_FETCH_TIMEOUT_SECONDS) -> Any:
    """Minimal JSON GET for public, keyless APIs (Wikipedia). Injectable for tests."""
    request = urllib.request.Request(url, headers={"User-Agent": PRIMER_USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _slug(value: str) -> str:
    out = []
    for char in value.strip().lower():
        if char.isalnum():
            out.append(char)
        elif char in " -_/":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "topic"


def wikipedia_source(topic: str, http_get: HttpGet = default_http_get) -> dict[str, Any] | None:
    """Resolve a topic to its Wikipedia page and pull the intro extract.

    Returns an evidence-shaped source dict, or None if nothing is found or the
    lookup fails (the primer still works, just without a seed).
    """
    try:
        opensearch = http_get(WIKI_OPENSEARCH + urllib.request.quote(topic))
        # opensearch -> [query, [titles], [descriptions], [urls]]
        titles = opensearch[1] if isinstance(opensearch, list) and len(opensearch) > 1 else []
        if not titles:
            return None
        title = titles[0]
        summary = http_get(WIKI_SUMMARY + urllib.request.quote(title.replace(" ", "_")))
        extract = summary.get("extract", "") if isinstance(summary, dict) else ""
        url = ""
        if isinstance(summary, dict):
            url = summary.get("content_urls", {}).get("desktop", {}).get("page", "") or ""
        if not url and isinstance(opensearch, list) and len(opensearch) > 3 and opensearch[3]:
            url = opensearch[3][0]
    except (KeyError, IndexError, ValueError, TypeError, OSError):
        return None

    return {
        "id": "S-wiki",
        "title": title,
        "source_type": "reference",
        "date": date.today().isoformat(),
        "url": url,
        "reliability": "medium",
        "claims": [],
        "extract": extract,
    }


_REQUIRED_FRAMING_FIELDS = ("id", "title", "core_question", "thesis_hypothesis", "theme_type", "domain", "drivers")


def validate_primer_shape(data: Any) -> list[str]:
    """Validate the model's primer JSON (load-bearing fields only; lenient on prose)."""
    if not isinstance(data, dict):
        return ["primer: expected a JSON object"]

    errors: list[str] = []
    for field in ("explainer", "state_of_play"):
        if not isinstance(data.get(field), str):
            errors.append(f"primer.{field}: expected str")

    for field in ("glossary", "landscape", "key_debates", "key_claims", "candidate_framings", "suggested_sources"):
        if not isinstance(data.get(field), list):
            errors.append(f"primer.{field}: expected list")

    maturity = data.get("maturity")
    if not isinstance(maturity, dict):
        errors.append("primer.maturity: expected object")
    else:
        if not isinstance(maturity.get("hype_stage"), str):
            errors.append("primer.maturity.hype_stage: expected str")
        trl = maturity.get("technology_readiness_level")
        if not isinstance(trl, int) or isinstance(trl, bool):
            errors.append("primer.maturity.technology_readiness_level: expected int")

    framings = data.get("candidate_framings")
    if isinstance(framings, list):
        if not framings:
            errors.append("primer.candidate_framings: at least one framing is required")
        for index, framing in enumerate(framings):
            prefix = f"primer.candidate_framings[{index}]"
            if not isinstance(framing, dict):
                errors.append(f"{prefix}: expected object")
                continue
            for field in _REQUIRED_FRAMING_FIELDS:
                if field not in framing:
                    errors.append(f"{prefix}.{field}: missing")
            if "drivers" in framing and not isinstance(framing["drivers"], list):
                errors.append(f"{prefix}.drivers: expected list")

    claims = data.get("key_claims")
    if isinstance(claims, list):
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                errors.append(f"primer.key_claims[{index}]: expected object")
            elif not isinstance(claim.get("claim"), str):
                errors.append(f"primer.key_claims[{index}].claim: expected str")

    return errors


def render_primer_prompt(topic: str, seed_sources: list[dict[str, Any]], ontology: dict[str, Any], prompts_dir: Path) -> str:
    template_path = prompts_dir / "primer.md"
    if not template_path.exists():
        raise FileNotFoundError(f"no primer template at {template_path}")
    template = template_path.read_text(encoding="utf-8")

    seed_block = json.dumps(
        [{"id": s["id"], "title": s["title"], "url": s.get("url", ""), "extract": s.get("extract", "")[:4000]} for s in seed_sources],
        ensure_ascii=False,
        indent=2,
    )
    substitutions = {
        "TOPIC": topic,
        "SEED_SOURCES_JSON": seed_block,
        "THEME_TYPES_JSON": json.dumps(ontology.get("theme_types", []), ensure_ascii=False),
        "HYPE_STAGES_JSON": json.dumps(ontology.get("hype_stages", []), ensure_ascii=False),
    }
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _unverified_claims(primer: dict[str, Any]) -> list[str]:
    out = []
    for claim in primer.get("key_claims", []):
        if not isinstance(claim, dict):
            continue
        supported = claim.get("supported_by") or []
        if claim.get("verify", True) or not supported:
            out.append(str(claim.get("claim", "")))
    return [c for c in out if c]


def build_primer(
    topic: str,
    adapter: Any,
    *,
    ontology: dict[str, Any],
    prompts_dir: Path,
    http_get: HttpGet = default_http_get,
    fetch: Fetcher = default_fetch,
    max_attempts: int = 2,
    fetch_suggested: bool = True,
    discover: Discoverer | None = None,
) -> dict[str, Any]:
    """Fetch seed sources, organize with the model, and return a structured primer.

    Raises ValueError if the model cannot produce a valid primer after retries.
    """
    seed = wikipedia_source(topic, http_get)
    seed_sources = [seed] if seed else []

    prompt = render_primer_prompt(topic, seed_sources, ontology, prompts_dir)
    initial = adapter.complete(prompt)
    completion = complete_json_with_retry(adapter, initial, prompt, validate_primer_shape, max_attempts)
    if completion.data is None:
        raise ValueError("primer: model could not produce a valid primer: " + "; ".join(completion.errors))
    primer = completion.data

    fetched_sources: list[dict[str, Any]] = []
    for source in seed_sources:
        record = {k: v for k, v in source.items() if k != "extract"}
        record["fetch_status"] = "fetched"
        record["extract_chars"] = len(source.get("extract", ""))
        fetched_sources.append(record)

    if fetch_suggested:
        for index, suggestion in enumerate(primer.get("suggested_sources", []), start=1):
            if not isinstance(suggestion, dict):
                continue
            url = suggestion.get("url", "")
            if not url:
                continue
            result = fetch(url)
            fetched_sources.append(
                {
                    "id": f"S{index}",
                    "title": suggestion.get("title", url),
                    "source_type": suggestion.get("source_type", "reference"),
                    "date": date.today().isoformat(),
                    "url": url,
                    "reliability": suggestion.get("reliability", "medium"),
                    "claims": [],
                    "fetch_status": result.status,
                    "extract_chars": len(result.text or "") if result.ok else 0,
                }
            )

    discovered_sources: list[dict[str, Any]] = []
    if discover is not None:
        for record in discover(topic):
            if not isinstance(record, dict):
                continue
            discovered = {**record, "fetch_status": "discovered", "extract_chars": 0}
            discovered_sources.append(discovered)
            fetched_sources.append(discovered)

    return {
        "topic": topic,
        "resolved_title": seed["title"] if seed else topic,
        "seed_used": bool(seed),
        "primer": primer,
        "fetched_sources": fetched_sources,
        "discovered_sources": discovered_sources,
        "unverified_claims": _unverified_claims(primer),
    }


def framing_to_theme_definition(
    framing: dict[str, Any],
    primer: dict[str, Any],
    as_of: str | None = None,
    thesis_evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Convert a chosen candidate framing into a theme_definition stage dict."""
    maturity = primer.get("maturity", {}) if isinstance(primer, dict) else {}
    definition = {
        "id": _slug(framing.get("title", framing.get("id", "topic"))),
        "title": framing["title"],
        "as_of": as_of or date.today().isoformat(),
        "theme_type": framing["theme_type"],
        "domain": framing["domain"],
        "core_question": framing["core_question"],
        "thesis": framing["thesis_hypothesis"],
        "hype_stage": maturity.get("hype_stage", ""),
        "technology_readiness_level": maturity.get("technology_readiness_level", 1),
        "drivers": [str(d) for d in framing.get("drivers", [])],
    }
    if thesis_evidence_ids:
        definition["thesis_evidence_ids"] = list(thesis_evidence_ids)
    return definition
