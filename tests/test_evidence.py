from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fundamental_research_engine.evidence import (
    FetchResult,
    _strip_html,
    build_evidence_audit,
    default_fetch,
    write_evidence_store,
)
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

        self.assertEqual(audit["inventory"]["evidence_count"], 5)
        self.assertEqual(audit["inventory"]["claim_count"], 5)
        self.assertEqual(len(audit["claims"]), 5)
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
            self.assertEqual(manifest["evidence_count"], 5)
            self.assertEqual(manifest["claim_count"], 5)
            self.assertFalse(manifest["fetch_attempted"])
            self.assertEqual(manifest["fetch_results"], [])

            raw_e1 = json.loads(raw_e1.read_text(encoding="utf-8"))
            self.assertEqual(raw_e1["source_snapshot_type"], "theme_config_record")

    def test_write_evidence_store_merges_rich_claim_provenance(self) -> None:
        claim_text = self.theme.evidence[0].claims[0]
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_evidence_store(
                self.theme.id,
                self.theme.evidence,
                {
                    "bottleneck": self.theme.bottlenecks,
                    "company": self.theme.companies,
                },
                Path(tmp),
                rich_claims=[
                    {
                        "theme_id": self.theme.id,
                        "evidence_id": "E1",
                        "claim": claim_text,
                        "quote": "Data-center demand remains large",
                        "confidence": "high",
                        "bears_on": ["thesis", "bn-hbm4-capacity-and-qualification"],
                        "verified": True,
                        "source_title": self.theme.evidence[0].title,
                        "source_url": self.theme.evidence[0].url,
                        "source_sha256": "sourcehash",
                        "extracted_at": "2026-07-04T00:00:00+00:00",
                        "extraction_model": "manual",
                        "extraction_model_name": None,
                        "extraction_attempts": 0,
                    }
                ],
            )

            claims = json.loads(Path(paths["claims_path"]).read_text(encoding="utf-8"))
            record = next(item for item in claims["records"] if item["claim_id"] == "E1.C1")
            self.assertEqual(record["status"], "applied")
            self.assertEqual(record["quote"], "Data-center demand remains large")
            self.assertEqual(record["confidence"], "high")
            self.assertEqual(record["bears_on"], ["thesis", "bn-hbm4-capacity-and-qualification"])
            self.assertTrue(record["verified"])
            self.assertEqual(record["source_sha256"], "sourcehash")

            manifest = json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["quote_verified_claim_count"], 1)
            self.assertEqual(manifest["candidate_claim_count"], 0)

    def test_write_evidence_store_keeps_unapplied_rich_claims_as_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_evidence_store(
                self.theme.id,
                self.theme.evidence,
                {"bottleneck": self.theme.bottlenecks, "company": self.theme.companies},
                Path(tmp),
                rich_claims=[
                    {
                        "theme_id": self.theme.id,
                        "evidence_id": "E1",
                        "claim": "A candidate claim not yet present in the theme.",
                        "quote": "A candidate claim not yet present in the theme.",
                        "confidence": "medium",
                        "bears_on": ["thesis"],
                        "verified": True,
                    }
                ],
            )

            claims = json.loads(Path(paths["claims_path"]).read_text(encoding="utf-8"))
            candidate = next(item for item in claims["records"] if item["claim_id"] == "E1.Q1")
            self.assertEqual(candidate["status"], "candidate")
            self.assertEqual(candidate["claim"], "A candidate claim not yet present in the theme.")
            self.assertTrue(candidate["verified"])

            manifest = json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["quote_verified_claim_count"], 1)
            self.assertEqual(manifest["candidate_claim_count"], 1)

    def test_write_evidence_store_with_fetch_sources_uses_fetched_content(self) -> None:
        def fake_fetch(url: str) -> FetchResult:
            if url.endswith("E4"):
                return FetchResult(ok=False, status="error", error="boom")
            return FetchResult(
                ok=True,
                status="fetched",
                content_type="text/html",
                text="fetched body text",
                content_sha256="deadbeef",
                http_status=200,
                fetched_at="2026-07-02T00:00:00+00:00",
            )

        # give each evidence item a distinct fake url so fake_fetch can distinguish them
        evidence = [replace(item, url=f"https://example.com/{item.id}") for item in self.theme.evidence]

        with tempfile.TemporaryDirectory() as tmp:
            paths = write_evidence_store(
                self.theme.id,
                evidence,
                {"bottleneck": self.theme.bottlenecks, "company": self.theme.companies},
                Path(tmp),
                fetch_sources=True,
                fetch=fake_fetch,
            )

            raw_e1 = json.loads((Path(tmp) / "data" / "raw_sources" / "hbm4" / "E1.json").read_text(encoding="utf-8"))
            self.assertEqual(raw_e1["source_snapshot_type"], "fetched_url")
            self.assertEqual(raw_e1["fetched_text"], "fetched body text")
            self.assertEqual(raw_e1["content_sha256"], "deadbeef")

            raw_e4 = json.loads((Path(tmp) / "data" / "raw_sources" / "hbm4" / "E4.json").read_text(encoding="utf-8"))
            self.assertEqual(raw_e4["source_snapshot_type"], "theme_config_record")
            self.assertTrue(raw_e4["fetch_attempted"])
            self.assertEqual(raw_e4["fetch_error"], "boom")

            manifest = json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8"))
            self.assertTrue(manifest["fetch_attempted"])
            statuses = {item["evidence_id"]: item["status"] for item in manifest["fetch_results"]}
            self.assertEqual(statuses["E1"], "fetched")
            self.assertEqual(statuses["E4"], "error")


class StripHtmlTest(unittest.TestCase):
    def test_strips_tags_and_collapses_whitespace(self) -> None:
        html = "<html><body><h1>Title</h1>\n<p>Some   text.</p></body></html>"
        self.assertEqual(_strip_html(html), "Title Some text.")

    def test_removes_script_and_style_blocks(self) -> None:
        html = "<p>Visible</p><script>var x = 1;</script><style>.a{color:red}</style>"
        self.assertEqual(_strip_html(html), "Visible")

    def test_unescapes_html_entities(self) -> None:
        html = "<p>Fish &amp; Chips &mdash; caf&eacute;</p>"
        self.assertEqual(_strip_html(html), "Fish & Chips — café")


class DefaultFetchTest(unittest.TestCase):
    def test_rejects_unsupported_scheme(self) -> None:
        result = default_fetch("ftp://example.com/file.txt")
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "skipped_scheme")


if __name__ == "__main__":
    unittest.main()
