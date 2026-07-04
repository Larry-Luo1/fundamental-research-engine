from __future__ import annotations

import re
from typing import Any

from .llm_json import complete_json_with_retry
from .prompts import render_claim_extraction_prompt

_CONFIDENCE_VALUES = {"high", "medium", "low"}


def validate_claims_shape(data: Any) -> list[str]:
    """Validate model output for quote-backed claim extraction."""
    if not isinstance(data, dict):
        return ["claims: expected a JSON object"]

    if "claims" not in data:
        return ["claims.claims: missing"]
    if not isinstance(data["claims"], list):
        return ["claims.claims: expected list"]

    errors: list[str] = []
    for index, item in enumerate(data["claims"]):
        prefix = f"claims.claims[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        unexpected = sorted(set(item) - {"text", "quote", "confidence", "bears_on"})
        for field in unexpected:
            errors.append(f"{prefix}.{field}: unexpected field")
        for field in ("text", "quote", "confidence", "bears_on"):
            if field not in item:
                errors.append(f"{prefix}.{field}: missing")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{prefix}.text: expected non-empty str")
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            errors.append(f"{prefix}.quote: expected non-empty str")
        confidence = item.get("confidence")
        if not isinstance(confidence, str):
            errors.append(f"{prefix}.confidence: expected str")
        elif confidence not in _CONFIDENCE_VALUES:
            errors.append(f"{prefix}.confidence: unknown value '{confidence}'")
        bears_on = item.get("bears_on")
        if not isinstance(bears_on, list):
            errors.append(f"{prefix}.bears_on: expected list")
        else:
            for bears_index, value in enumerate(bears_on):
                if not isinstance(value, str):
                    errors.append(f"{prefix}.bears_on[{bears_index}]: expected str")
    return errors


# Fold characters that filings render differently from how a model retypes a
# "verbatim" quote (curly quotes, primes, guillemets, the various dashes, and
# ellipsis). Whitespace (incl. NBSP, matched by \s in unicode mode) is collapsed
# separately, and matching is case-insensitive. This reduces false-negative
# drops of genuine quotes without weakening the substring requirement that blocks
# fabricated quotes.
_QUOTE_FOLD = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "‵": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "‶": '"',
    "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    "…": "...",
}
_QUOTE_TRANSLATION = str.maketrans(_QUOTE_FOLD)


def _normalize_quote_text(value: str) -> str:
    folded = value.translate(_QUOTE_TRANSLATION)
    return re.sub(r"\s+", " ", folded).strip().casefold()


def verify_quotes(claims: list[dict[str, Any]], source_text: str) -> tuple[list[dict[str, Any]], int]:
    """Keep only claims whose quote is found in the source text.

    Whitespace is normalized before matching so line wrapping in filings does
    not cause false negatives. The quote still needs to be copied from source
    text rather than paraphrased.
    """
    normalized_source = _normalize_quote_text(source_text)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for claim in claims:
        quote = claim.get("quote", "")
        normalized_quote = _normalize_quote_text(quote) if isinstance(quote, str) else ""
        if normalized_quote and normalized_quote in normalized_source:
            verified = dict(claim)
            verified["verified"] = True
            kept.append(verified)
        else:
            dropped += 1
    return kept, dropped


def extract_claims(
    source_text: str,
    adapter: Any,
    *,
    context: dict[str, Any],
    prompts_dir: Any,
    source_title: str = "",
    max_attempts: int = 2,
    max_source_chars: int = 60_000,
) -> dict[str, Any]:
    """Extract quote-backed claims from source text with deterministic quote verification."""
    prompt = render_claim_extraction_prompt(
        source_title=source_title,
        source_text=source_text,
        context=context,
        prompts_dir=prompts_dir,
        max_source_chars=max_source_chars,
    )
    response = adapter.complete(prompt)
    completion = complete_json_with_retry(adapter, response, prompt, validate_claims_shape, max_attempts)
    if completion.data is None:
        raise ValueError("claim extraction failed: " + "; ".join(completion.errors))

    kept, dropped = verify_quotes(completion.data["claims"], source_text)
    return {
        "claims": kept,
        "dropped_unverified": dropped,
        "attempts": completion.attempts,
    }


def claim_texts(claims: list[dict[str, Any]]) -> list[str]:
    """Return de-duplicated claim text values preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for claim in claims:
        text = str(claim.get("text", "")).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
