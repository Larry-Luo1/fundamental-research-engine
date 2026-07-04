from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.cli import main
from fundamental_research_engine.watch import (
    build_digest,
    gate_radar,
    render_digest_md,
    summarize_analysis_diff,
    theme_result,
    validate_watchlist,
)


def _action_radar():
    return {
        "theme_id": "hot",
        "as_of": "2026-07-01",
        "driver": {"slope_surprise": 0.5},
        "ranking": ["power"],
        "constraints": [{"id": "power", "headroom_ratio": 0.65, "ratio_delta": -0.1}],
        "alerts": [
            {"type": "driver_slope_alert", "level": "investigate"},
            {"type": "constraint_migration_alert", "level": "action", "constraint_id": "power", "pre_consensus": True, "message": "[pre-consensus] power tight"},
        ],
    }


def _quiet_radar():
    return {
        "theme_id": "calm",
        "as_of": "2026-07-01",
        "driver": {"slope_surprise": None},
        "ranking": ["x"],
        "constraints": [{"id": "x", "headroom_ratio": 1.3, "ratio_delta": 0.0}],
        "alerts": [{"type": "constraint_migration_alert", "level": "watch", "constraint_id": "x", "pre_consensus": False, "message": "x ok"}],
    }


class ValidateWatchlistTest(unittest.TestCase):
    def test_valid(self) -> None:
        wl = {"name": "w", "themes": [{"theme": "a.json", "radar_spec": "b.json"}]}
        self.assertEqual(validate_watchlist(wl), [])

    def test_missing_themes_and_paths(self) -> None:
        self.assertTrue(any("themes" in e for e in validate_watchlist({"name": "w"})))
        errors = validate_watchlist({"themes": [{"theme": "a.json"}]})
        self.assertTrue(any("radar_spec" in e for e in errors))


class GateTest(unittest.TestCase):
    def test_action_radar_is_material(self) -> None:
        gate = gate_radar(_action_radar())
        self.assertTrue(gate["material"])
        self.assertEqual(gate["top_level"], "action")
        joined = "; ".join(gate["reasons"])
        self.assertIn("driver slope surprise", joined)
        self.assertIn("action-level constraint migration", joined)
        self.assertIn("pre-consensus alpha window", joined)
        self.assertIn("eroded", joined)

    def test_quiet_radar_is_not_material(self) -> None:
        gate = gate_radar(_quiet_radar())
        self.assertFalse(gate["material"])
        self.assertEqual(gate["reasons"], [])


class DigestTest(unittest.TestCase):
    def test_build_and_render(self) -> None:
        results = [
            theme_result(_action_radar()),
            theme_result(_quiet_radar()),
            {"theme_id": "broken", "error": "bad spec"},
        ]
        digest = build_digest(results, as_of="2026-07-04", watchlist_name="ai-compute")
        self.assertEqual(digest["summary"], {"flagged": 1, "quiet": 1, "action": 1, "pre_consensus": 1, "errored": 1})
        self.assertEqual(digest["flagged"][0]["theme_id"], "hot")
        self.assertEqual(digest["quiet"], ["calm"])

        md = render_digest_md(digest)
        self.assertIn("ai-compute", md)
        self.assertIn("hot", md)
        self.assertNotIn("[pre-consensus] [pre-consensus]", md)  # tag not doubled

    def test_flagged_sorted_by_level_then_tightness(self) -> None:
        a = theme_result(_action_radar())
        invest = theme_result({**_action_radar(), "theme_id": "mid", "alerts": [{"type": "constraint_migration_alert", "level": "investigate", "constraint_id": "power", "pre_consensus": False, "message": "m"}], "constraints": [{"id": "power", "headroom_ratio": 0.9, "ratio_delta": -0.1}]})
        digest = build_digest([invest, a], as_of="2026-07-04")
        self.assertEqual([r["theme_id"] for r in digest["flagged"]], ["hot", "mid"])  # action before investigate


class DiffSummaryTest(unittest.TestCase):
    def test_counts_changed_sections(self) -> None:
        report = {
            "from_as_of": "a", "to_as_of": "b",
            "theme_changes": [{"field": "trl"}],
            "drivers": {"added": [], "removed": []},
            "bottleneck_scores": {"added": [], "removed": [], "changed": [{"id": 1}]},
            "segments": {"added": [], "removed": [], "changed": []},
        }
        summary = summarize_analysis_diff(report)
        self.assertTrue(summary["changed"])
        self.assertEqual(summary["sections_changed"], 2)


class WatchCliTest(unittest.TestCase):
    def test_watch_cli_writes_digest(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        watchlist = project_root / "configs" / "watchlists" / "ai-compute.json"
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "w"
            code = main([
                "watch", str(watchlist), "--project-root", str(project_root),
                "--as-of", "2026-07-04", "--out-dir", str(out_dir),
                "--no-persist", "--no-register", "--no-diff",
            ])
            self.assertEqual(code, 0)
            digest = json.loads((out_dir / "digest.json").read_text(encoding="utf-8"))
            self.assertEqual(digest["summary"]["flagged"], 1)
            self.assertEqual(digest["flagged"][0]["theme_id"], "hbm4")
            self.assertEqual(digest["flagged"][0]["tightest"], "rack-power-cooling")
            self.assertTrue((out_dir / "digest.md").exists())


if __name__ == "__main__":
    unittest.main()
