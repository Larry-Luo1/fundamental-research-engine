from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fundamental_research_engine.evidence import build_evidence_audit, write_evidence_store
from fundamental_research_engine.models import theme_from_dict


class EvidenceAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        data = json.loads((project_root / "configs" / "themes" / "hbm4.json").read_text(encoding="utf-8"))
        self.theme = theme_from_dict(data)

    def test_build_evidence_audit_inventory_and_claims(self) -> None:
        audit = build_evidence_audit(
            self.theme.evidence,
            {
                "bottleneck": self.theme.bottlenecks,
                "company": self.theme.companies,
            },
        )

        self.assertEqual(audit["inventory"]["evidence_count"], 4)
        self.assertEqual(audit["inventory"]["claim_count"], 4)
        self.assertEqual(len(audit["claims"]), 4)
        self.assertEqual(audit["claims"][0]["id"], "E1.C1")
        self.assertEqual(audit["source_manifest"][0]["evidence_id"], "E1")

    def test_build_evidence_audit_scores_owner_coverage(self) -> None:
        audit = build_evidence_audit(
            self.theme.evidence,
            {
                "bottleneck": self.theme.bottlenecks,
                "company": self.theme.companies,
            },
        )

        by_owner = {item["owner_id"]: item for item in audit["coverage"]}
        self.assertEqual(by_owner["bn-hbm4-capacity-and-qualification"]["status"], "strong")
        self.assertEqual(by_owner["co-sk-hynix"]["evidence_ids"], ["E2"])
        self.assertGreater(audit["summary"]["average_coverage_score"], 0.0)

    def test_write_evidence_store_creates_raw_normalized_claim_and_audit_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_evidence_store(
                self.theme.id,
                self.theme.evidence,
                {
                    "bottleneck": self.theme.bottlenecks,
                    "company": self.theme.companies,
                },
                Path(tmp),
            )

            raw_e1 = Path(tmp) / "data" / "raw_sources" / "hbm4" / "E1.json"
            self.assertTrue(raw_e1.exists())
            self.assertTrue(Path(paths["normalized_evidence_path"]).exists())
            self.assertTrue(Path(paths["claims_path"]).exists())
            self.assertTrue(Path(paths["coverage_path"]).exists())
            self.assertTrue(Path(paths["audit_path"]).exists())
            self.assertTrue(Path(paths["manifest_path"]).exists())

            normalized = json.loads(Path(paths["normalized_evidence_path"]).read_text(encoding="utf-8"))
            claims = json.loads(Path(paths["claims_path"]).read_text(encoding="utf-8"))
            manifest = json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8"))

            self.assertEqual(normalized["records"][0]["claim_ids"], ["E1.C1"])
            self.assertEqual(claims["records"][0]["claim_id"], "E1.C1")
            self.assertEqual(manifest["evidence_count"], 4)
            self.assertEqual(manifest["claim_count"], 4)


if __name__ == "__main__":
    unittest.main()
