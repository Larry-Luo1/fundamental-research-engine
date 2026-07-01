from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.diff import diff_analysis, find_runs_for_theme, has_changes


def _base_analysis() -> dict:
    return {
        "theme": {
            "id": "demo",
            "title": "Demo Theme",
            "as_of": "2026-01-01",
            "theme_type": "technology_adoption",
            "domain": "ai",
            "core_question": "Is this a bottleneck?",
            "thesis": "Initial thesis.",
            "mechanism": "Initial mechanism.",
            "hype_stage": "trigger",
            "technology_readiness_level": 4,
            "drivers": ["driver a"],
        },
        "bottleneck_scores": [
            {
                "name": "B1",
                "score": 3.0,
                "rating": "clear",
                "positive_score": 3.5,
                "risk_penalty": 1.0,
                "dimensions": {},
            }
        ],
        "segments": [
            {
                "name": "S1",
                "layer": "l",
                "role": "r",
                "beneficiary_class": "first-order",
                "representative_companies": [],
            }
        ],
        "profit_pools": [
            {"name": "P1", "rationale": "r1", "capture_quality": "high", "beneficiaries": []}
        ],
        "companies": [
            {
                "name": "C1",
                "product": "p",
                "stack_position": "s",
                "positioning_label": "qualified leader",
                "exposure_quality": "e",
                "moat": [],
                "risks": [],
                "evidence_ids": [],
            }
        ],
        "scenarios": [{"name": "bull", "description": "d", "implications": [], "triggers": []}],
        "evidence": [
            {
                "id": "E1",
                "title": "t",
                "source_type": "s",
                "date": "2026-01-01",
                "url": "",
                "reliability": "high",
                "claims": [],
            }
        ],
        "evidence_coverage": {},
        "counter_theses": ["risk one"],
        "tracking_signals": ["signal one"],
    }


class DiffTest(unittest.TestCase):
    def test_no_changes(self) -> None:
        old = _base_analysis()
        new = _base_analysis()
        report = diff_analysis(old, new)
        self.assertFalse(has_changes(report))
        self.assertEqual(report["theme_changes"], [])

    def test_theme_scalar_change(self) -> None:
        old = _base_analysis()
        new = copy.deepcopy(old)
        new["theme"]["technology_readiness_level"] = 6
        new["theme"]["hype_stage"] = "enlightenment"

        report = diff_analysis(old, new)

        fields_changed = {change["field"] for change in report["theme_changes"]}
        self.assertEqual(fields_changed, {"technology_readiness_level", "hype_stage"})
        self.assertTrue(has_changes(report))

    def test_bottleneck_score_change(self) -> None:
        old = _base_analysis()
        new = copy.deepcopy(old)
        new["bottleneck_scores"][0]["score"] = 4.0
        new["bottleneck_scores"][0]["rating"] = "strong"

        report = diff_analysis(old, new)

        changed = report["bottleneck_scores"]["changed"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["name"], "B1")
        changed_fields = {change["field"] for change in changed[0]["changes"]}
        self.assertEqual(changed_fields, {"score", "rating"})

    def test_added_evidence(self) -> None:
        old = _base_analysis()
        new = copy.deepcopy(old)
        new["evidence"].append(
            {
                "id": "E2",
                "title": "t2",
                "source_type": "s",
                "date": "2026-02-01",
                "url": "",
                "reliability": "medium",
                "claims": [],
            }
        )

        report = diff_analysis(old, new)

        self.assertEqual([item["id"] for item in report["evidence"]["added"]], ["E2"])
        self.assertEqual(report["evidence"]["removed"], [])
        self.assertTrue(has_changes(report))

    def test_removed_scenario(self) -> None:
        old = _base_analysis()
        new = copy.deepcopy(old)
        new["scenarios"] = []

        report = diff_analysis(old, new)

        self.assertEqual([item["name"] for item in report["scenarios"]["removed"]], ["bull"])

    def test_tracking_signal_and_counter_thesis_diff(self) -> None:
        old = _base_analysis()
        new = copy.deepcopy(old)
        new["tracking_signals"] = ["signal two"]
        new["counter_theses"] = ["risk one", "risk two"]

        report = diff_analysis(old, new)

        self.assertEqual(report["tracking_signals"]["added"], ["signal two"])
        self.assertEqual(report["tracking_signals"]["removed"], ["signal one"])
        self.assertEqual(report["counter_theses"]["added"], ["risk two"])
        self.assertEqual(report["counter_theses"]["removed"], [])


class FindRunsForThemeTest(unittest.TestCase):
    def test_sorts_by_as_of_and_ignores_unrelated_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            runs_dir = project_root / "runs"
            for name in ["2026-03-01-demo", "2026-01-01-demo", "2026-02-01-other-theme", "not-a-run"]:
                run_dir = runs_dir / name
                run_dir.mkdir(parents=True)
                if "demo" in name or "other-theme" in name:
                    (run_dir / "analysis.json").write_text(json.dumps({}), encoding="utf-8")

            matches = find_runs_for_theme(project_root, "demo")

            self.assertEqual([as_of for as_of, _ in matches], ["2026-01-01", "2026-03-01"])

    def test_missing_runs_dir_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(find_runs_for_theme(Path(tmp), "demo"), [])


if __name__ == "__main__":
    unittest.main()
