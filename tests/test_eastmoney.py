from __future__ import annotations

import unittest

from fundamental_research_engine.eastmoney import (
    _quote_page_url,
    quote,
    search_security,
    security_to_evidence,
)

# Shapes mirror real Eastmoney responses (verified live 2026-07-08).
_SEARCH = {
    "QuotationCodeTable": {
        "Data": [
            {"Code": "300750", "Name": "宁德时代", "MktNum": "0", "Classify": "AStock", "SecurityTypeName": "深A"}
        ]
    }
}
_QUOTE = {
    "rc": 0,
    "data": {"f43": 361.0, "f57": "300750", "f58": "宁德时代", "f169": -2.5, "f170": -0.69,
             "f116": 1670220960821.0, "f117": 1536789898891.0, "f162": 20.14, "f167": 5.11},
}
# Futures snapshot: equity-only fields come back as "-" and must be dropped.
_FUT_QUOTE = {
    "rc": 0,
    "data": {"f43": 102850.0, "f57": "cum", "f58": "沪铜主连", "f169": -110.0, "f170": -0.11,
             "f116": "-", "f117": "-", "f162": "-", "f167": "-"},
}


class SearchSecurityTest(unittest.TestCase):
    def test_resolves_best_hit_and_secid(self) -> None:
        hit = search_security("宁德时代", http_get=lambda url: _SEARCH)
        self.assertEqual(hit["code"], "300750")
        self.assertEqual(hit["name"], "宁德时代")
        self.assertEqual(hit["mkt_num"], "0")
        self.assertEqual(hit["secid"], "0.300750")

    def test_no_match_returns_none(self) -> None:
        self.assertIsNone(search_security("zzz", http_get=lambda url: {"QuotationCodeTable": {"Data": []}}))


class QuoteTest(unittest.TestCase):
    def test_parses_numeric_fields(self) -> None:
        q = quote("0.300750", http_get=lambda url: _QUOTE)
        self.assertEqual(q["name"], "宁德时代")
        self.assertEqual(q["total_market_cap"], 1670220960821.0)
        self.assertEqual(q["pe_ttm"], 20.14)
        self.assertEqual(q["pb"], 5.11)

    def test_empty_payload_is_tolerated(self) -> None:
        self.assertEqual(quote("0.300750", http_get=lambda url: {"data": None}), {})

    def test_futures_snapshot_keeps_price_change_drops_equity_fields(self) -> None:
        q = quote("113.cum", http_get=lambda url: _FUT_QUOTE)
        self.assertEqual(q["name"], "沪铜主连")
        self.assertEqual(q["price"], 102850.0)
        self.assertEqual(q["change"], -110.0)
        ev = security_to_evidence({"mkt_num": "113", "code": "cum", "name": "沪铜主连"}, q,
                                   as_of="2026-07-08", evidence_id="S1")
        self.assertIn("price 102850.0", ev["claims"])
        self.assertIn("change -110.0", ev["claims"])
        # Equity-only "-" fields are filtered out of the metric claims.
        self.assertFalse(any("PE(TTM)" in c or "market cap" in c for c in ev["claims"]))


class QuotePageUrlTest(unittest.TestCase):
    def test_market_prefixes(self) -> None:
        self.assertEqual(_quote_page_url({"mkt_num": "0", "code": "300750"}), "https://quote.eastmoney.com/sz300750.html")
        self.assertEqual(_quote_page_url({"mkt_num": "1", "code": "600519"}), "https://quote.eastmoney.com/sh600519.html")
        self.assertEqual(_quote_page_url({"mkt_num": "116", "code": "00700"}), "https://quote.eastmoney.com/hk/00700.html")
        self.assertEqual(_quote_page_url({"mkt_num": "105", "code": "AAPL"}), "https://quote.eastmoney.com/us/AAPL.html")


class SecurityToEvidenceTest(unittest.TestCase):
    def test_evidence_shape_and_metric_claims(self) -> None:
        hit = search_security("宁德时代", http_get=lambda url: _SEARCH)
        q = quote("0.300750", http_get=lambda url: _QUOTE)
        ev = security_to_evidence(hit, q, as_of="2026-07-08", evidence_id="S1")
        self.assertEqual(ev["id"], "S1")
        self.assertEqual(ev["source_type"], "market_data")
        self.assertEqual(ev["date"], "2026-07-08")
        self.assertEqual(ev["url"], "https://quote.eastmoney.com/sz300750.html")
        self.assertIn("宁德时代(300750)", ev["title"])
        self.assertIn("PE(TTM) 20.14", ev["claims"])
        self.assertIn("PB 5.11", ev["claims"])


if __name__ == "__main__":
    unittest.main()
