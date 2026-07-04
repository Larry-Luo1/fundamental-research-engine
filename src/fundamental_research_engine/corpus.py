"""Auto-collect the consensus corpus (feeds the radar's gear C `--corpus`).

The consensus proxy measures how often each candidate constraint is mentioned
across a dated universe of documents. That universe should be a BROAD theme query
(e.g. "artificial intelligence accelerator", "data center") over time — NOT a
per-constraint query, or every document would mention the constraint and the signal
would be meaningless. Within that universe, `consensus_signal` then counts how often
each specific bottleneck ("rack power" vs "HBM") is discussed.

This builds the universe from EDGAR full-text search. Fetching each filing's text is
the heavy part; it is injectable (`fetch_text`) so it can be faked in tests and
offloaded/bounded in production. With no fetcher, documents fall back to their
title metadata (light, for wiring/smoke only — too thin for a real signal).
"""

from __future__ import annotations

from typing import Any, Callable

from .edgar import default_edgar_get, fetch_filing_text, search_filings

FetchText = Callable[[dict[str, Any]], str]


def _doc_id(hit: dict[str, Any]) -> str:
    parts = [hit.get("adsh", ""), hit.get("primary_doc", "")]
    joined = ":".join(p for p in parts if p)
    return joined or hit.get("url", "") or hit.get("adsh", "")


def build_corpus(
    query: str,
    *,
    forms: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 40,
    http_get: Callable[[str], Any] = default_edgar_get,
    fetch_text: FetchText | None = None,
    max_chars: int = 200_000,
) -> dict[str, Any]:
    """Search EDGAR for a broad theme query and assemble a dated document corpus.

    Returns `{query, count, documents:[{id, date, text, url, company, form}]}`,
    ready to serialize and hand to `fre radar --corpus` / a watchlist `corpus` field.
    """
    hits = search_filings(
        query, forms=forms, date_from=date_from, date_to=date_to, limit=limit, http_get=http_get
    )
    documents: list[dict[str, Any]] = []
    for hit in hits:
        text = ""
        if fetch_text is not None:
            try:
                text = fetch_text(hit) or ""
            except Exception:  # a single unreachable filing must not sink the corpus
                text = ""
        if not text:
            text = hit.get("title", "")
        if max_chars and len(text) > max_chars:
            text = text[:max_chars]
        documents.append(
            {
                "id": _doc_id(hit),
                "date": hit.get("filed", ""),
                "text": text,
                "url": hit.get("url", ""),
                "company": hit.get("company", ""),
                "form": hit.get("form", ""),
            }
        )
    return {"query": query, "count": len(documents), "documents": documents}


def default_fetch_text(hit: dict[str, Any]) -> str:
    """Real filing-text fetcher (heavy: one HTTP GET per filing)."""
    return fetch_filing_text(hit)
