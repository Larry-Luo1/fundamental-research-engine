from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fundamental_research_engine.cli import main


def _analysis(as_of: str, technology_readiness_level: int) -> dict:
    return {
        "theme": {
            "id": "demo",
            "title": "Demo Theme",
            "as_of": as_of,
            "theme_type": "technology_adoption",
            "domain": "ai",
            "core_question": "Is this a bottleneck?",
            "thesis": "Thesis text.",
            "mechanism": "Mechanism text.",
            "hype_stage": "trigger",
            "technology_readiness_level": technology_readiness_level,
            "drivers": [],
        },
        "bottleneck_scores": [],
        "segments": [],
        "profit_pools": [],
        "companies": [],
        "scenarios": [],
        "evidence": [],
        "evidence_coverage": {},
        "counter_theses": [],
        "tracking_signals": [],
    }


class DiffCliTest(unittest.TestCase):
    def test_diff_with_explicit_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_path = tmp_path / "old.json"
            new_path = tmp_path / "new.json"
            old_path.write_text(json.dumps(_analysis("2026-01-01", 4)), encoding="utf-8")
            new_path.write_text(json.dumps(_analysis("2026-02-01", 6)), encoding="utf-8")
            out_dir = tmp_path / "out"

            exit_code = main(
                ["diff", "--from", str(old_path), "--to", str(new_path), "--out", str(out_dir)]
            )

            self.assertEqual(exit_code, 0)
            diff_json = json.loads((out_dir / "diff.json").read_text(encoding="utf-8"))
            self.assertEqual(diff_json["from_as_of"], "2026-01-01")
            self.assertEqual(diff_json["to_as_of"], "2026-02-01")
            self.assertTrue(
                any(c["field"] == "technology_readiness_level" for c in diff_json["theme_changes"])
            )
            self.assertIn("technology_readiness_level", (out_dir / "diff.md").read_text(encoding="utf-8"))

    def test_diff_autodiscovers_latest_two_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            for as_of, trl in [("2026-01-01", 4), ("2026-02-01", 5), ("2026-03-01", 6)]:
                run_dir = project_root / "runs" / f"{as_of}-demo"
                run_dir.mkdir(parents=True)
                (run_dir / "analysis.json").write_text(
                    json.dumps(_analysis(as_of, trl)), encoding="utf-8"
                )

            exit_code = main(["diff", "demo", "--project-root", str(project_root)])

            self.assertEqual(exit_code, 0)
            diff_dir = project_root / "runs" / "diffs" / "demo-2026-02-01-to-2026-03-01"
            diff_json = json.loads((diff_dir / "diff.json").read_text(encoding="utf-8"))
            self.assertEqual(diff_json["from_as_of"], "2026-02-01")
            self.assertEqual(diff_json["to_as_of"], "2026-03-01")


class StageCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def test_split_then_merge_round_trips_and_run_accepts_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stage_dir = tmp_path / "hbm4"
            merged_path = tmp_path / "merged.json"
            run_out = tmp_path / "run_out"

            self.assertEqual(main(["split", str(self.hbm4_path), str(stage_dir)]), 0)
            for stage in [
                "theme_definition",
                "mechanism_analysis",
                "bottleneck_diagnosis",
                "value_chain_map",
                "company_positioning",
                "scenario_analysis",
            ]:
                self.assertTrue((stage_dir / f"{stage}.json").exists())

            self.assertEqual(main(["merge", str(stage_dir), str(merged_path)]), 0)
            original = json.loads(self.hbm4_path.read_text(encoding="utf-8"))
            merged = json.loads(merged_path.read_text(encoding="utf-8"))
            self.assertEqual(merged, original)

            self.assertEqual(
                main(
                    [
                        "validate",
                        str(stage_dir),
                        "--project-root",
                        str(self.project_root),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "run",
                        str(stage_dir),
                        "--project-root",
                        str(self.project_root),
                        "--out",
                        str(run_out),
                    ]
                ),
                0,
            )
            self.assertTrue((run_out / "analysis.json").exists())
            self.assertTrue((run_out / "memo.md").exists())


class FillCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def _theme_dir_with_definition_only(self, tmp_path: Path) -> Path:
        theme_dir = tmp_path / "hbm4"
        self.assertEqual(main(["split", str(self.hbm4_path), str(theme_dir)]), 0)
        for stage in [
            "mechanism_analysis",
            "bottleneck_diagnosis",
            "value_chain_map",
            "company_positioning",
            "scenario_analysis",
        ]:
            (theme_dir / f"{stage}.json").unlink()
        return theme_dir

    def test_manual_mode_writes_prompt_without_writing_stage_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = self._theme_dir_with_definition_only(Path(tmp))

            exit_code = main(["fill", str(theme_dir), "--project-root", str(self.project_root)])

            self.assertEqual(exit_code, 0)
            prompt_path = theme_dir / "mechanism_analysis.prompt.md"
            self.assertTrue(prompt_path.exists())
            self.assertIn("mechanism", prompt_path.read_text(encoding="utf-8"))
            self.assertFalse((theme_dir / "mechanism_analysis.json").exists())

    def test_mocked_adapter_writes_stage_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = self._theme_dir_with_definition_only(Path(tmp))

            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.return_value = json.dumps({"mechanism": "test mechanism text"})

            with patch("fundamental_research_engine.cli.get_adapter", return_value=fake_adapter):
                exit_code = main(
                    [
                        "fill",
                        str(theme_dir),
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            stage_data = json.loads((theme_dir / "mechanism_analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(stage_data, {"mechanism": "test mechanism text"})

    def test_mocked_adapter_bad_shape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = self._theme_dir_with_definition_only(Path(tmp))

            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.return_value = json.dumps({"mechanism": "ok", "extra_field": 1})

            with patch("fundamental_research_engine.cli.get_adapter", return_value=fake_adapter):
                exit_code = main(
                    [
                        "fill",
                        str(theme_dir),
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse((theme_dir / "mechanism_analysis.json").exists())

    def test_fill_requires_theme_definition_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "empty"
            theme_dir.mkdir()
            with self.assertRaises(SystemExit):
                main(
                    [
                        "fill",
                        str(theme_dir),
                        "--stage",
                        "mechanism_analysis",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

    def test_all_stages_present_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "hbm4"
            self.assertEqual(main(["split", str(self.hbm4_path), str(theme_dir)]), 0)

            exit_code = main(["fill", str(theme_dir), "--project-root", str(self.project_root)])

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
