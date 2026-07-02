from __future__ import annotations

import unittest
from types import SimpleNamespace

from fundamental_research_engine.calibration import (
    build_calibration,
    extract_predictions,
    prediction_key,
    register_predictions,
    resolve_prediction,
)


def _theme():
    return SimpleNamespace(
        id="demo",
        as_of="2026-07-01",
        tracking_signals=["ASP rises", "capacity sold out"],
        counter_theses=["capacity catches up"],
        scenarios=[SimpleNamespace(triggers=["inventory builds", ""])],
    )


class ExtractTest(unittest.TestCase):
    def test_extracts_all_kinds_and_skips_blank(self) -> None:
        preds = extract_predictions(_theme())
        kinds = sorted({p["kind"] for p in preds})
        self.assertEqual(kinds, ["counter_thesis", "scenario_trigger", "tracking_signal"])
        # 2 signals + 1 counter + 1 non-blank trigger = 4 (blank trigger skipped)
        self.assertEqual(len(preds), 4)
        self.assertTrue(all(p["registered_as_of"] == "2026-07-01" for p in preds))

    def test_register_is_idempotent(self) -> None:
        record = register_predictions({"predictions": []}, _theme())
        again = register_predictions(record, _theme())
        self.assertEqual(len(record["predictions"]), len(again["predictions"]))


class BuildCalibrationTest(unittest.TestCase):
    def test_counts_and_brier(self) -> None:
        record = {
            "theme_id": "demo",
            "predictions": [
                {"key": "a", "kind": "tracking_signal", "statement": "s1", "registered_as_of": "2026-01-01",
                 "probability": 0.8, "resolved": True, "outcome": True, "resolved_as_of": "2026-06-01"},
                {"key": "b", "kind": "tracking_signal", "statement": "s2", "registered_as_of": "2026-01-01",
                 "probability": 0.3, "resolved": True, "outcome": False, "resolved_as_of": "2026-06-01"},
                {"key": "c", "kind": "counter_thesis", "statement": "s3", "registered_as_of": "2026-04-01",
                 "probability": None, "resolved": False, "outcome": None, "resolved_as_of": None},
            ],
        }
        cal = build_calibration(record)
        self.assertEqual(cal["predictions"], 3)
        self.assertEqual(cal["resolved"], 2)
        self.assertEqual(cal["open"], 1)
        self.assertEqual(cal["resolved_true"], 1)
        self.assertEqual(cal["track_record_runs"], 2)
        # (0.8-1)^2 + (0.3-0)^2 = 0.04 + 0.09 = 0.13 / 2 = 0.065
        self.assertEqual(cal["brier"], 0.065)

    def test_no_scored_predictions_gives_null_brier(self) -> None:
        cal = build_calibration({"predictions": []})
        self.assertIsNone(cal["brier"])
        self.assertEqual(cal["resolution_rate"], 0.0)

    def test_resolve_prediction(self) -> None:
        record = register_predictions({"predictions": []}, _theme())
        key = record["predictions"][0]["key"]
        self.assertTrue(resolve_prediction(record, key, True, "2026-06-01"))
        self.assertFalse(resolve_prediction(record, "nonexistent", True, "2026-06-01"))
        self.assertTrue(record["predictions"][0]["resolved"])
        self.assertEqual(record["predictions"][0]["key"], prediction_key("tracking_signal", "ASP rises"))


if __name__ == "__main__":
    unittest.main()
