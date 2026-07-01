from __future__ import annotations

import unittest

from fundamental_research_engine.critique import summarize_critique, validate_critique_shape


def _valid_critique() -> dict:
    return {
        "concerns": [
            {
                "severity": "medium",
                "field": "bottlenecks[0].scorecard.supplier_pricing_power",
                "issue": "The score isn't tied to a specific evidence claim.",
                "suggested_fix": "Cite the relevant evidence item.",
            }
        ],
        "overall_assessment": "Mostly solid, one dimension needs an evidence anchor.",
        "recommendation": "revise",
    }


class ValidateCritiqueShapeTest(unittest.TestCase):
    def test_valid_critique_has_no_errors(self) -> None:
        self.assertEqual(validate_critique_shape(_valid_critique()), [])

    def test_non_dict_rejected(self) -> None:
        self.assertEqual(validate_critique_shape(["not", "a", "dict"]), ["critique: expected a JSON object"])

    def test_missing_top_level_field(self) -> None:
        data = _valid_critique()
        del data["recommendation"]
        errors = validate_critique_shape(data)
        self.assertIn("critique.recommendation: missing", errors)

    def test_unexpected_top_level_field(self) -> None:
        data = _valid_critique()
        data["extra"] = 1
        errors = validate_critique_shape(data)
        self.assertIn("critique.extra: unexpected field", errors)

    def test_unknown_recommendation_value(self) -> None:
        data = _valid_critique()
        data["recommendation"] = "maybe"
        errors = validate_critique_shape(data)
        self.assertTrue(any("recommendation" in e for e in errors))

    def test_unknown_severity_value(self) -> None:
        data = _valid_critique()
        data["concerns"][0]["severity"] = "critical"
        errors = validate_critique_shape(data)
        self.assertTrue(any("severity" in e for e in errors))

    def test_missing_concern_field(self) -> None:
        data = _valid_critique()
        del data["concerns"][0]["suggested_fix"]
        errors = validate_critique_shape(data)
        self.assertIn("critique.concerns[0].suggested_fix: missing", errors)

    def test_empty_concerns_is_valid(self) -> None:
        data = _valid_critique()
        data["concerns"] = []
        data["recommendation"] = "accept"
        self.assertEqual(validate_critique_shape(data), [])


class SummarizeCritiqueTest(unittest.TestCase):
    def test_summarizes_recommendation_and_severity_counts(self) -> None:
        summary = summarize_critique(_valid_critique())
        self.assertEqual(summary, "recommendation=revise concerns=[medium=1]")

    def test_summarizes_no_concerns(self) -> None:
        data = _valid_critique()
        data["concerns"] = []
        data["recommendation"] = "accept"
        summary = summarize_critique(data)
        self.assertEqual(summary, "recommendation=accept concerns=[none]")


if __name__ == "__main__":
    unittest.main()
