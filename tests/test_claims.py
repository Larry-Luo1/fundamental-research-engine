from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from fundamental_research_engine.claims import (
    claim_texts,
    extract_claims,
    validate_claims_shape,
    verify_quotes,
)


class ClaimsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.prompts_dir = self.project_root / "prompts"

    def test_validate_claims_shape_rejects_missing_and_bad_values(self) -> None:
        errors = validate_claims_shape(
            {
                "claims": [
                    {
                        "text": "HBM demand is rising.",
                        "quote": "HBM demand is rising.",
                        "confidence": "certain",
                        "extra": "not allowed",
                    }
                ]
            }
        )

        self.assertIn("claims.claims[0].confidence: unknown value 'certain'", errors)
        self.assertIn("claims.claims[0].bears_on: missing", errors)
        self.assertIn("claims.claims[0].extra: unexpected field", errors)

    def test_verify_quotes_keeps_only_verbatim_source_quotes(self) -> None:
        source_text = "HBM supply is constrained by\nqualification delays. Pricing remains firm."
        claims = [
            {
                "text": "HBM supply is constrained by qualification delays.",
                "quote": "HBM supply is constrained by qualification delays.",
                "confidence": "high",
                "bears_on": ["thesis"],
            },
            {
                "text": "Capacity is unlimited.",
                "quote": "capacity is unlimited",
                "confidence": "low",
                "bears_on": ["thesis"],
            },
        ]

        kept, dropped = verify_quotes(claims, source_text)

        self.assertEqual(dropped, 1)
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0]["verified"])
        self.assertEqual(kept[0]["text"], "HBM supply is constrained by qualification delays.")

    def test_extract_claims_retries_shape_errors_and_drops_unverified_quotes(self) -> None:
        source_text = "Customers signed long-term agreements for HBM capacity."
        adapter = Mock()
        adapter.complete.side_effect = [
            json.dumps(
                {
                    "claims": [
                        {
                            "text": "Bad confidence value.",
                            "quote": "Customers signed long-term agreements",
                            "confidence": "certain",
                            "bears_on": ["thesis"],
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    "claims": [
                        {
                            "text": "Customers signed long-term agreements for HBM capacity.",
                            "quote": "Customers signed long-term agreements for HBM capacity.",
                            "confidence": "high",
                            "bears_on": ["thesis"],
                        },
                        {
                            "text": "HBM capacity is immediately abundant.",
                            "quote": "HBM capacity is immediately abundant.",
                            "confidence": "low",
                            "bears_on": ["thesis"],
                        },
                    ]
                }
            ),
        ]

        result = extract_claims(
            source_text,
            adapter,
            context={"theme": {"id": "demo"}, "owners": {"thesis": [{"id": "thesis"}]}},
            prompts_dir=self.prompts_dir,
            max_attempts=2,
        )

        self.assertEqual(adapter.complete.call_count, 2)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["dropped_unverified"], 1)
        self.assertEqual(
            claim_texts(result["claims"]),
            ["Customers signed long-term agreements for HBM capacity."],
        )


if __name__ == "__main__":
    unittest.main()
