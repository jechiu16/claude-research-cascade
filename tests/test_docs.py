from __future__ import annotations

import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_package_versions_are_consistent(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        from research_harness import __version__

        declared = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
        self.assertIsNotNone(declared)
        self.assertEqual(declared.group(1), __version__)

    def test_bindings_use_posture_and_tier(self) -> None:
        for relative in ("SKILL.md", "AGENTS.md", "HARNESS.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("posture", text.lower())
                self.assertIn("tier", text.lower())
                self.assertNotIn("depth x independence x strictness", text.lower())

    def test_readmes_reference_v2_cli(self) -> None:
        for relative in ("README.md", "README.zh-TW.md"):
            with self.subTest(path=relative):
                self.assertIn(
                    "scripts/research_state.py",
                    (ROOT / relative).read_text(encoding="utf-8"),
                )

    def test_product_identity_is_host_neutral(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "agent-deep-research-trigger"', pyproject)
        for relative in ("README.md", "README.zh-TW.md", "SKILL.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("Agent Deep Research Trigger", text)
                self.assertIn("Claude Code", text)
                self.assertIn("Codex", text)

    def test_both_hosts_have_project_skill_discovery_wrappers(self) -> None:
        wrappers = (
            ".claude/skills/deep/SKILL.md",
            ".agents/skills/deep/SKILL.md",
        )
        canonical = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for relative in wrappers:
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("../../../SKILL.md", text)
                self.assertIn("name: deep", text)
                self.assertIn("description:", text)
        self.assertIn("shared by\nClaude Code and OpenAI Codex", canonical)

    def test_readmes_use_official_host_skill_locations(self) -> None:
        combined = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in ("README.md", "README.zh-TW.md")
        )
        self.assertIn("$HOME/.claude/skills/deep", combined)
        self.assertIn("$HOME/.agents/skills/deep", combined)

    def test_source_distribution_includes_agent_skill_files(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        for required in (
            "SKILL.md",
            "AGENTS.md",
            "HARNESS.md",
            ".claude",
            ".agents",
        ):
            with self.subTest(path=required):
                self.assertIn(required, manifest)

    def test_current_scenarios_use_v2_contract_vocabulary(self) -> None:
        scenarios = (ROOT / "SCENARIOS.md").read_text(encoding="utf-8").lower()
        self.assertIn("posture", scenarios)
        self.assertIn("tier", scenarios)
        for legacy in ("three-axis", "preset: fast", "preset: standard"):
            with self.subTest(term=legacy):
                self.assertNotIn(legacy, scenarios)

    def test_readme_front_matter_is_searchable_and_focused(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        opening = "\n".join(readme.splitlines()[:20]).lower()
        for phrase in (
            "agent deep research trigger",
            "deep research",
            "agent skill",
            "claude code",
            "openai codex",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, opening)
        self.assertLessEqual(len(readme.splitlines()), 260)

    def test_active_identity_files_do_not_use_retired_brand(self) -> None:
        for relative in (
            "README.md",
            "README.zh-TW.md",
            "SKILL.md",
            "AGENTS.md",
            "HARNESS.md",
            "pyproject.toml",
        ):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8").lower()
                self.assertNotIn("claude-research-cascade", text)

    def test_runtime_docs_name_registry_and_provider_portfolio(self) -> None:
        for relative in ("README.md", "README.zh-TW.md", "HARNESS.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8").lower()
                self.assertIn("provider", text)
                self.assertIn("registry", text)

    def test_foundation_discloses_external_routes_are_not_v2_bound(self) -> None:
        for relative in ("README.md", "README.zh-TW.md", "HARNESS.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8").lower()
                self.assertIn("external", text)
                self.assertIn("disabled", text)
                self.assertIn("worker", text)

    def test_runtime_docs_require_confirmation_validation_and_render(self) -> None:
        for relative in ("SKILL.md", "AGENTS.md", "HARNESS.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8").lower()
                self.assertIn("confirm", text)
                self.assertIn("validate", text)
                self.assertIn("render", text)

    def test_docs_do_not_claim_key_readiness_is_execution_readiness(self) -> None:
        combined = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8").lower()
            for relative in ("README.md", "README.zh-TW.md", "HARNESS.md")
        )
        self.assertIn("credential", combined)
        self.assertIn("execution readiness", combined)

    def test_organizer_docs_define_traditional_chinese_report_boundary(self) -> None:
        for relative in ("SKILL.md", "AGENTS.md", "HARNESS.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("Traditional Chinese", text)
                self.assertIn("exact evidence excerpts", text)
                self.assertIn("source titles", text)
        for relative in ("README.md", "README.zh-TW.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("zh-Hant-TW", text)


if __name__ == "__main__":
    unittest.main()
