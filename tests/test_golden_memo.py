from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.pipeline import run_pipeline

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


class GoldenMemoTest(unittest.TestCase):
    """Regression guard for memo rendering.

    If a deliberate rendering change makes this fail, regenerate the golden
    file with:

        PYTHONPATH=src python -m fundamental_research_engine run \\
            configs/themes/hbm4.json --out /tmp/golden-gen
        cp /tmp/golden-gen/memo.md tests/golden/hbm4_memo.md

    then review the diff before committing it.
    """

    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]

    def test_hbm4_memo_matches_golden_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = run_pipeline(
                self.project_root / "configs" / "themes" / "hbm4.json",
                self.project_root,
                Path(tmp),
            )
            rendered = (out_dir / "memo.md").read_text(encoding="utf-8")
            golden = (GOLDEN_DIR / "hbm4_memo.md").read_text(encoding="utf-8")
            self.assertEqual(rendered, golden)


if __name__ == "__main__":
    unittest.main()
