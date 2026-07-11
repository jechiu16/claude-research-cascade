from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
