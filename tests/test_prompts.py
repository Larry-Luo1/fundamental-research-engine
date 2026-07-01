from __future__ import annotations

import json
import unittest
from pathlib import Path

from fundamental_research_engine.prompts import default_methodology_path, render_stage_prompt
from fundamental_research_engine.stages import STAGE_ORDER, split_theme_dict


class PromptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.prompts_dir = self.project_root / "prompts"
        self.ontology = json.loads(
            (self.project_root / "knowledge" / "ontology.json").read_text(encoding="utf-8")
        )
        self.theme = json.loads(
            (self.project_root / "configs" / "themes" / "hbm4.json").read_text(encoding="utf-8")
        )
        self.methodology = json.loads(
            default_methodology_path(self.project_root, "technology_adoption").read_text(encoding="utf-8")
        )

    def test_every_stage_template_renders_without_leftover_placeholders(self) -> None:
        stages = split_theme_dict(self.theme)
        completed: dict[str, dict] = {}
        for stage in STAGE_ORDER:
            prompt = render_stage_prompt(stage, self.prompts_dir, completed, self.ontology, self.methodology)
            self.assertNotIn("{{", prompt)
            self.assertNotIn("}}", prompt)
            self.assertIn("Return ONLY the JSON object for this stage", prompt)
            completed[stage] = stages[stage]

    def test_theme_definition_prompt_lists_its_own_schema_fields(self) -> None:
        prompt = render_stage_prompt("theme_definition", self.prompts_dir, {}, self.ontology)
        for field in ["id", "title", "as_of", "theme_type", "domain", "core_question", "thesis"]:
            self.assertIn(field, prompt)
        self.assertIn("technology_adoption", prompt)  # from ontology.theme_types

    def test_later_stage_prompt_embeds_upstream_context(self) -> None:
        stages = split_theme_dict(self.theme)
        completed = {"theme_definition": stages["theme_definition"]}
        prompt = render_stage_prompt(
            "mechanism_analysis", self.prompts_dir, completed, self.ontology, self.methodology
        )
        self.assertIn(self.theme["core_question"], prompt)

    def test_unknown_stage_raises(self) -> None:
        with self.assertRaises(ValueError):
            render_stage_prompt("not_a_stage", self.prompts_dir, {}, self.ontology)

    def test_missing_template_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            render_stage_prompt("theme_definition", self.project_root / "nonexistent_prompts", {}, self.ontology)


if __name__ == "__main__":
    unittest.main()
