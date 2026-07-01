from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.stages import (
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

    def test_split_covers_every_theme_field(self) -> None:
        stages = split_theme_dict(self.theme)
        self.assertEqual(set(stages), set(STAGE_ORDER))
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

            self.assertEqual(set(stages), {"theme_definition", "mechanism_analysis", "bottleneck_diagnosis", "value_chain_map"})
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
            self.assertEqual(validate_stage_shape(stage, data), [])

    def test_validate_stage_shape_rejects_non_dict(self) -> None:
        self.assertEqual(
            validate_stage_shape("mechanism_analysis", ["not", "a", "dict"]),
            ["mechanism_analysis: expected a JSON object"],
        )


if __name__ == "__main__":
    unittest.main()
