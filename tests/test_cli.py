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


class AuditCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def test_audit_writes_evidence_audit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "evidence_audit.json"

            exit_code = main(
                [
                    "audit",
                    str(self.hbm4_path),
                    "--project-root",
                    str(self.project_root),
                    "--out",
                    str(out_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            audit = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["inventory"]["evidence_count"], 4)
            self.assertTrue(audit["coverage"])


class EvidenceSyncCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def test_evidence_sync_writes_store_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = main(
                [
                    "evidence-sync",
                    str(self.hbm4_path),
                    "--project-root",
                    str(self.project_root),
                    "--store-root",
                    tmp,
                ]
            )

            self.assertEqual(exit_code, 0)
            store_root = Path(tmp)
            self.assertTrue((store_root / "data" / "raw_sources" / "hbm4" / "E1.json").exists())
            self.assertTrue((store_root / "data" / "normalized" / "hbm4" / "evidence.json").exists())
            self.assertTrue((store_root / "data" / "evidence" / "hbm4" / "claims.json").exists())
            self.assertTrue((store_root / "data" / "evidence" / "hbm4" / "manifest.json").exists())


class ExtractClaimsCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def _write_source_and_claims(self, tmp_path: Path) -> tuple[Path, Path]:
        source_path = tmp_path / "source.txt"
        source_path.write_text(
            "NVIDIA reported data center revenue increased because AI customers are scaling infrastructure.",
            encoding="utf-8",
        )
        claims_path = tmp_path / "claims.json"
        claims_path.write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "text": "NVIDIA reported data center revenue increased because AI customers are scaling infrastructure.",
                            "quote": "NVIDIA reported data center revenue increased because AI customers are scaling infrastructure.",
                            "confidence": "high",
                            "bears_on": ["thesis"],
                        },
                        {
                            "text": "NVIDIA said HBM supply is already unconstrained.",
                            "quote": "HBM supply is already unconstrained.",
                            "confidence": "low",
                            "bears_on": ["thesis"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        return source_path, claims_path

    def test_extract_claims_with_pre_authored_json_writes_verified_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path, claims_path = self._write_source_and_claims(tmp_path)
            out_path = tmp_path / "report.json"

            exit_code = main(
                [
                    "extract-claims",
                    str(self.hbm4_path),
                    "--source",
                    "E1",
                    "--source-text",
                    str(source_path),
                    "--claims",
                    str(claims_path),
                    "--out",
                    str(out_path),
                    "--project-root",
                    str(self.project_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            report = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(report["source"]["evidence_id"], "E1")
            self.assertEqual(len(report["claims"]), 1)
            self.assertEqual(report["dropped_unverified"], 1)
            self.assertFalse(report["applied"])

    def test_extract_claims_apply_appends_verified_claim_text_to_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            theme_path = tmp_path / "hbm4.json"
            theme_path.write_text(self.hbm4_path.read_text(encoding="utf-8"), encoding="utf-8")
            source_path, claims_path = self._write_source_and_claims(tmp_path)
            claims_payload = json.loads(claims_path.read_text(encoding="utf-8"))
            for claim in claims_payload["claims"]:
                claim["verified"] = True
            claims_path.write_text(json.dumps(claims_payload), encoding="utf-8")
            out_path = tmp_path / "report.json"

            exit_code = main(
                [
                    "extract-claims",
                    str(theme_path),
                    "--source",
                    "E1",
                    "--source-text",
                    str(source_path),
                    "--claims",
                    str(claims_path),
                    "--apply",
                    "--store",
                    "--store-root",
                    str(tmp_path),
                    "--out",
                    str(out_path),
                    "--project-root",
                    str(self.project_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            updated = json.loads(theme_path.read_text(encoding="utf-8"))
            e1 = next(item for item in updated["evidence"] if item["id"] == "E1")
            self.assertIn(
                "NVIDIA reported data center revenue increased because AI customers are scaling infrastructure.",
                e1["claims"],
            )
            self.assertNotIn("NVIDIA said HBM supply is already unconstrained.", e1["claims"])
            report = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertTrue(report["stored"])
            claims_store = json.loads(
                (tmp_path / "data" / "evidence" / "hbm4" / "claims.json").read_text(encoding="utf-8")
            )
            stored_claim = next(
                item
                for item in claims_store["records"]
                if item["claim"]
                == "NVIDIA reported data center revenue increased because AI customers are scaling infrastructure."
            )
            self.assertEqual(stored_claim["status"], "applied")
            self.assertEqual(
                stored_claim["quote"],
                "NVIDIA reported data center revenue increased because AI customers are scaling infrastructure.",
            )
            self.assertTrue(stored_claim["verified"])
            self.assertTrue(stored_claim["source_sha256"])

    def test_extract_claims_manual_mode_writes_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_path = tmp_path / "source.txt"
            source_path.write_text("Data-center infrastructure demand increased.", encoding="utf-8")
            out_path = tmp_path / "report.json"

            exit_code = main(
                [
                    "extract-claims",
                    str(self.hbm4_path),
                    "--source",
                    "E1",
                    "--source-text",
                    str(source_path),
                    "--out",
                    str(out_path),
                    "--project-root",
                    str(self.project_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            prompt_path = tmp_path / "hbm4-e1.claim_extraction.prompt.md"
            self.assertTrue(prompt_path.exists())
            self.assertIn("Data-center infrastructure demand", prompt_path.read_text(encoding="utf-8"))
            self.assertFalse(out_path.exists())


def _theme_dir_with_definition_only(hbm4_path: Path, tmp_path: Path) -> Path:
    theme_dir = tmp_path / "hbm4"
    assert main(["split", str(hbm4_path), str(theme_dir)]) == 0
    for stage in [
        "causal_map",
        "mechanism_analysis",
        "bottleneck_diagnosis",
        "value_chain_map",
        "company_positioning",
        "scenario_analysis",
    ]:
        (theme_dir / f"{stage}.json").unlink()
    # The fake adapter drafts a self-contained demo world (only evidence E1), so drop
    # the real theme's optional thesis_evidence_ids, which reference E2/E4.
    definition_path = theme_dir / "theme_definition.json"
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    definition.pop("thesis_evidence_ids", None)
    definition_path.write_text(json.dumps(definition), encoding="utf-8")
    return theme_dir


_DRAFT_STAGE_RESPONSES = {
    "mechanism_analysis": {
        "mechanism": "Demo driver increases scarcity, forcing slow capacity expansion and upstream pricing power."
    },
    "bottleneck_diagnosis": {
        "bottlenecks": [
            {
                "name": "Demo bottleneck",
                "types": ["capacity"],
                "technical_reason": "Capacity cannot expand quickly.",
                "scorecard": {
                    "demand_growth_speed": 4,
                    "capacity_expansion_difficulty": 4,
                    "technology_substitution_difficulty": 3,
                    "yield_material_equipment_constraint": 3,
                    "customer_qualification_lock_in": 3,
                    "supplier_pricing_power": 4,
                    "rapid_supply_release_risk": 2,
                    "architecture_bypass_risk": 1,
                },
                "evidence_ids": ["E1"],
            }
        ]
    },
    "value_chain_map": {
        "segments": [
            {
                "name": "Demo suppliers",
                "layer": "upstream",
                "role": "Supply the scarce resource.",
                "beneficiary_class": "first-order",
                "representative_companies": ["DemoCo"],
            }
        ],
        "profit_pools": [
            {
                "name": "Demo pool",
                "rationale": "Scarce capacity captures pricing power.",
                "capture_quality": "high",
                "beneficiaries": ["DemoCo"],
            }
        ],
    },
    "company_positioning": {
        "companies": [
            {
                "name": "DemoCo",
                "product": "Demo widgets",
                "stack_position": "upstream",
                "positioning_label": "core bottleneck owner",
                "exposure_quality": "direct revenue upside",
                "moat": ["scale"],
                "risks": ["new entrants"],
                "evidence_ids": ["E1"],
            }
        ]
    },
    "scenario_analysis": {
        "scenarios": [
            {
                "name": "bull",
                "description": "Demand keeps outrunning supply.",
                "implications": ["pricing power persists"],
                "triggers": ["sold-out capacity"],
            }
        ],
        "counter_theses": ["Capacity could expand faster than expected."],
        "tracking_signals": ["watch capacity announcements"],
        "evidence": [
            {
                "id": "E1",
                "title": "Demo source",
                "source_type": "industry_research",
                "date": "2026-06-01",
                "url": "",
                "reliability": "medium",
                "claims": ["demo claim"],
            }
        ],
    },
}


class _FakeStageAdapter:
    def complete(self, prompt: str) -> str:
        for stage, payload in _DRAFT_STAGE_RESPONSES.items():
            if f"# Stage: {stage}" in prompt:
                return json.dumps(payload)
        raise AssertionError(f"unexpected prompt (no matching stage marker): {prompt[:200]}")


class FillCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def _theme_dir_with_definition_only(self, tmp_path: Path) -> Path:
        return _theme_dir_with_definition_only(self.hbm4_path, tmp_path)

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
            metadata = json.loads((theme_dir / "mechanism_analysis.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["stage"], "mechanism_analysis")
            self.assertEqual(metadata["model"], "openai")
            self.assertEqual(metadata["model_name"], "gpt-test")
            self.assertEqual(metadata["attempts"], 1)

    def test_mocked_adapter_accepts_json_inside_markdown_fence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = self._theme_dir_with_definition_only(Path(tmp))

            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.return_value = "```json\n{\"mechanism\": \"fenced mechanism text\"}\n```"

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
            self.assertEqual(stage_data, {"mechanism": "fenced mechanism text"})

    def test_mocked_adapter_retries_bad_stage_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = self._theme_dir_with_definition_only(Path(tmp))

            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.side_effect = [
                json.dumps({"mechanism": 1}),
                json.dumps({"mechanism": "corrected mechanism text"}),
            ]

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
            self.assertEqual(fake_adapter.complete.call_count, 2)
            stage_data = json.loads((theme_dir / "mechanism_analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(stage_data, {"mechanism": "corrected mechanism text"})
            metadata = json.loads((theme_dir / "mechanism_analysis.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["attempts"], 2)

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
                        "--max-attempts",
                        "1",
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


class DraftCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def test_draft_on_complete_stage_dir_runs_the_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "hbm4"
            self.assertEqual(main(["split", str(self.hbm4_path), str(theme_dir)]), 0)

            exit_code = main(["draft", str(theme_dir), "--project-root", str(self.project_root)])

            self.assertEqual(exit_code, 0)
            run_dir = self.project_root / "runs" / "2026-07-01-hbm4"
            try:
                self.assertTrue((run_dir / "memo.md").exists())
            finally:
                import shutil

                shutil.rmtree(run_dir, ignore_errors=True)

    def test_default_mode_stops_after_one_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = _theme_dir_with_definition_only(self.hbm4_path, Path(tmp))

            exit_code = main(["draft", str(theme_dir), "--project-root", str(self.project_root)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((theme_dir / "mechanism_analysis.prompt.md").exists())
            self.assertFalse((theme_dir / "mechanism_analysis.json").exists())
            self.assertFalse((theme_dir / "bottleneck_diagnosis.json").exists())

    def test_auto_mode_walks_every_remaining_stage_and_finishes_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = _theme_dir_with_definition_only(self.hbm4_path, Path(tmp))

            with patch("fundamental_research_engine.cli.get_adapter", return_value=_FakeStageAdapter()):
                exit_code = main(
                    [
                        "draft",
                        str(theme_dir),
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--auto",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            for stage in [
                "mechanism_analysis",
                "bottleneck_diagnosis",
                "value_chain_map",
                "company_positioning",
                "scenario_analysis",
            ]:
                self.assertTrue((theme_dir / f"{stage}.json").exists())
                self.assertTrue((theme_dir / f"{stage}.meta.json").exists())

            run_dir = self.project_root / "runs" / "2026-07-01-hbm4"
            try:
                self.assertTrue((run_dir / "memo.md").exists())
            finally:
                import shutil

                shutil.rmtree(run_dir, ignore_errors=True)

    def test_auto_requires_non_manual_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = _theme_dir_with_definition_only(self.hbm4_path, Path(tmp))
            with self.assertRaises(SystemExit):
                main(["draft", str(theme_dir), "--auto", "--project-root", str(self.project_root)])

    def test_auto_rejects_explicit_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = _theme_dir_with_definition_only(self.hbm4_path, Path(tmp))
            with self.assertRaises(SystemExit):
                main(
                    [
                        "draft",
                        str(theme_dir),
                        "--auto",
                        "--stage",
                        "mechanism_analysis",
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

    def test_auto_mode_stops_on_bad_stage_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = _theme_dir_with_definition_only(self.hbm4_path, Path(tmp))

            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.return_value = json.dumps({"mechanism": "ok", "extra_field": 1})

            with patch("fundamental_research_engine.cli.get_adapter", return_value=fake_adapter):
                exit_code = main(
                    [
                        "draft",
                        str(theme_dir),
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--max-attempts",
                        "1",
                        "--auto",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse((theme_dir / "mechanism_analysis.json").exists())
            self.assertFalse((theme_dir / "bottleneck_diagnosis.json").exists())


class CritiqueCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def test_manual_mode_writes_critique_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "hbm4"
            self.assertEqual(main(["split", str(self.hbm4_path), str(theme_dir)]), 0)

            exit_code = main(
                [
                    "critique",
                    str(theme_dir),
                    "--stage",
                    "bottleneck_diagnosis",
                    "--project-root",
                    str(self.project_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            prompt_path = theme_dir / "bottleneck_diagnosis.critique.prompt.md"
            self.assertTrue(prompt_path.exists())
            self.assertIn("Critique: bottleneck_diagnosis", prompt_path.read_text(encoding="utf-8"))
            self.assertFalse((theme_dir / "bottleneck_diagnosis.critique.json").exists())

    def test_mocked_adapter_writes_critique_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "hbm4"
            self.assertEqual(main(["split", str(self.hbm4_path), str(theme_dir)]), 0)

            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.return_value = json.dumps(
                {
                    "concerns": [],
                    "overall_assessment": "Looks solid.",
                    "recommendation": "accept",
                }
            )

            with patch("fundamental_research_engine.cli.get_adapter", return_value=fake_adapter):
                exit_code = main(
                    [
                        "critique",
                        str(theme_dir),
                        "--stage",
                        "bottleneck_diagnosis",
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            critique_data = json.loads(
                (theme_dir / "bottleneck_diagnosis.critique.json").read_text(encoding="utf-8")
            )
            self.assertEqual(critique_data["recommendation"], "accept")

    def test_mocked_adapter_bad_shape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp) / "hbm4"
            self.assertEqual(main(["split", str(self.hbm4_path), str(theme_dir)]), 0)

            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.return_value = json.dumps({"recommendation": "accept"})

            with patch("fundamental_research_engine.cli.get_adapter", return_value=fake_adapter):
                exit_code = main(
                    [
                        "critique",
                        str(theme_dir),
                        "--stage",
                        "bottleneck_diagnosis",
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--max-attempts",
                        "1",
                        "--project-root",
                        str(self.project_root),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse((theme_dir / "bottleneck_diagnosis.critique.json").exists())

    def test_critique_requires_stage_to_already_be_drafted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = _theme_dir_with_definition_only(self.hbm4_path, Path(tmp))

            with self.assertRaises(SystemExit):
                main(
                    [
                        "critique",
                        str(theme_dir),
                        "--stage",
                        "mechanism_analysis",
                        "--project-root",
                        str(self.project_root),
                    ]
                )


class QcCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def _valid_review(self) -> dict:
        return {
            "lenses": {
                "premortem": {"findings": []},
                "steelman_bear": {"counter_thesis_strength": "moderate", "strongest_disconfirmers": [], "assessment": "ok"},
                "consistency": {"issues": []},
                "unsupported_claims": {"items": []},
            },
            "open_concerns": [{"severity": "high", "target": "thesis", "issue": "unsupported ASP", "suggested_fix": "add source"}],
            "recommendation": "revise",
        }

    def test_grounding_only_writes_scorecard_without_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "qc.json"
            exit_code = main(
                ["qc", str(self.hbm4_path), "--grounding-only", "--project-root", str(self.project_root), "--out", str(out)]
            )
            self.assertEqual(exit_code, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertIsNone(report["review"])
            self.assertIn("grounding_score", report["quality_scorecard"])
            self.assertFalse(report["quality_scorecard"]["disconfirmation"]["premortem_done"])

    def test_mocked_adapter_runs_adversarial_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "qc.json"
            fake_adapter = unittest.mock.Mock()
            fake_adapter.complete.return_value = json.dumps(self._valid_review())
            with patch("fundamental_research_engine.cli.get_adapter", return_value=fake_adapter):
                exit_code = main(
                    [
                        "qc",
                        str(self.hbm4_path),
                        "--model",
                        "openai",
                        "--model-name",
                        "gpt-test",
                        "--project-root",
                        str(self.project_root),
                        "--out",
                        str(out),
                    ]
                )
            self.assertEqual(exit_code, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["review"]["recommendation"], "revise")
            disc = report["quality_scorecard"]["disconfirmation"]
            self.assertTrue(disc["premortem_done"] and disc["steelman_done"])
            self.assertEqual(disc["open_critical"], 1)

    def test_review_file_is_used_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "review.json"
            review_path.write_text(json.dumps(self._valid_review()), encoding="utf-8")
            exit_code = main(
                ["qc", str(self.hbm4_path), "--review", str(review_path), "--project-root", str(self.project_root)]
            )
            self.assertEqual(exit_code, 0)

    def test_strict_fails_on_open_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "review.json"
            review_path.write_text(json.dumps(self._valid_review()), encoding="utf-8")
            exit_code = main(
                [
                    "qc",
                    str(self.hbm4_path),
                    "--review",
                    str(review_path),
                    "--strict",
                    "--project-root",
                    str(self.project_root),
                ]
            )
            self.assertEqual(exit_code, 1)


class CalibrateCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.hbm4_path = self.project_root / "configs" / "themes" / "hbm4.json"

    def test_register_resolve_and_qc_uses_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            track = Path(tmp) / "hbm4.json"

            # register predictions
            self.assertEqual(
                main(["calibrate", str(self.hbm4_path), "--register", "--track-record", str(track), "--project-root", str(self.project_root)]),
                0,
            )
            record = json.loads(track.read_text(encoding="utf-8"))
            self.assertGreater(len(record["predictions"]), 0)
            key = record["predictions"][0]["key"]

            # resolve one with a probability
            self.assertEqual(
                main(
                    [
                        "calibrate", str(self.hbm4_path), "--resolve", key, "--outcome", "true",
                        "--probability", "0.7", "--as-of", "2026-06-01",
                        "--track-record", str(track), "--project-root", str(self.project_root),
                    ]
                ),
                0,
            )
            record = json.loads(track.read_text(encoding="utf-8"))
            self.assertTrue(record["predictions"][0]["resolved"])

            # qc picks up the track record calibration
            out = Path(tmp) / "qc.json"
            self.assertEqual(
                main(
                    [
                        "qc", str(self.hbm4_path), "--grounding-only",
                        "--track-record", str(track), "--out", str(out), "--project-root", str(self.project_root),
                    ]
                ),
                0,
            )
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["quality_scorecard"]["calibration"]["resolved"], 1)
            self.assertIsNotNone(report["quality_scorecard"]["calibration"]["brier"])

    def test_resolve_unknown_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            track = Path(tmp) / "hbm4.json"
            main(["calibrate", str(self.hbm4_path), "--register", "--track-record", str(track), "--project-root", str(self.project_root)])
            exit_code = main(
                ["calibrate", str(self.hbm4_path), "--resolve", "deadbeef", "--outcome", "false", "--track-record", str(track), "--project-root", str(self.project_root)]
            )
            self.assertEqual(exit_code, 1)


class SourcesSearchCliTest(unittest.TestCase):
    _HITS = [
        {
            "adsh": "0001039399-25-000023",
            "cik": "0001039399",
            "company": "FORMFACTOR INC (FORM)",
            "form": "10-K",
            "filed": "2025-02-21",
            "period_ending": "2024-12-28",
            "primary_doc": "form-20241228.htm",
            "title": "FORMFACTOR INC (FORM) 10-K filed 2025-02-21",
            "url": "https://www.sec.gov/Archives/edgar/data/1039399/000103939925000023/form-20241228.htm",
        }
    ]

    def test_search_writes_evidence_shaped_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sources.json"
            with patch("fundamental_research_engine.cli.search_filings", return_value=self._HITS) as mocked:
                exit_code = main(["sources", "search", "high bandwidth memory", "--forms", "10-K", "--out", str(out)])
            self.assertEqual(exit_code, 0)
            mocked.assert_called_once()
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["count"], 1)
            src = report["sources"][0]
            self.assertEqual(src["id"], "S1")
            self.assertEqual(src["source_type"], "regulatory_filing")
            self.assertTrue(src["url"].startswith("https://www.sec.gov/Archives/"))


if __name__ == "__main__":
    unittest.main()
