"""Offline service-level tests for the watch-digest web endpoints.

Imports web.service directly (no FastAPI needed) and points the service's
project_root at a temp dir holding fake digests.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from web.config import Config
from web.service import Service


def _config(tmp: Path) -> Config:
    return Config(
        password="pw", api_key="", model="claude", model_name="claude-opus-4-8",
        max_tokens=16000, max_attempts=2, max_concurrency=4, data_dir=tmp,
        cookie_secret=hashlib.sha256(b"x").digest(), host="127.0.0.1", port=8000,
    )


def _write_digest(root: Path, as_of: str, watchlist: str, flagged_theme: str) -> None:
    date_dir = root / "reports" / "watch" / as_of
    date_dir.mkdir(parents=True, exist_ok=True)
    (date_dir / "digest.json").write_text(
        json.dumps({
            "as_of": as_of, "watchlist": watchlist,
            "summary": {"flagged": 1, "action": 1},
            "flagged": [{"theme_id": flagged_theme}],
        }),
        encoding="utf-8",
    )


class WatchDigestServiceTest(unittest.TestCase):
    def test_list_and_get_digests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = Service(_config(root / "data"))
            service.project_root = root
            _write_digest(root, "2026-06-27", "ai-compute", "hbm4")
            _write_digest(root, "2026-07-04", "ai-compute", "cowos")

            listing = service.list_watch_digests()
            self.assertEqual([d["as_of"] for d in listing], ["2026-07-04", "2026-06-27"])  # newest first
            self.assertEqual(listing[0]["watchlist"], "ai-compute")
            self.assertEqual(listing[0]["summary"]["flagged"], 1)

            full = service.get_watch_digest("2026-07-04")
            self.assertEqual(full["flagged"][0]["theme_id"], "cowos")

    def test_missing_and_unsafe_dates_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = Service(_config(Path(tmp) / "data"))
            service.project_root = Path(tmp)
            with self.assertRaises(KeyError):
                service.get_watch_digest("2099-01-01")
            with self.assertRaises(KeyError):
                service.get_watch_digest("../secrets")

    def test_empty_when_no_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = Service(_config(Path(tmp) / "data"))
            service.project_root = Path(tmp)
            self.assertEqual(service.list_watch_digests(), [])


if __name__ == "__main__":
    unittest.main()
