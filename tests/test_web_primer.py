"""Offline service-level tests for the primer web flow.

Imports web.service directly (no FastAPI needed) and patches build_primer so no
network or model is touched. The real build_primer is covered in test_primer.py.
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from web.config import Config
from web.service import Service, model_config_issue


def _config(tmp: Path) -> Config:
    return Config(
        password="pw",
        api_key="sk-ant-test",
        model="claude",
        model_name="claude-opus-4-8",
        max_tokens=16000,
        max_attempts=2,
        max_concurrency=4,
        data_dir=tmp,
        cookie_secret=hashlib.sha256(b"x").digest(),
        host="127.0.0.1",
        port=8000,
    )


def _primer_result():
    return {
        "topic": "HBM",
        "resolved_title": "High Bandwidth Memory",
        "seed_used": True,
        "primer": {
            "explainer": "stacked memory",
            "glossary": [],
            "landscape": [],
            "state_of_play": "tight",
            "maturity": {"hype_stage": "enlightenment", "technology_readiness_level": 7},
            "key_debates": [],
            "key_claims": [],
            "candidate_framings": [
                {
                    "id": "f1",
                    "title": "HBM supply bottleneck",
                    "core_question": "Is HBM a durable bottleneck?",
                    "thesis_hypothesis": "HBM stays constrained.",
                    "theme_type": "technology_adoption",
                    "domain": "ai",
                    "drivers": ["accelerator demand"],
                }
            ],
            "suggested_sources": [],
        },
        "fetched_sources": [],
        "unverified_claims": [],
    }


def _drain(agen):
    async def run():
        return [event async for event in agen]

    return asyncio.run(run())


class PrimerServiceTest(unittest.TestCase):
    def test_create_and_generate_and_promote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = Service(_config(Path(tmp)))
            sid = service.create_primer("HBM")
            self.assertIsNone(service.get_primer(sid)["primer"])

            with mock.patch("web.service.build_primer", return_value=_primer_result()), \
                 mock.patch("web.service.get_adapter", return_value=mock.Mock()):
                events = _drain(service.generate_primer(sid))

            self.assertEqual(events[-1]["event"], "done")
            stored = service.get_primer(sid)
            self.assertEqual(stored["meta"]["status"], "done")
            self.assertEqual(stored["primer"]["resolved_title"], "High Bandwidth Memory")
            audit_events = service.audit_events(20)
            self.assertIn("primer_created", {event.get("event") for event in audit_events})
            self.assertIn("primer_finished", {event.get("event") for event in audit_events})

            # promote the framing into a real analysis with a seeded theme_definition
            analysis_sid = service.promote_framing(sid, "f1")
            got = service.get_analysis(analysis_sid)
            self.assertEqual(got["meta"]["from_primer"], sid)
            self.assertIn("theme_definition", got["stages"])
            self.assertEqual(got["stages"]["theme_definition"]["theme_type"], "technology_adoption")

            # primers are excluded from the analysis list; the promoted analysis is included
            listed_ids = {item["id"] for item in service.list_analyses()}
            self.assertIn(analysis_sid, listed_ids)
            self.assertNotIn(sid, listed_ids)

    def test_empty_topic_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = Service(_config(Path(tmp)))
            with self.assertRaises(ValueError):
                service.create_primer("   ")

    def test_promote_unknown_framing_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = Service(_config(Path(tmp)))
            sid = service.create_primer("HBM")
            with mock.patch("web.service.build_primer", return_value=_primer_result()), \
                 mock.patch("web.service.get_adapter", return_value=mock.Mock()):
                _drain(service.generate_primer(sid))
            with self.assertRaises(ValueError):
                service.promote_framing(sid, "nope")

    def test_model_config_issue_catches_deepseek_key_in_claude_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = replace(_config(Path(tmp)), model="claude", api_key="sk-deepseek-looking-key")
            self.assertIn("DeepSeek Key", model_config_issue(config) or "")

    def test_model_config_issue_accepts_deepseek_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = replace(
                _config(Path(tmp)),
                model="deepseek",
                model_name="deepseek-v4-pro",
                api_key="sk-deepseek-looking-key",
            )
            self.assertIsNone(model_config_issue(config))


if __name__ == "__main__":
    unittest.main()
