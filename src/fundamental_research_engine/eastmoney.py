"""Eastmoney (东方财富) fundamentals — keyless market-data snapshots for A-share,
Hong Kong, and US securities.

The "AkShare-style" fundamentals layer, built stdlib-only (no akshare/pandas) by
calling Eastmoney's public keyless JSON endpoints directly. Resolves a company
name or ticker to a security, then pulls a delayed quote snapshot (market cap,
P/E, P/B) and returns it as an evidence-shaped record — the numeric input the
financial-analysis skills (comps, DCF) need, on the same evidence rail as
:mod:`edgar` and :mod:`cninfo`.

A snapshot is dated market data, so ``source_type`` is ``market_data`` and the
caller supplies the ``as_of`` date. HTTP is injectable so tests never hit the
network; the real getter carries a browser User-Agent + Referer and a throttle.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

SEARCH_URL = "https://searchadapter.eastmoney.com/api/suggest/get"
QUOTE_URL = "https://push2delay.eastmoney.com/api/qt/stock/get"
QUOTE_PAGE_BASE = "https://quote.eastmoney.com"
# Public static token used by Eastmoney's own web quote pages.
DEFAULT_UT = "fa5fd1943c7b386f172d6893dbfba10b"
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; fundamental-research-engine/0.1)"
_MAX_RPS = 8.0
# MktNum -> quote.eastmoney.com URL prefix for the common markets.
_MKT_PREFIX = {"0": "sz", "1": "sh", "116": "hk", "105": "us", "106": "us", "107": "us"}

HttpGet = Callable[[str], Any]

_last_call = [0.0]


def _throttle() -> None:
    interval = 1.0 / _MAX_RPS
    wait = interval - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()


def default_em_get(url: str, timeout: float = 15.0) -> Any:
    """Rate-limited JSON GET against Eastmoney with a browser UA + Referer."""
    _throttle()
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _secid(mkt_num: str, code: str) -> str:
    return f"{mkt_num}.{code}" if mkt_num != "" and code else ""


def search_security(query: str, *, http_get: HttpGet = default_em_get) -> dict[str, Any] | None:
    """Resolve a name or ticker to the best-matching security (or None)."""
    url = f"{SEARCH_URL}?{urllib.parse.urlencode({'input': query, 'type': '14', 'count': '5'})}"
    payload = http_get(url)
    rows = (((payload or {}).get("QuotationCodeTable") or {}).get("Data")) if isinstance(payload, dict) else None
    rows = rows or []
    if not rows:
        return None
    row = rows[0]
    code = row.get("Code", "")
    mkt_num = str(row.get("MktNum", ""))
    return {
        "code": code,
        "name": row.get("Name", ""),
        "mkt_num": mkt_num,
        "secid": _secid(mkt_num, code),
        "classify": row.get("Classify", ""),
        "type_name": row.get("SecurityTypeName", ""),
    }


def _quote_page_url(hit: dict[str, Any]) -> str:
    prefix = _MKT_PREFIX.get(str(hit.get("mkt_num", "")))
    code = hit.get("code", "")
    if not code:
        return ""
    if prefix in ("sz", "sh"):
        return f"{QUOTE_PAGE_BASE}/{prefix}{code}.html"
    if prefix == "hk":
        return f"{QUOTE_PAGE_BASE}/hk/{code}.html"
    if prefix == "us":
        return f"{QUOTE_PAGE_BASE}/us/{code}.html"
    return f"{QUOTE_PAGE_BASE}/{code}.html"


def quote(secid: str, *, http_get: HttpGet = default_em_get, ut: str = DEFAULT_UT) -> dict[str, Any]:
    """Fetch a delayed quote snapshot; return normalized numeric fields (or {})."""
    params = {"ut": ut, "fltt": "2", "invt": "2", "secid": secid,
              "fields": "f43,f57,f58,f116,f117,f162,f167"}
    payload = http_get(f"{QUOTE_URL}?{urllib.parse.urlencode(params)}")
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not data:
        return {}
    return {
        "code": data.get("f57", ""),
        "name": data.get("f58", ""),
        "price": data.get("f43"),
        "total_market_cap": data.get("f116"),
        "circulating_market_cap": data.get("f117"),
        "pe_ttm": data.get("f162"),
        "pb": data.get("f167"),
    }


def _metric_claims(q: dict[str, Any]) -> list[str]:
    labels = [
        ("price", "price"),
        ("total_market_cap", "total market cap"),
        ("circulating_market_cap", "circulating market cap"),
        ("pe_ttm", "PE(TTM)"),
        ("pb", "PB"),
    ]
    return [f"{label} {q[key]}" for key, label in labels if q.get(key) not in (None, "", "-")]


def security_to_evidence(
    hit: dict[str, Any],
    q: dict[str, Any],
    *,
    as_of: str,
    evidence_id: str,
    reliability: str = "high",
) -> dict[str, Any]:
    """Convert a resolved security + quote snapshot into an evidence-shaped record."""
    name = q.get("name") or hit.get("name", "")
    code = q.get("code") or hit.get("code", "")
    label = f"{name}({code})" if code else name
    return {
        "id": evidence_id,
        "title": f"{label} market snapshot as of {as_of}".strip(),
        "source_type": "market_data",
        "date": as_of,
        "url": _quote_page_url(hit),
        "reliability": reliability,
        "claims": _metric_claims(q),
    }
