"""SEC EDGAR source discovery — keyless full-text search over real filings.

Closes the "no source discovery" gap: instead of hand-authored or
model-hallucinated URLs, find real primary filings via SEC's public,
authentication-free JSON API and hand them back as evidence-shaped records that
slot straight into the existing pipeline / audit / grounding layers.

Compliance (SEC policy): a descriptive User-Agent with a contact is required and
requests are rate-limited to <=10/s. HTTP is injectable so tests never hit the
network; the real getter carries the UA and a simple throttle.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

from .evidence import FetchResult, default_fetch

EFTS_SEARCH = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_SEC_USER_AGENT = "fundamental-research-engine/0.1 (set FRE_SEC_USER_AGENT to your name and email)"
_MAX_RPS = 8.0
_PAGE_SIZE = 10
_MAX_PAGES = 10

HttpGet = Callable[[str], Any]
Fetcher = Callable[[str], FetchResult]

_last_call = [0.0]


def _sec_user_agent() -> str:
    return os.environ.get("FRE_SEC_USER_AGENT", "").strip() or DEFAULT_SEC_USER_AGENT


def _throttle() -> None:
    interval = 1.0 / _MAX_RPS
    wait = interval - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()


def default_edgar_get(url: str, timeout: float = 15.0) -> Any:
    """Rate-limited JSON GET against EDGAR with the SEC-required User-Agent."""
    _throttle()
    request = urllib.request.Request(url, headers={"User-Agent": _sec_user_agent(), "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _build_search_url(query: str, forms: list[str] | None, date_from: str | None, date_to: str | None, offset: int) -> str:
    params: dict[str, str] = {"q": query}
    if forms:
        params["forms"] = ",".join(forms)
    if date_from:
        params["startdt"] = date_from
    if date_to:
        params["enddt"] = date_to
    if offset:
        params["from"] = str(offset)
    return f"{EFTS_SEARCH}?{urllib.parse.urlencode(params)}"


def _clean_company(display_name: str) -> str:
    # "FORMFACTOR INC  (FORM)  (CIK 0001039399)" -> "FORMFACTOR INC (FORM)"
    name = re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", display_name)
    return re.sub(r"\s{2,}", " ", name).strip()


def _parse_hit(hit: dict[str, Any]) -> dict[str, Any]:
    source = hit.get("_source", {})
    hit_id = hit.get("_id", "")
    primary_doc = hit_id.split(":", 1)[1] if ":" in hit_id else ""

    adsh = source.get("adsh") or (hit_id.split(":", 1)[0] if hit_id else "")
    ciks = source.get("ciks") or []
    cik = ciks[0] if ciks else ""
    if not cik:
        match = re.search(r"CIK\s*(\d+)", " ".join(source.get("display_names", [])))
        cik = match.group(1) if match else ""

    display_names = source.get("display_names") or []
    company = _clean_company(display_names[0]) if display_names else ""
    root_forms = source.get("root_forms") or []
    form = source.get("form") or (root_forms[0] if root_forms else "")
    filed = source.get("file_date", "")

    url = ""
    if cik and adsh and primary_doc:
        try:
            cik_int = int(cik)
            url = f"{ARCHIVES_BASE}/{cik_int}/{adsh.replace('-', '')}/{primary_doc}"
        except ValueError:
            url = ""

    title_bits = [b for b in [company, form, f"filed {filed}" if filed else ""] if b]
    return {
        "adsh": adsh,
        "cik": cik,
        "company": company,
        "form": form,
        "filed": filed,
        "period_ending": source.get("period_ending", ""),
        "primary_doc": primary_doc,
        "title": " ".join(title_bits),
        "url": url,
    }


def search_filings(
    query: str,
    *,
    forms: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
    http_get: HttpGet = default_edgar_get,
) -> list[dict[str, Any]]:
    """Full-text search EDGAR filings; return normalized hits (newest first as EDGAR returns)."""
    collected: list[dict[str, Any]] = []
    offset = 0
    for _ in range(_MAX_PAGES):
        payload = http_get(_build_search_url(query, forms, date_from, date_to, offset))
        hits = (payload or {}).get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
        if not hits:
            break
        for hit in hits:
            collected.append(_parse_hit(hit))
            if len(collected) >= limit:
                return collected
        if len(hits) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return collected


def filing_to_evidence(hit: dict[str, Any], *, evidence_id: str, reliability: str = "high") -> dict[str, Any]:
    """Convert a normalized hit into an evidence-shaped record (same shape as theme evidence)."""
    return {
        "id": evidence_id,
        "title": hit.get("title") or hit.get("company") or hit.get("adsh", evidence_id),
        "source_type": "regulatory_filing",
        "date": hit.get("filed", ""),
        "url": hit.get("url", ""),
        "reliability": reliability,
        "claims": [],
    }


def fetch_filing_text(hit: dict[str, Any], fetch: Fetcher = default_fetch) -> str:
    """Fetch a filing's primary document text (for downstream claim extraction)."""
    url = hit.get("url", "")
    if not url:
        return ""
    result = fetch(url)
    return result.text or "" if result.ok else ""
