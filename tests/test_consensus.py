from __future__ import annotations

import unittest

from fundamental_research_engine.consensus import consensus_signal, constraint_terms


def _docs(*pairs):
    return [{"id": f"d{i}", "date": date, "text": text} for i, (date, text) in enumerate(pairs)]


class ConstraintTermsTest(unittest.TestCase):
    def test_explicit_terms_win(self) -> None:
        self.assertEqual(constraint_terms({"name": "Rack power", "terms": ["rack power", "cooling"]}), ["rack power", "cooling"])

    def test_falls_back_to_name(self) -> None:
        self.assertEqual(constraint_terms({"name": "Rack power"}), ["Rack power"])


class ConsensusSignalTest(unittest.TestCase):
    def test_low_and_flat_is_pre_consensus(self) -> None:
        docs = _docs(
            ("2025-01-01", "AI compute demand accelerates"),
            ("2025-04-01", "datacenter capex rising"),
            ("2025-07-01", "training clusters scale"),
            ("2025-10-01", "compute density increases"),
        )
        signal = consensus_signal(["rack power", "cooling"], docs)
        self.assertEqual(signal["recent_rate"], 0.0)
        self.assertEqual(signal["level"], "low")
        self.assertEqual(signal["trend"], "flat")
        self.assertTrue(signal["pre_consensus"])

    def test_rising_mentions_is_not_pre_consensus(self) -> None:
        docs = _docs(
            ("2025-01-01", "AI compute demand accelerates"),
            ("2025-04-01", "datacenter capex rising"),
            ("2026-01-01", "HBM shortage deepens, high bandwidth memory tight"),
            ("2026-06-01", "HBM dominates supply, high bandwidth memory pricing climbs"),
        )
        signal = consensus_signal(["hbm", "high bandwidth memory"], docs)
        self.assertEqual(signal["recent_rate"], 1.0)
        self.assertEqual(signal["trend"], "rising")
        self.assertFalse(signal["pre_consensus"])

    def test_empty_corpus_is_unknown(self) -> None:
        signal = consensus_signal(["rack power"], [])
        self.assertEqual(signal["level"], "unknown")
        self.assertFalse(signal["pre_consensus"])

    def test_matching_is_case_insensitive(self) -> None:
        docs = _docs(("2025-01-01", "RACK   Power delivery is constrained"), ("2025-06-01", "rack power tight"))
        signal = consensus_signal(["rack power"], docs)
        self.assertEqual(signal["recent_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
