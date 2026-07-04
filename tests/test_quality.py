from __future__ import annotations

import unittest
from types import SimpleNamespace

from fundamental_research_engine.models import Evidence
from fundamental_research_engine.quality import (
    build_causal_quality,
    build_grounding,
    build_quality_status,
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


def _ev(eid, source_type, url, reliability, claims=None):
    return Evidence(
        id=eid,
        title=eid,
        source_type=source_type,
        date="2026-01-01",
        url=url,
        reliability=reliability,
        claims=claims or [],
    )


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

    def test_scorecard_includes_causal_quality_flags(self) -> None:
        causal_quality = {
            "edges": [],
            "summary": {"edges": 0},
            "flags": ["causal edge 'edge-a' lacks quote-verified provenance for: E1.C1"],
        }
        sc = build_quality_scorecard(self._grounding(), causal_quality=causal_quality)
        self.assertEqual(sc["causal_quality"], causal_quality)
        self.assertTrue(any("lacks quote-verified provenance" in f for f in sc["flags"]))

    def test_quality_status_tiers(self) -> None:
        grounding = self._grounding()
        causal_quality = {
            "edges": [],
            "summary": {
                "edges": 2,
                "supported": 2,
                "fully_quote_verified": 2,
                "thin": 0,
                "low_confidence": 0,
                "missing_claims": 0,
                "weak_evidence": 0,
            },
            "flags": [],
        }
        status = build_quality_status(
            0.7,
            grounding,
            causal_quality,
            [],
            {"open_critical": 0, "open_major": 0},
        )
        self.assertEqual(status["tier"], "multi-source causal map")
        self.assertIn("quote-verified", status["satisfied"])


class CausalQualityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = [
            _ev("E1", "company_disclosure", "http://a", "high", ["A claim"]),
            _ev("E2", "industry_research", "http://b", "medium", ["B claim"]),
            _ev("E3", "blog", "http://c", "low", ["C claim"]),
        ]

    def test_flags_missing_quote_provenance_single_source_and_low_confidence(self) -> None:
        edge = SimpleNamespace(id="edge-a", confidence="low", claim_ids=["E1.C1"])
        cq = build_causal_quality([edge], self.evidence)

        self.assertEqual(cq["summary"]["edges"], 1)
        self.assertEqual(cq["summary"]["supported"], 1)
        self.assertEqual(cq["summary"]["fully_quote_verified"], 0)
        self.assertEqual(cq["summary"]["thin"], 1)
        self.assertEqual(cq["summary"]["low_confidence"], 1)
        self.assertTrue(any("lacks quote-verified provenance" in f for f in cq["flags"]))
        self.assertTrue(any("supported by a single source" in f for f in cq["flags"]))
        self.assertTrue(any("low confidence" in f for f in cq["flags"]))

    def test_quote_verified_two_source_edge_passes_core_checks(self) -> None:
        edge = SimpleNamespace(id="edge-b", confidence="high", claim_ids=["E1.C1", "E2.C1"])
        provenance = [
            {"claim_id": "E1.C1", "verified": True, "quote": "A claim"},
            {"claim_id": "E2.C1", "verified": True, "quote": "B claim"},
        ]
        cq = build_causal_quality([edge], self.evidence, provenance)

        edge_report = cq["edges"][0]
        self.assertEqual(cq["summary"]["fully_quote_verified"], 1)
        self.assertEqual(edge_report["distinct_sources"], 2)
        self.assertFalse(edge_report["thin"])
        self.assertFalse(edge_report["weak_evidence"])
        self.assertEqual(cq["flags"], [])

    def test_candidate_claim_can_be_resolved_from_sidecar(self) -> None:
        edge = SimpleNamespace(id="edge-q", confidence="medium", claim_ids=["E1.Q1"])
        provenance = [
            {
                "claim_id": "E1.Q1",
                "evidence_id": "E1",
                "claim": "candidate",
                "source_type": "company_disclosure",
                "reliability": "high",
                "source_url": "http://a",
                "verified": True,
                "quote": "candidate",
            }
        ]
        cq = build_causal_quality([edge], self.evidence, provenance)

        self.assertEqual(cq["edges"][0]["resolved_claim_ids"], ["E1.Q1"])
        self.assertEqual(cq["summary"]["missing_claims"], 0)
        self.assertEqual(cq["summary"]["fully_quote_verified"], 1)

    def test_missing_candidate_claim_is_flagged(self) -> None:
        edge = SimpleNamespace(id="edge-missing", confidence="medium", claim_ids=["E1.Q1"])
        cq = build_causal_quality([edge], self.evidence)

        self.assertEqual(cq["summary"]["missing_claims"], 1)
        self.assertTrue(any("missing claim ids: E1.Q1" in f for f in cq["flags"]))


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
