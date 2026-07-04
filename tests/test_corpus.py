from __future__ import annotations

import unittest

from fundamental_research_engine.corpus import build_corpus

# Mirrors a real EFTS hit (see test_edgar).
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


class BuildCorpusTest(unittest.TestCase):
    def test_documents_carry_date_id_and_fetched_text(self) -> None:
        corpus = build_corpus(
            "artificial intelligence accelerator",
            limit=1,
            http_get=lambda url: _payload([_HIT]),
            fetch_text=lambda hit: "HBM and high bandwidth memory discussed; rack power noted.",
        )
        self.assertEqual(corpus["count"], 1)
        doc = corpus["documents"][0]
        self.assertEqual(doc["date"], "2025-02-21")
        self.assertEqual(doc["id"], "0001039399-25-000023:form-20241228.htm")
        self.assertIn("high bandwidth memory", doc["text"])
        self.assertTrue(doc["url"].endswith("form-20241228.htm"))
        self.assertEqual(doc["form"], "10-K")

    def test_falls_back_to_title_without_fetcher(self) -> None:
        corpus = build_corpus("ai", limit=1, http_get=lambda url: _payload([_HIT]))
        doc = corpus["documents"][0]
        self.assertIn("FORMFACTOR", doc["text"])  # title metadata
        self.assertIn("10-K", doc["text"])

    def test_fetch_error_falls_back_to_title(self) -> None:
        def boom(hit):
            raise RuntimeError("unreachable")

        corpus = build_corpus("ai", limit=1, http_get=lambda url: _payload([_HIT]), fetch_text=boom)
        self.assertIn("FORMFACTOR", corpus["documents"][0]["text"])

    def test_max_chars_truncates(self) -> None:
        corpus = build_corpus(
            "ai", limit=1, http_get=lambda url: _payload([_HIT]),
            fetch_text=lambda hit: "x" * 500, max_chars=100,
        )
        self.assertEqual(len(corpus["documents"][0]["text"]), 100)

    def test_feeds_consensus_signal(self) -> None:
        # end-to-end: a built corpus is directly consumable by the consensus proxy
        from fundamental_research_engine.consensus import consensus_signal

        hits = [dict(_HIT, _id=f"a{i}:doc.htm") for i in range(4)]
        texts = ["ai compute", "ai capex", "HBM tight, high bandwidth memory", "HBM dominates"]
        corpus = build_corpus(
            "ai", limit=4,
            http_get=lambda url: _payload(hits),
            fetch_text=lambda hit: texts.pop(0),
        )
        signal = consensus_signal(["hbm", "high bandwidth memory"], corpus["documents"])
        self.assertEqual(signal["trend"], "rising")


if __name__ == "__main__":
    unittest.main()
