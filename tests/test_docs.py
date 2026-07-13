from __future__ import annotations

import json
import unittest
from pathlib import Path

from research_harness.providers import load_provider_registry


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def section(self, text: str, heading: str, next_heading: str | None = None) -> str:
        start = text.index(heading)
        end = text.index(next_heading, start) if next_heading else len(text)
        return text[start:end]

    def test_trigger_card_is_one_nine_line_profile_card(self) -> None:
        text = self.read("SKILL.md")
        start = text.index("<!-- PURE_TRIGGER_CARD_START -->")
        end = text.index("<!-- PURE_TRIGGER_CARD_END -->", start)
        card = text[start:end].splitlines()[1:]
        self.assertEqual(
            card,
            [
                "問題：{正規化後的問題}",
                "Query Brief：{決策、範圍、成功條件各一句}",
                "建議：{light/standard/heavy}，因為{一個理由}",
                "Light：deep {a}｜search {b}｜free unlimited",
                "Standard：deep {a}｜search {b}｜free unlimited",
                "Heavy：deep {a}｜search {b}｜free unlimited",
                "D1：{最低成本 ready provider；候選與資料外送範圍}",
                "共通：背景執行；host 複驗並寫結論；交付 JSON + 繁體中文 HTML；超限即停並標註缺口",
                "開始：light｜standard｜heavy｜調整｜取消",
            ],
        )
        self.assertLessEqual(len(text.splitlines()), 60)
        self.assertIn("show exactly one completed card", " ".join(text.split()))

    def test_preconfirmation_allows_only_local_card_reads(self) -> None:
        text = self.read("SKILL.md")
        before = " ".join(
            self.section(text, "## Before Confirmation", "## After Confirmation").split()
        )
        for phrase in (
            "Do not search",
            "inspect the project",
            "call a provider",
            "start a worker",
            "Local profile/registry reads",
            "make no external request",
        ):
            self.assertIn(phrase, before)
        self.assertIn("one run", before)
        self.assertIn("Re-card only", before)

    def test_host_authorship_reverification_and_delivery_are_public_rules(self) -> None:
        text = " ".join(self.read("SKILL.md").split())
        for phrase in (
            "sole conclusion author",
            "buy breadth and structure only",
            "cannot support a canonical claim",
            "targeted re-verification",
            "Fix disproved claims",
            "mark unverifiable claims",
            "never withhold delivery",
            "Stop external calls at the confirmed count limit",
            "name the unresolved gap",
            "no hard gate",
            "no automatic provider bundle",
        ):
            self.assertIn(phrase, text)

    def test_harness_uses_repo_local_cli_and_one_internal_confirmation(self) -> None:
        text = self.read("HARNESS.md")
        bridge = self.section(text, "## Runtime Bridge", "## Contract Shape")
        self.assertIn('CLI="$ROOT/.venv/bin/deep-research-state"', bridge)
        self.assertIn('SESSION="/absolute/path/to/this-run-package"', bridge)
        self.assertIn('"$CLI" card', bridge)
        self.assertIn('"$CLI" prepare', bridge)
        self.assertIn('"$CLI" confirm', bridge)
        self.assertIn('"$CLI" init', bridge)
        self.assertIn("only user confirmation", bridge)
        self.assertIn("not a second prompt", bridge)
        self.assertNotIn("scripts/research_state.py", text)
        self.assertNotIn("command -v", text)

    def test_harness_contract_and_cost_classes_match_runtime(self) -> None:
        text = self.read("HARNESS.md")
        normalized = " ".join(text.split())
        for phrase in (
            '"research_workflow": "host_led_v1"',
            '"conclusion_author": "host"',
            '"provider_reports_role": "discovery_only"',
            '"deep": 1',
            '"search": 15',
            '"free": "unlimited"',
            "New tools enter a class, never a profile",
            "credential is not execution readiness",
            "budget_exhausted",
            "targeted_reverification",
        ):
            self.assertIn(phrase, normalized)

        profiles = json.loads(self.read("research_harness/budget_profiles.json"))["profiles"]
        self.assertEqual(profiles["light"], {"deep": 0, "search": 5, "free": "unlimited"})
        self.assertEqual(profiles["standard"], {"deep": 1, "search": 15, "free": "unlimited"})
        self.assertEqual(profiles["heavy"], {"deep": 2, "search": 30, "free": "unlimited"})

        registry = load_provider_registry()
        enabled = [provider for provider in registry["providers"] if provider["enabled"]]
        self.assertTrue(all(provider["cost_class"] in {"deep", "search", "free"} for provider in enabled))
        deep = sorted(
            (provider for provider in enabled if provider["cost_class"] == "deep"),
            key=lambda provider: provider["cost_rank"],
        )
        self.assertEqual([provider["id"] for provider in deep], ["perplexity", "gemini-deep", "openai-deep"])

    def test_harness_preserves_evidence_and_gap_statuses(self) -> None:
        text = self.read("HARNESS.md")
        for phrase in (
            "claim -> evidence -> source + source_origin -> raw artifact",
            "證據不足 / EVIDENCE_INSUFFICIENT",
            "交付不完整 / DELIVERY_INCOMPLETE",
            "still writes `report.html`",
            "Traditional Chinese",
            "`檢查方式 => 預期結果`",
        ):
            self.assertIn(phrase, text)

    def test_agents_and_wrappers_keep_one_protocol(self) -> None:
        agents = self.read("AGENTS.md")
        self.assertIn("not a second public", agents)
        self.assertIn("conclusion author", agents)
        self.assertIn("after profile confirmation", agents)
        self.assertIn("do not reimplement", agents)
        for relative in (".claude/skills/deep/SKILL.md", ".agents/skills/deep/SKILL.md"):
            wrapper = self.read(relative)
            self.assertIn("discovery wrapper", wrapper.lower())
            self.assertIn("../../../SKILL.md", wrapper)

    def test_readmes_explain_problem_profiles_demo_and_outputs(self) -> None:
        expectations = {
            "README.md": (
                "## Why This Exists",
                "## What You Get",
                "## How Quality Is Earned",
                "## Profiles",
                "## Demo",
                "## Outputs",
            ),
            "README.zh-TW.md": (
                "## 為什麼需要它",
                "## 產出長什麼樣",
                "## 品質怎麼來",
                "## Profiles",
                "## Demo",
                "## 輸出",
            ),
        }
        for relative, headings in expectations.items():
            text = self.read(relative)
            for heading in headings:
                self.assertIn(heading, text)
            self.assertLessEqual(len(text.splitlines()), 180)
            for phrase in (
                "Host",
                "D1/D2",
                "Targeted re-verification",
                "Light",
                "Standard",
                "Heavy",
                "state.json",
                "events.jsonl",
                "raw/",
                "report.html",
                "No second full Markdown" if relative == "README.md" else "不另外產生第二份完整 Markdown",
            ):
                self.assertIn(phrase, text)
            self.assertNotIn("## Tiers", text)

    def test_readmes_share_native_architecture(self) -> None:
        for relative in ("README.md", "README.zh-TW.md"):
            text = self.read(relative)
            start = text.index("```mermaid")
            end = text.index("```", start + len("```mermaid"))
            diagram = text[start:end]
            for term in (
                "Host Organizer",
                "D1 / optional D2",
                "Targeted re-verification",
                "deep-research-state CLI",
                "research_harness/",
                "source_origin",
                "state.json",
                "report.html",
            ):
                self.assertIn(term, diagram)

    def test_scenarios_pin_three_real_parallax_acceptance_questions(self) -> None:
        text = self.read("SCENARIOS.md")
        for profile in ("Light", "Standard", "Heavy"):
            self.assertIn(profile, text)
        self.assertEqual(text.count("\n/deep "), 3)
        self.assertIn("without manual runtime repair", text)
        self.assertIn("Provider report presented as evidence or final verdict", text)
        self.assertIn("Withholding the package", text)


if __name__ == "__main__":
    unittest.main()
