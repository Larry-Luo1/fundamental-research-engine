from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from fundamental_research_engine.validation import validate_theme_dict


class ValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.ontology = json.loads((project_root / "knowledge" / "ontology.json").read_text(encoding="utf-8"))
        self.theme = json.loads(
            (project_root / "configs" / "themes" / "hbm4.json").read_text(encoding="utf-8")
        )

    def test_valid_theme_has_no_errors(self) -> None:
        self.assertEqual(validate_theme_dict(self.theme, self.ontology), [])

    def test_missing_required_field(self) -> None:
        data = copy.deepcopy(self.theme)
        del data["core_question"]
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("core_question" in item for item in errors))

    def test_bad_as_of_format(self) -> None:
        data = copy.deepcopy(self.theme)
        data["as_of"] = "07-01-2026"
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("as_of" in item for item in errors))

    def test_unknown_theme_type(self) -> None:
        data = copy.deepcopy(self.theme)
        data["theme_type"] = "not_a_real_type"
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("theme_type" in item for item in errors))

    def test_trl_out_of_range(self) -> None:
        data = copy.deepcopy(self.theme)
        data["technology_readiness_level"] = 12
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("technology_readiness_level" in item for item in errors))

    def test_dangling_evidence_id(self) -> None:
        data = copy.deepcopy(self.theme)
        data["bottlenecks"][0]["evidence_ids"].append("E999")
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("unknown evidence id 'E999'" in item for item in errors))

    def test_duplicate_evidence_id(self) -> None:
        data = copy.deepcopy(self.theme)
        data["evidence"][0]["id"] = data["evidence"][1]["id"]
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("duplicate evidence id" in item for item in errors))

    def test_unknown_positioning_label(self) -> None:
        data = copy.deepcopy(self.theme)
        data["companies"][0]["positioning_label"] = "made up label"
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("positioning_label" in item for item in errors))

    def test_empty_bottlenecks_rejected(self) -> None:
        data = copy.deepcopy(self.theme)
        data["bottlenecks"] = []
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("bottlenecks" in item and "required" in item for item in errors))

    def test_scorecard_out_of_scale(self) -> None:
        data = copy.deepcopy(self.theme)
        data["bottlenecks"][0]["scorecard"]["demand_growth_speed"] = 7
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("outside 0-5 scale" in item for item in errors))

    def test_duplicate_stable_ids_rejected(self) -> None:
        data = copy.deepcopy(self.theme)
        data["companies"][1]["id"] = data["companies"][0]["id"]
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("duplicate id" in item for item in errors))

    def test_dangling_thesis_evidence_id(self) -> None:
        data = copy.deepcopy(self.theme)
        data["thesis_evidence_ids"] = ["E999"]
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("unknown evidence id 'E999'" in item for item in errors))

    def test_dangling_scenario_evidence_id(self) -> None:
        data = copy.deepcopy(self.theme)
        data["scenarios"][0]["evidence_ids"] = ["E999"]
        errors = validate_theme_dict(data, self.ontology)
        self.assertTrue(any("unknown evidence id 'E999'" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
