"""cninfo (巨潮资讯网) source discovery — keyless full-text search over official
China A-share / H-share disclosures.

The China-market counterpart to :mod:`edgar`. cninfo is the CSRC-designated
official disclosure platform for Shenzhen- and Shanghai-listed companies, so its
announcements are primary regulatory filings — the same evidence tier EDGAR
gives for US filings. This closes the "US-only source discovery" gap for the
China/global research universe without any paid data subscription.

The public query endpoint is authentication-free JSON over HTTP POST. HTTP is
injectable so tests never hit the network; the real poster carries a browser
User-Agent and a simple <=8/s throttle, matching :mod:`edgar`.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

from .evidence import FetchResult, default_fetch

CNINFO_QUERY = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_BASE = "http://static.cninfo.com.cn/"
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; fundamental-research-engine/0.1)"
_MAX_RPS = 8.0
_PAGE_SIZE = 30
_MAX_PAGES = 10
_BEIJING_OFFSET = 8 * 3600  # announcementTime is Beijing midnight (UTC+8)

HttpPost = Callable[[str, dict], Any]
Fetcher = Callable[[str], FetchResult]

_last_call = [0.0]


def _throttle() -> None:
    interval = 1.0 / _MAX_RPS
    wait = interval - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()


def default_cninfo_post(url: str, data: dict, timeout: float = 15.0) -> Any:
    """Rate-limited form-encoded JSON POST against cninfo with a browser UA."""
    _throttle()
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _strip_em(title: str) -> str:
    # cninfo wraps matched terms in <em>…</em> highlight tags; strip them.
    return re.sub(r"</?em>", "", title or "").strip()


def _ms_to_date(ms: Any) -> str:
    try:
        seconds = int(ms) / 1000.0
    except (TypeError, ValueError):
        return ""
    return time.strftime("%Y-%m-%d", time.gmtime(seconds + _BEIJING_OFFSET))


def _announcement_url(adjunct_url: str) -> str:
    adjunct_url = (adjunct_url or "").lstrip("/")
    return f"{STATIC_BASE}{adjunct_url}" if adjunct_url else ""


def _parse_announcement(ann: dict[str, Any]) -> dict[str, Any]:
    code = ann.get("secCode", "")
    name = ann.get("secName", "")
    headline = _strip_em(ann.get("announcementTitle", ""))
    date = _ms_to_date(ann.get("announcementTime"))
    title_bits = [b for b in [f"{name}({code})" if code else name, headline] if b]
    return {
        "code": code,
        "name": name,
        "headline": headline,
        "date": date,
        "url": _announcement_url(ann.get("adjunctUrl", "")),
        "org_id": ann.get("orgId", ""),
        "announcement_id": ann.get("announcementId", ""),
        "title": " ".join(title_bits),
    }


def search_announcements(
    query: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
    column: str = "szse",
    http_post: HttpPost = default_cninfo_post,
) -> list[dict[str, Any]]:
    """Full-text search cninfo disclosures; return normalized hits (newest first).

    ``column`` selects the query backend; cninfo's full-text tab returns
    cross-market results regardless, so the default ``"szse"`` covers both
    Shenzhen- and Shanghai-listed issuers. ``date_from``/``date_to`` are only
    applied when both are given (cninfo expects a closed ``start~end`` range).
    """
    se_date = f"{date_from}~{date_to}" if date_from and date_to else ""
    collected: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        data = {
            "pageNum": str(page),
            "pageSize": str(_PAGE_SIZE),
            "column": column,
            "tabName": "fulltext",
            "searchkey": query,
            "seDate": se_date,
            "isHLtitle": "true",
        }
        payload = http_post(CNINFO_QUERY, data)
        announcements = (payload or {}).get("announcements") if isinstance(payload, dict) else None
        announcements = announcements or []
        if not announcements:
            break
        for ann in announcements:
            collected.append(_parse_announcement(ann))
            if len(collected) >= limit:
                return collected
        if len(announcements) < _PAGE_SIZE:
            break
    return collected


def announcement_to_evidence(hit: dict[str, Any], *, evidence_id: str, reliability: str = "high") -> dict[str, Any]:
    """Convert a normalized hit into an evidence-shaped record (theme evidence shape)."""
    return {
        "id": evidence_id,
        "title": hit.get("title") or hit.get("headline") or hit.get("name", evidence_id),
        "source_type": "regulatory_filing",
        "date": hit.get("date", ""),
        "url": hit.get("url", ""),
        "reliability": reliability,
        "claims": [],
    }


def fetch_announcement_text(hit: dict[str, Any], fetch: Fetcher = default_fetch) -> str:
    """Fetch an announcement's document text (for downstream claim extraction).

    Note: cninfo adjuncts are usually PDFs, which the stdlib HTML fetcher cannot
    parse into clean text. The official ``headline`` on the evidence record is
    itself a verifiable, quote-usable string; full-body PDF extraction is a
    separate step (out of scope for the zero-dependency core).
    """
    url = hit.get("url", "")
    if not url:
        return ""
    result = fetch(url)
    return result.text or "" if result.ok else ""
