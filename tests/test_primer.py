from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from fundamental_research_engine.evidence import FetchResult
from fundamental_research_engine.primer import (
    build_primer,
    framing_to_theme_definition,
    validate_primer_shape,
    wikipedia_source,
)
from fundamental_research_engine.stages import validate_stage_shape

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = json.loads((PROJECT_ROOT / "knowledge" / "ontology.json").read_text(encoding="utf-8"))


def _fake_http_get(url: str):
    if "opensearch" in url:
        return ["HBM", ["High Bandwidth Memory"], ["stacked DRAM"], ["https://en.wikipedia.org/wiki/High_Bandwidth_Memory"]]
    if "/summary/" in url:
        return {
            "extract": "High Bandwidth Memory (HBM) is a stacked DRAM interface used with AI accelerators.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/High_Bandwidth_Memory"}},
        }
    raise AssertionError(f"unexpected url {url}")


def _valid_primer():
    return {
        "explainer": "HBM is stacked memory close to compute.",
        "glossary": [{"term": "TSV", "definition": "through-silicon via"}],
        "landscape": [{"segment": "memory", "role": "make HBM", "example_players": ["SK hynix"]}],
        "state_of_play": "Supply is tight.",
        "maturity": {"hype_stage": "enlightenment", "technology_readiness_level": 7, "rationale": "shipping"},
        "key_debates": [{"question": "Does supply catch up?", "bull": "no", "bear": "yes"}],
        "key_claims": [
            {"claim": "HBM sits close to compute.", "supported_by": ["S-wiki"], "verify": False},
            {"claim": "ASPs will rise 20%.", "supported_by": [], "verify": True},
        ],
        "candidate_framings": [
            {
                "id": "f1",
                "title": "HBM supply bottleneck",
                "core_question": "Is HBM a durable supply bottleneck?",
                "thesis_hypothesis": "HBM stays constrained through 2027.",
                "theme_type": "technology_adoption",
                "domain": "ai",
                "drivers": ["accelerator demand", "packaging capacity"],
            },
            {
                "id": "f2",
                "title": "HBM demand adoption",
                "core_question": "Does inference demand keep scaling HBM attach?",
                "thesis_hypothesis": "Long-context inference lifts HBM per-accelerator.",
                "theme_type": "consumer_adoption",
                "domain": "ai",
                "drivers": ["long-context inference"],
            },
        ],
        "suggested_sources": [
            {"title": "SK hynix IR", "url": "https://example.com/skhynix", "source_type": "company_disclosure", "reliability": "high", "why": "ASP mix"}
        ],
    }


class WikipediaSourceTest(unittest.TestCase):
    def test_resolves_topic(self) -> None:
        source = wikipedia_source("HBM", _fake_http_get)
        self.assertEqual(source["id"], "S-wiki")
        self.assertEqual(source["title"], "High Bandwidth Memory")
        self.assertIn("stacked DRAM", source["extract"])

    def test_returns_none_when_no_match(self) -> None:
        self.assertIsNone(wikipedia_source("zzz", lambda url: ["zzz", [], [], []]))

    def test_returns_none_on_error(self) -> None:
        def boom(url):
            raise OSError("network down")

        self.assertIsNone(wikipedia_source("HBM", boom))


