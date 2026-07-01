from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.io import load_theme
from fundamental_research_engine.pipeline import run_pipeline


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]

    def test_load_theme(self) -> None:
        theme = load_theme(self.project_root / "configs" / "themes" / "hbm4.json")
        self.assertEqual(theme.id, "hbm4")
        self.assertEqual(theme.bottlenecks[0].name, "HBM4 capacity and qualification")

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
            self.assertIn(analysis["bottleneck_scores"][0]["rating"], {"strong", "critical"})
            self.assertIn("HBM4", memo_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
