from __future__ import annotations

import unittest
import urllib.error

from fundamental_research_engine.edgar import (
    _build_search_url,
    _parse_hit,
    _retry,
    filing_to_evidence,
    search_filings,
)


def _http_error(code):
    return urllib.error.HTTPError("url", code, "err", {}, None)

# Shape mirrors a real EFTS hit (verified against efts.sec.gov).
_HIT = {
    "_id": "0001039399-25-000023:form-20241228.htm",
    "_source": {
        "adsh": "0001039399-25-000023",
        "ciks": ["0001039399"],
        "display_names": ["FORMFACTOR INC  (FORM)  (CIK 0001039399)"],
        "form": "10-K",
        "root_forms": ["10-K"],
        "file_date": "2025-02-21",
        "period_ending": "2024-12-28",
    },
}


def _payload(hits):
    return {"hits": {"hits": hits}}


class ParseHitTest(unittest.TestCase):
    def test_parses_all_fields_and_builds_url(self) -> None:
        hit = _parse_hit(_HIT)
        self.assertEqual(hit["adsh"], "0001039399-25-000023")
        self.assertEqual(hit["cik"], "0001039399")
        self.assertEqual(hit["company"], "FORMFACTOR INC (FORM)")
        self.assertEqual(hit["form"], "10-K")
        self.assertEqual(hit["filed"], "2025-02-21")
        # CIK is int-normalized (leading zeros dropped) in the archives path
        self.assertEqual(
            hit["url"],
            "https://www.sec.gov/Archives/edgar/data/1039399/000103939925000023/form-20241228.htm",
        )

    def test_missing_fields_are_tolerated(self) -> None:
        hit = _parse_hit({"_id": "", "_source": {}})
        self.assertEqual(hit["url"], "")
        self.assertEqual(hit["form"], "")


class RetryTest(unittest.TestCase):
    def test_retries_transient_5xx_then_succeeds(self) -> None:
        attempts = []
        slept = []

        def op():
            attempts.append(1)
            if len(attempts) < 3:
                raise _http_error(500)
            return {"ok": True}

        result = _retry(op, retries=3, backoff=0.1, sleep=slept.append)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(slept), 2)  # slept between the two failures

    def test_4xx_is_not_retried(self) -> None:
        attempts = []

        def op():
            attempts.append(1)
            raise _http_error(404)

        with self.assertRaises(urllib.error.HTTPError):
            _retry(op, retries=3, backoff=0.1, sleep=lambda _: None)
        self.assertEqual(len(attempts), 1)  # raised immediately

    def test_gives_up_after_retries(self) -> None:
        attempts = []

        def op():
            attempts.append(1)
            raise _http_error(503)

        with self.assertRaises(urllib.error.HTTPError):
            _retry(op, retries=2, backoff=0.1, sleep=lambda _: None)
        self.assertEqual(len(attempts), 2)


class SearchFilingsTest(unittest.TestCase):
    def test_respects_limit(self) -> None:
        payload = _payload([_HIT, _HIT, _HIT])
        hits = search_filings("hbm", limit=2, http_get=lambda url: payload)
        self.assertEqual(len(hits), 2)

    def test_stops_when_page_not_full(self) -> None:
        calls = []

        def fake(url):
            calls.append(url)
            return _payload([_HIT])  # single hit < page size -> stop after one page

        hits = search_filings("hbm", limit=10, http_get=fake)
        self.assertEqual(len(hits), 1)
        self.assertEqual(len(calls), 1)

    def test_build_url_encodes_query_and_forms(self) -> None:
        url = _build_search_url('"high bandwidth memory"', ["10-K", "10-Q"], "2025-01-01", None, 0)
        self.assertIn("q=%22high+bandwidth+memory%22", url)
        self.assertIn("forms=10-K%2C10-Q", url)
        self.assertIn("startdt=2025-01-01", url)


class FilingToEvidenceTest(unittest.TestCase):
    def test_produces_evidence_shape(self) -> None:
        evidence = filing_to_evidence(_parse_hit(_HIT), evidence_id="S1")
        self.assertEqual(evidence["id"], "S1")
        self.assertEqual(evidence["source_type"], "regulatory_filing")
        self.assertEqual(evidence["date"], "2025-02-21")
        self.assertEqual(evidence["reliability"], "high")
        self.assertEqual(evidence["claims"], [])
        self.assertTrue(evidence["url"].startswith("https://www.sec.gov/Archives/"))


if __name__ == "__main__":
    unittest.main()
