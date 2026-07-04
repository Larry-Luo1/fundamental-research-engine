from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fundamental_research_engine.cli import main
from fundamental_research_engine.radar import build_radar, validate_radar_spec


def _theme():
    return SimpleNamespace(
        id="hbm4",
        as_of="2026-07-01",
        bottlenecks=[SimpleNamespace(name="HBM bandwidth/capacity")],
        causal_map=[SimpleNamespace(target="advanced packaging capacity utilization")],
        segments=[SimpleNamespace(name="Rack power and cooling")],
    )


def _spec():
    return {
        "theme_id": "hbm4",
        "as_of": "2026-07-01",
        "driver": {"name": "AI compute", "realized_growth": 1.9, "assumed_growth": 1.4},
        "constraints": [
            {"id": "hbm", "name": "HBM bandwidth/capacity", "ring": "current_binding", "demand_growth": 1.9, "capacity_growth": 1.5},
            {"id": "packaging", "name": "Advanced packaging (CoWoS)", "ring": "adjacent_latent", "demand_growth": 1.9, "capacity_growth": 2.0},
            {"id": "power", "name": "Rack power and cooling", "ring": "adjacent_latent", "demand_growth": 2.0, "capacity_growth": 1.3},
            {"id": "grid", "name": "Grid interconnection", "ring": "second_order_external", "signpost": "queue backlog"},
        ],
    }


class ValidateSpecTest(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(validate_radar_spec(_spec()), [])

    def test_bad_ring_and_nonpositive_demand(self) -> None:
        spec = _spec()
        spec["constraints"][0]["ring"] = "nope"
        spec["constraints"][1]["demand_growth"] = 0
        errors = validate_radar_spec(spec)
        self.assertTrue(any("ring: unknown value 'nope'" in e for e in errors))
        self.assertTrue(any("demand_growth: expected positive number" in e for e in errors))

    def test_empty_constraints(self) -> None:
        self.assertTrue(any("constraints" in e for e in validate_radar_spec({"constraints": []})))


class BuildRadarTest(unittest.TestCase):
    def test_ratios_ranking_and_migration(self) -> None:
        radar = build_radar(_theme(), _spec())
        by_id = {c["id"]: c for c in radar["constraints"]}
        self.assertEqual(by_id["hbm"]["headroom_ratio"], round(1.5 / 1.9, 4))
        self.assertEqual(by_id["power"]["headroom_ratio"], 0.65)
        self.assertTrue(by_id["hbm"]["binding"])       # ratio < 1
        self.assertIsNone(by_id["grid"]["headroom_ratio"])  # exogenous, no ratio

        # tightest first; exogenous excluded from ranking
        self.assertEqual(radar["ranking"][0], "power")
        self.assertNotIn("grid", radar["ranking"])
        self.assertEqual(radar["tightest_current_ratio"], round(1.5 / 1.9, 4))

        # driver accelerated past assumption -> slope alert
        self.assertEqual(radar["driver"]["slope_surprise"], 0.5)
        self.assertTrue(any(a["type"] == "driver_slope_alert" for a in radar["alerts"]))

        # power (0.65) is tighter than the acknowledged HBM (0.79) -> action migration alert
        migrations = [a for a in radar["alerts"] if a["type"] == "constraint_migration_alert"]
        power_alert = next(a for a in migrations if a["constraint_id"] == "power")
        self.assertEqual(power_alert["level"], "action")
        # packaging is within the migration band but healthy (>1) and not eroding -> watch
        packaging_alert = next(a for a in migrations if a["constraint_id"] == "packaging")
        self.assertEqual(packaging_alert["level"], "watch")

    def test_erosion_delta_vs_prev_state(self) -> None:
        prev = {"as_of": "2026-04-01", "ratios": {"power": 0.80}}
        radar = build_radar(_theme(), _spec(), prev)
        power = next(c for c in radar["constraints"] if c["id"] == "power")
        self.assertEqual(power["prev_ratio"], 0.80)
        self.assertEqual(power["ratio_delta"], round(0.65 - 0.80, 4))  # eroded

    def test_uncovered_candidates_flagged(self) -> None:
        theme = _theme()
        theme.bottlenecks.append(SimpleNamespace(name="Substrate supply"))
        radar = build_radar(theme, _spec())
        self.assertIn("Substrate supply", radar["uncovered_candidates"])

    def test_invalid_spec_returns_errors(self) -> None:
        radar = build_radar(_theme(), {"constraints": []})
        self.assertTrue(radar["errors"])


class RadarCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4 = self.project_root / "configs" / "themes" / "hbm4.json"
        self.spec = self.project_root / "configs" / "radar" / "hbm4.json"

    def test_radar_cli_writes_report_and_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            out = Path(tmp) / "radar.json"
            code = main(
                ["radar", str(self.hbm4), str(self.spec), "--project-root", str(self.project_root),
                 "--state", str(state), "--out", str(out)]
            )
            self.assertEqual(code, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["ranking"][0], "rack-power-cooling")
            self.assertTrue(state.exists())
            self.assertEqual(len(json.loads(state.read_text(encoding="utf-8"))["history"]), 1)

            # second run appends to the state series
            main(["radar", str(self.hbm4), str(self.spec), "--project-root", str(self.project_root), "--state", str(state), "--out", str(out)])
            self.assertEqual(len(json.loads(state.read_text(encoding="utf-8"))["history"]), 2)


if __name__ == "__main__":
    unittest.main()
