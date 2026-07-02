from __future__ import annotations

import unittest
from types import SimpleNamespace

from fundamental_research_engine.models import Evidence
from fundamental_research_engine.quality import (
    build_grounding,
    build_quality_scorecard,
    validate_quality_review_shape,
)


def _valid_review():
    return {
        "lenses": {
            "premortem": {"findings": []},
            "steelman_bear": {"counter_thesis_strength": "moderate", "strongest_disconfirmers": [], "assessment": "ok"},
            "consistency": {"issues": []},
            "unsupported_claims": {"items": []},
        },
        "open_concerns": [{"severity": "high", "target": "thesis", "issue": "x", "suggested_fix": "y"}],
        "recommendation": "revise",
    }


def _ev(eid, source_type, url, reliability):
    return Evidence(id=eid, title=eid, source_type=source_type, date="2026-01-01", url=url, reliability=reliability)


def _owner(oid, name, evidence_ids):
    return SimpleNamespace(id=oid, name=name, evidence_ids=evidence_ids)


class GroundingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = [
            _ev("E1", "company_disclosure", "http://a", "high"),
            _ev("E2", "industry_research", "http://b", "medium"),
            _ev("E3", "company_disclosure", "http://c", "low"),
        ]

    def test_grounded_corroborated_thin_ungrounded(self) -> None:
        owners = {
            "bottleneck": [
                _owner("bn-a", "A", ["E1", "E2"]),  # 2 distinct sources -> corroborated, reliability high
                _owner("bn-b", "B", ["E3"]),        # single source -> thin
            ],
            "company": [
                _owner("co-c", "C", []),            # no evidence -> ungrounded
                _owner("co-d", "D", ["E1", "E1"]),  # same evidence twice -> single distinct source -> thin
            ],
        }
        g = build_grounding(self.evidence, owners)

        by_id = {o["id"]: o for o in g["owners"]}
        self.assertTrue(by_id["bn-a"]["grounded"] and by_id["bn-a"]["corroborated"])
        self.assertEqual(by_id["bn-a"]["reliability_max"], "high")
        self.assertEqual(by_id["bn-a"]["distinct_sources"], 2)
        self.assertFalse(by_id["bn-b"]["corroborated"])
        self.assertEqual(by_id["co-d"]["distinct_sources"], 1)
        self.assertFalse(by_id["co-c"]["grounded"])

        self.assertEqual(g["ungrounded"], ["co-c"])
        self.assertEqual(sorted(g["thin"]), ["bn-b", "co-d"])
        self.assertEqual(g["summary"], {"owners": 4, "grounded": 3, "corroborated": 1, "ungrounded": 1, "thin": 2})
        self.assertEqual(g["corroboration_ratio"], round(1 / 4, 2))
        # weighted coverage: high(1.0)+low(0.4)+0+high(1.0) = 2.4 / 4 = 0.6
        self.assertEqual(g["reliability_weighted_coverage"], 0.6)

    def test_empty_owners(self) -> None:
        g = build_grounding(self.evidence, {"bottleneck": [], "company": []})
        self.assertEqual(g["reliability_weighted_coverage"], 0.0)
        self.assertEqual(g["summary"]["owners"], 0)


class ScorecardTest(unittest.TestCase):
    def _grounding(self):
        evidence = [_ev("E1", "x", "http://a", "high"), _ev("E2", "y", "http://b", "high")]
        owners = {"bottleneck": [_owner("bn-a", "A", ["E1", "E2"]), _owner("co-b", "B", [])]}
        return build_grounding(evidence, owners)

    def test_scorecard_without_review(self) -> None:
        sc = build_quality_scorecard(self._grounding())
        self.assertIn("grounding_score", sc)
        self.assertFalse(sc["disconfirmation"]["premortem_done"])
        self.assertIsNone(sc["calibration"]["brier"])
        # ungrounded owner produces a flag
        self.assertTrue(any("no linked evidence" in f for f in sc["flags"]))
        self.assertIn("not a truth score", sc["note"])

    def test_scorecard_with_review(self) -> None:
        review = {
            "lenses": {"premortem": {}, "steelman_bear": {}},
            "open_concerns": [{"severity": "high", "issue": "unsupported ASP claim"}, {"severity": "medium", "issue": "x"}],
        }
        sc = build_quality_scorecard(self._grounding(), review=review)
        self.assertTrue(sc["disconfirmation"]["premortem_done"])
        self.assertTrue(sc["disconfirmation"]["steelman_done"])
        self.assertEqual(sc["disconfirmation"]["open_critical"], 1)
        self.assertEqual(sc["disconfirmation"]["open_major"], 1)
        self.assertTrue(any(f.startswith("critical:") for f in sc["flags"]))


class ReviewShapeTest(unittest.TestCase):
    def test_valid_review_passes(self) -> None:
        self.assertEqual(validate_quality_review_shape(_valid_review()), [])

    def test_missing_lens_flagged(self) -> None:
        review = _valid_review()
        del review["lenses"]["premortem"]
        errors = validate_quality_review_shape(review)
        self.assertTrue(any("lenses.premortem: missing" in e for e in errors))

    def test_bad_severity_and_recommendation(self) -> None:
        review = _valid_review()
        review["open_concerns"][0]["severity"] = "critical"
        review["recommendation"] = "maybe"
        errors = validate_quality_review_shape(review)
        self.assertTrue(any("severity: unknown value 'critical'" in e for e in errors))
        self.assertTrue(any("recommendation: unknown value 'maybe'" in e for e in errors))

    def test_non_dict_rejected(self) -> None:
        self.assertEqual(validate_quality_review_shape([]), ["quality_review: expected a JSON object"])


if __name__ == "__main__":
    unittest.main()
