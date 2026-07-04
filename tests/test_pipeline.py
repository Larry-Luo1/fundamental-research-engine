from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.io import load_theme
from fundamental_research_engine.pipeline import run_pipeline
from fundamental_research_engine.validation import ThemeValidationError


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]

    def test_load_theme(self) -> None:
        theme = load_theme(self.project_root / "configs" / "themes" / "hbm4.json")
        self.assertEqual(theme.id, "hbm4")
        self.assertEqual(theme.theme_type, "technology_adoption")
        self.assertEqual(theme.domain, "ai")
        self.assertEqual(theme.bottlenecks[0].name, "HBM4 capacity and qualification")
        self.assertEqual(theme.causal_map[0].id, "edge-ai-capex-to-qualified-hbm-demand")
        self.assertTrue(theme.profit_pools)
        self.assertTrue(theme.scenarios)

    def test_load_non_ai_theme(self) -> None:
        theme = load_theme(self.project_root / "configs" / "themes" / "copper-supply-demand.json")
        self.assertEqual(theme.theme_type, "supply_demand_cycle")
        self.assertEqual(theme.domain, "metals_mining")
        self.assertIn("electrification", theme.mechanism)

    def test_run_pipeline_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = run_pipeline(
                self.project_root / "configs" / "themes" / "hbm4.json",
                self.project_root,
                Path(tmp),
            )
            analysis_path = out / "analysis.json"
            memo_path = out / "memo.md"
            self.assertTrue(analysis_path.exists())
            self.assertTrue(memo_path.exists())

            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            self.assertEqual(analysis["theme"]["id"], "hbm4")
            self.assertEqual(analysis["bottleneck_scores"][0]["id"], "bn-hbm4-capacity-and-qualification")
            self.assertEqual(analysis["causal_map"][0]["id"], "edge-ai-capex-to-qualified-hbm-demand")
            self.assertEqual(analysis["quality_scorecard"]["causal_quality"]["summary"]["edges"], 3)
            self.assertEqual(analysis["companies"][0]["id"], "co-sk-hynix")
            self.assertEqual(analysis["evidence_audit"]["inventory"]["evidence_count"], 4)
            self.assertTrue(analysis["evidence_audit"]["coverage"])
            self.assertIn(analysis["bottleneck_scores"][0]["rating"], {"strong", "critical"})
            memo = memo_path.read_text(encoding="utf-8")
            self.assertIn("HBM4", memo)
            self.assertIn("Causal Map", memo)
            self.assertIn("Evidence Audit", memo)

    def test_run_pipeline_rejects_invalid_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = json.loads(
                (self.project_root / "configs" / "themes" / "hbm4.json").read_text(encoding="utf-8")
            )
            del broken["core_question"]
            broken_path = Path(tmp) / "broken.json"
            broken_path.write_text(json.dumps(broken), encoding="utf-8")

            with self.assertRaises(ThemeValidationError):
                run_pipeline(broken_path, self.project_root, Path(tmp) / "out")


if __name__ == "__main__":
    unittest.main()
