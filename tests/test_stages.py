from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.stages import (
    OPTIONAL_STAGE_ORDER,
    STAGE_ORDER,
    StageError,
    load_theme_source,
    load_theme_stage_dir,
    merge_stage_dicts,
    next_missing_stage,
    read_stage_dir_partial,
    split_theme_dict,
    validate_stage_shape,
    write_theme_stage_dir,
)


class StagesTest(unittest.TestCase):
    def setUp(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.theme = json.loads(
            (project_root / "configs" / "themes" / "hbm4.json").read_text(encoding="utf-8")
        )
        self.ontology = json.loads((project_root / "knowledge" / "ontology.json").read_text(encoding="utf-8"))

    def test_split_covers_every_theme_field(self) -> None:
        stages = split_theme_dict(self.theme)
        expected_stages = set(STAGE_ORDER)
        if "causal_map" in self.theme:
            expected_stages.update(OPTIONAL_STAGE_ORDER)
        self.assertEqual(set(stages), expected_stages)
        recombined_fields = {field for stage in stages.values() for field in stage}
        self.assertEqual(recombined_fields, set(self.theme))

    def test_split_then_merge_round_trips(self) -> None:
        stages = split_theme_dict(self.theme)
        merged = merge_stage_dicts(stages)
        self.assertEqual(merged, self.theme)

    def test_merge_missing_stage_raises(self) -> None:
        stages = split_theme_dict(self.theme)
        del stages["bottleneck_diagnosis"]
        with self.assertRaises(StageError):
            merge_stage_dicts(stages)

    def test_write_and_load_stage_dir_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "hbm4"
            write_theme_stage_dir(theme_dir, self.theme)
            for stage in STAGE_ORDER:
                self.assertTrue((theme_dir / f"{stage}.json").exists())
            self.assertTrue((theme_dir / "causal_map.json").exists())
            loaded = load_theme_stage_dir(theme_dir)
            self.assertEqual(loaded, self.theme)

    def test_load_theme_source_handles_file_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "hbm4"
            write_theme_stage_dir(theme_dir, self.theme)
            theme_file = Path(tmp) / "hbm4.json"
            theme_file.write_text(json.dumps(self.theme), encoding="utf-8")

            self.assertEqual(load_theme_source(theme_dir), self.theme)
            self.assertEqual(load_theme_source(theme_file), self.theme)

    def test_load_theme_stage_dir_missing_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "partial"
            write_theme_stage_dir(theme_dir, self.theme)
            (theme_dir / "scenario_analysis.json").unlink()
            with self.assertRaises(StageError):
                load_theme_stage_dir(theme_dir)

    def test_read_stage_dir_partial_and_next_missing_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "partial"
            write_theme_stage_dir(theme_dir, self.theme)
            (theme_dir / "company_positioning.json").unlink()
            (theme_dir / "scenario_analysis.json").unlink()

            stages = read_stage_dir_partial(theme_dir)

            self.assertEqual(
                set(stages),
                {"theme_definition", "mechanism_analysis", "causal_map", "bottleneck_diagnosis", "value_chain_map"},
            )
            self.assertEqual(next_missing_stage(stages), "company_positioning")

    def test_next_missing_stage_none_when_complete(self) -> None:
        stages = split_theme_dict(self.theme)
        self.assertIsNone(next_missing_stage(stages))

    def test_validate_stage_shape_detects_missing_and_unexpected_fields(self) -> None:
        errors = validate_stage_shape("mechanism_analysis", {"mechanism": "x", "extra_field": 1})
        self.assertIn("mechanism_analysis.extra_field: unexpected field for this stage", errors)

        errors = validate_stage_shape("mechanism_analysis", {})
        self.assertIn("mechanism_analysis.mechanism: missing", errors)

    def test_validate_stage_shape_accepts_well_formed_stage(self) -> None:
        stages = split_theme_dict(self.theme)
        for stage, data in stages.items():
            self.assertEqual(validate_stage_shape(stage, data, self.ontology), [])

    def test_validate_stage_shape_rejects_causal_edge_without_claims(self) -> None:
        data = split_theme_dict(self.theme)["causal_map"]
        data["causal_map"][0]["claim_ids"] = []

        errors = validate_stage_shape("causal_map", data, self.ontology)

        self.assertTrue(any("claim_ids" in item and "required" in item for item in errors))

    def test_validate_stage_shape_rejects_non_dict(self) -> None:
        self.assertEqual(
            validate_stage_shape("mechanism_analysis", ["not", "a", "dict"]),
            ["mechanism_analysis: expected a JSON object"],
        )

    def test_validate_stage_shape_checks_nested_bottleneck_fields(self) -> None:
        data = split_theme_dict(self.theme)["bottleneck_diagnosis"]
        del data["bottlenecks"][0]["scorecard"]["demand_growth_speed"]
        data["bottlenecks"][0]["scorecard"]["made_up_dimension"] = 2
        data["bottlenecks"][0]["types"] = ["not_a_real_type"]

        errors = validate_stage_shape("bottleneck_diagnosis", data, self.ontology)

        self.assertTrue(any("demand_growth_speed" in item and "missing" in item for item in errors))
        self.assertTrue(any("made_up_dimension" in item and "unexpected" in item for item in errors))
        self.assertTrue(any("not_a_real_type" in item for item in errors))

    def test_validate_stage_shape_checks_scenario_evidence_quality(self) -> None:
        data = split_theme_dict(self.theme)["scenario_analysis"]
        data["evidence"][1]["id"] = data["evidence"][0]["id"]
        data["evidence"][0]["reliability"] = "certain"
        data["evidence"][0]["date"] = "2026/07/01"

        errors = validate_stage_shape("scenario_analysis", data)

        self.assertTrue(any("duplicate evidence id" in item for item in errors))
        self.assertTrue(any("reliability" in item and "certain" in item for item in errors))
        self.assertTrue(any("date" in item and "YYYY-MM-DD" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
