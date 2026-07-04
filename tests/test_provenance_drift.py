"""Anti-drift guard for committed claim provenance.

The committed `data/evidence/<theme>/claims.json` sidecars are a *scoring input*:
`build_causal_quality` trusts each record's `verified` flag when rating causal
edges. If someone edits a theme's evidence/quotes without regenerating
provenance, that flag would silently go stale and inflate causal quality.

Each `configs/provenance/<theme>.json` spec embeds the `source_text`, so we can
re-run the deterministic quote verification offline and assert it still holds for
every committed record. If this fails, regenerate provenance (fre build-provenance)
before committing the theme change.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from fundamental_research_engine.pipeline import load_and_validate_theme
from fundamental_research_engine.provenance import build_provenance_records

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_DIR = PROJECT_ROOT / "configs" / "provenance"


class ProvenanceDriftTest(unittest.TestCase):
    def test_committed_provenance_specs_still_verify(self) -> None:
        specs = sorted(PROVENANCE_DIR.glob("*.json"))
        self.assertTrue(specs, "no provenance specs found")

        for spec_path in specs:
            with self.subTest(spec=spec_path.name):
                theme_path = PROJECT_ROOT / "configs" / "themes" / spec_path.name
                self.assertTrue(theme_path.exists(), f"no theme config for {spec_path.name}")

                theme = load_and_validate_theme(theme_path, PROJECT_ROOT)
                spec = json.loads(spec_path.read_text(encoding="utf-8"))

                result = build_provenance_records(
                    theme,
                    spec,
                    spec_dir=PROVENANCE_DIR,
                    make_record=lambda evidence, kept, source_text: kept,
                )

                self.assertEqual(
                    result.errors,
                    [],
                    f"{spec_path.name}: provenance drifted — every claim_id must exist and every "
                    f"quote must still verify against its source_text. Regenerate with build-provenance.",
                )
                # Every spec record must produce a record (nothing silently dropped).
                self.assertEqual(len(result.records), len(spec["records"]))


if __name__ == "__main__":
    unittest.main()