class ValidatePrimerTest(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(validate_primer_shape(_valid_primer()), [])

    def test_missing_framings_flagged(self) -> None:
        data = _valid_primer()
        data["candidate_framings"] = []
        errors = validate_primer_shape(data)
        self.assertTrue(any("at least one framing" in e for e in errors))

    def test_bad_maturity_flagged(self) -> None:
        data = _valid_primer()
        data["maturity"] = {"hype_stage": "x"}
        errors = validate_primer_shape(data)
        self.assertTrue(any("technology_readiness_level" in e for e in errors))


class BuildPrimerTest(unittest.TestCase):
    def test_end_to_end_with_fakes(self) -> None:
        adapter = mock.Mock()
        adapter.complete.return_value = json.dumps(_valid_primer())
        fetch = mock.Mock(return_value=FetchResult(ok=True, status="fetched", text="hello world"))

        result = build_primer(
            "HBM",
            adapter,
            ontology=ONTOLOGY,
            prompts_dir=PROJECT_ROOT / "prompts",
            http_get=_fake_http_get,
            fetch=fetch,
        )

        self.assertEqual(result["resolved_title"], "High Bandwidth Memory")
        self.assertTrue(result["seed_used"])
        # seed + one suggested source fetched
        ids = [s["id"] for s in result["fetched_sources"]]
        self.assertEqual(ids, ["S-wiki", "S1"])
        self.assertEqual(result["fetched_sources"][1]["fetch_status"], "fetched")
        # only the unsupported/verify claim is surfaced as unverified
        self.assertEqual(result["unverified_claims"], ["ASPs will rise 20%."])

    def test_discover_folds_real_sources_into_result(self) -> None:
        adapter = mock.Mock()
        adapter.complete.return_value = json.dumps(_valid_primer())
        fetch = mock.Mock(return_value=FetchResult(ok=True, status="fetched", text="hello world"))
        discover = mock.Mock(return_value=[
            {"id": "US1", "title": "Micron 10-K", "source_type": "regulatory_filing",
             "date": "2025-01-01", "url": "https://sec.gov/x", "reliability": "high",
             "claims": [], "discovery": "edgar"},
            {"id": "CN1", "title": "长鑫 公告", "source_type": "regulatory_filing",
             "date": "2026-01-01", "url": "http://static.cninfo.com.cn/y", "reliability": "high",
             "claims": [], "discovery": "cninfo"},
        ])

        result = build_primer(
            "HBM", adapter, ontology=ONTOLOGY, prompts_dir=PROJECT_ROOT / "prompts",
            http_get=_fake_http_get, fetch=fetch, discover=discover,
        )

        discover.assert_called_once_with("HBM")
        self.assertEqual([s["id"] for s in result["discovered_sources"]], ["US1", "CN1"])
        self.assertEqual({s["discovery"] for s in result["discovered_sources"]}, {"edgar", "cninfo"})
        # discovered sources are also merged into the unified fetched_sources list
        ids = [s["id"] for s in result["fetched_sources"]]
        self.assertEqual(ids, ["S-wiki", "S1", "US1", "CN1"])
        self.assertTrue(all(s["fetch_status"] == "discovered" for s in result["discovered_sources"]))

    def test_discovery_off_by_default(self) -> None:
        adapter = mock.Mock()
        adapter.complete.return_value = json.dumps(_valid_primer())
        result = build_primer(
            "HBM", adapter, ontology=ONTOLOGY, prompts_dir=PROJECT_ROOT / "prompts",
            http_get=_fake_http_get, fetch=mock.Mock(return_value=FetchResult(ok=True, status="fetched", text="x")),
        )
        self.assertEqual(result["discovered_sources"], [])

    def test_raises_on_invalid_model_output(self) -> None:
        adapter = mock.Mock()
        adapter.complete.return_value = json.dumps({"explainer": "x"})
        with self.assertRaises(ValueError):
            build_primer("HBM", adapter, ontology=ONTOLOGY, prompts_dir=PROJECT_ROOT / "prompts",
                         http_get=_fake_http_get, fetch=mock.Mock(), max_attempts=1)


class FramingToThemeDefinitionTest(unittest.TestCase):
    def test_produces_valid_theme_definition_stage(self) -> None:
        primer_result = _valid_primer()
        definition = framing_to_theme_definition(
            primer_result["candidate_framings"][0], primer_result, as_of="2026-07-01", thesis_evidence_ids=["S-wiki"]
        )
        # The produced definition must satisfy the real stage contract.
        errors = validate_stage_shape("theme_definition", definition, ONTOLOGY)
        self.assertEqual(errors, [])
        self.assertEqual(definition["id"], "hbm-supply-bottleneck")
        self.assertEqual(definition["thesis_evidence_ids"], ["S-wiki"])


if __name__ == "__main__":
    unittest.main()
