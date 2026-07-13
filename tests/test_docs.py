from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from research_harness.contracts import contract_card_sha256


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def section(self, text: str, heading: str, next_heading: str | None = None) -> str:
        start = text.index(heading)
        end = text.index(next_heading, start) if next_heading else len(text)
        return text[start:end]

    def test_first_trigger_card_is_exactly_seven_lines(self) -> None:
        text = self.read("SKILL.md")
        start = text.index("<!-- PURE_TRIGGER_CARD_START -->")
        end = text.index("<!-- PURE_TRIGGER_CARD_END -->", start)
        card = text[start:end].splitlines()[1:]

        self.assertEqual(
            card,
            [
                "問題：{正規化後的問題}",
                "建議：{層級}，因為{一個理由}",
                "Low：只在對話中回答，附上連結。",
                "Medium：為具名缺口補上直接取得的來源，並交付套件。",
                "High：直接取得至少兩個不同來源，並交付套件。",
                "額外付費請求：{精確數量}；本機資料外送：{是／否}。",
                "開始：Low｜Medium｜High｜調整",
            ],
        )
        self.assertLessEqual(len(text.splitlines()), 60)

    def test_missing_question_still_returns_the_card_without_a_followup(self) -> None:
        text = " ".join(self.read("SKILL.md").split())
        self.assertIn("conversation text only", text)
        self.assertIn("問題：尚未提供研究問題", text)
        self.assertIn("建議：調整，因為需要先提供研究問題", text)
        self.assertIn("do not ask first", text)

    def test_tier_selection_has_zero_preselection_tools(self) -> None:
        text = self.read("SKILL.md")
        before = self.section(text, "## Before Selection", "## After Selection")
        normalized = " ".join(before.split())

        for phrase in (
            "do not call tools",
            "inspect research, project, runtime, or source material",
            "search the web",
            "run scripts",
            "start workers",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)
        self.assertIn("Low never reads or invokes the runtime", normalized)
        self.assertIn("read [HARNESS.md](HARNESS.md)", text)

    def test_paid_call_count_excludes_non_provider_actions(self) -> None:
        text = " ".join(self.read("SKILL.md").split())
        self.assertIn(
            "額外付費請求只計 provider/API paid calls；host-native retrieval、local、Organizer 不計，無計畫 external paid route 時預設為 0。",
            text,
        )

    def test_medium_high_bridge_defines_repo_local_cli_and_flow(self) -> None:
        text = self.read("HARNESS.md")
        bridge = self.section(text, "## Runtime Bridge", "## Internal Binding")
        normalized = " ".join(bridge.split())

        self.assertIn("absolute directory containing that canonical `SKILL.md`", normalized)
        self.assertIn('CLI="$ROOT/.venv/bin/deep-research-state"', bridge)
        self.assertIn('SESSION="/absolute/path/to/this-run-package"', bridge)
        self.assertIn("host-capture", bridge)
        self.assertIn('"$CLI" patch "$SESSION" --patch "/absolute/path/to/state-patch.json" --json', bridge)
        self.assertIn("acceptance_tests", bridge)
        self.assertIn("`檢查方式 => 預期結果`", bridge)
        self.assertIn("non-empty text on both sides", normalized)
        self.assertIn("adds no schema", normalized)
        self.assertIn("Set status before `validate` for PASS", normalized)
        self.assertIn("must not retain `IN_PROGRESS`", normalized)
        self.assertIn("--payload", bridge)
        self.assertIn("--marginal-purpose", bridge)
        self.assertIn("--fidelity host_rendered", bridge)
        self.assertNotIn("--input", bridge)
        self.assertNotIn("--purpose", bridge)
        self.assertNotIn("$ROOT/.deep", bridge)
        self.assertIn("Do not use `command -v`", normalized)

        flow = "init -> host-capture -> patch as needed -> validate -> render"
        self.assertIn(flow, normalized)
        command_lines = [line.strip() for line in bridge.splitlines() if line.strip().startswith('"$CLI"')]
        self.assertGreaterEqual(len(command_lines), 4)
        self.assertTrue(all(line.startswith('"$CLI"') for line in command_lines))

    def test_harness_commands_use_only_repo_local_cli(self) -> None:
        harness = self.read("HARNESS.md")
        bridge = self.section(harness, "## Runtime Bridge", "## Internal Binding")

        self.assertNotIn("$PY", harness)
        self.assertNotIn("scripts/research_state.py", harness)
        self.assertNotIn('$ROOT/<contract>', bridge)
        self.assertNotIn('$ROOT/<capture>', bridge)
        self.assertIn("/absolute/path/to/confirmed-contract.json", bridge)
        self.assertIn("/absolute/path/to/capture-file", bridge)

    def test_low_does_not_read_harness_before_selection(self) -> None:
        skill = self.read("SKILL.md")
        harness = self.read("HARNESS.md")
        before = self.section(skill, "## Before Selection", "## After Selection")
        normalized = " ".join(before.split())

        self.assertIn("Low never reads or invokes the runtime", normalized)
        self.assertIn("After Medium or High is selected", skill)
        self.assertIn("Low never reads or invokes this runtime", harness)

    def test_agents_and_wrappers_keep_one_protocol_with_discovery_exemption(self) -> None:
        agents = self.read("AGENTS.md")
        skill = self.read("SKILL.md")
        self.assertIn("not a second public protocol", agents)
        self.assertIn("Low does not read it", agents)
        self.assertIn("required internal runtime bridge", agents)
        self.assertIn("Host discovery may read", skill)
        self.assertIn("not a research action", skill)
        for relative in (".claude/skills/deep/SKILL.md", ".agents/skills/deep/SKILL.md"):
            with self.subTest(path=relative):
                self.assertIn("discovery wrapper", self.read(relative).lower())

    def test_shortfall_contract_uses_matching_human_and_html_reasons(self) -> None:
        for relative in ("SKILL.md", "HARNESS.md"):
            with self.subTest(path=relative):
                text = self.read(relative)
                self.assertIn("BLOCKED", text)
                self.assertIn("證據不足", text)
                self.assertIn("EVIDENCE_INSUFFICIENT", text)
                self.assertIn("交付不完整", text)
                self.assertIn("DELIVERY_INCOMPLETE", text)

        for relative in ("README.md", "README.zh-TW.md"):
            with self.subTest(path=relative):
                text = self.read(relative)
                self.assertIn("EVIDENCE_INSUFFICIENT", text)
                self.assertIn("DELIVERY_INCOMPLETE", text)
                self.assertIn("PASS", text)

    def test_readmes_have_four_step_b6_clone_link_happy_path(self) -> None:
        expectations = {
            "README.md": (
                "## Quickstart",
                "## Tiers",
                (
                    "1. **Install the tagged skill and runtime.**",
                    "2. **Link it to one host.**",
                    "3. **Start a fresh session**",
                    "4. **Type `/deep` with a research question, then choose a tier.**",
                ),
            ),
            "README.zh-TW.md": (
                "## 快速開始",
                "## Tiers",
                (
                    "1. **安裝指定 tag 的完整 skill 與 runtime。**",
                    "2. **連結到一個 host。**",
                    "3. **開啟新的 session，**",
                    "4. **輸入 `/deep` 與研究問題，再選擇 tier。**",
                ),
            ),
        }

        for relative, (heading, next_heading, steps) in expectations.items():
            with self.subTest(path=relative):
                text = self.read(relative)
                quickstart = self.section(text, heading, next_heading)
                positions = [quickstart.index(step) for step in steps]
                self.assertEqual(positions, sorted(positions))
                self.assertIn("v2.0.0b6", quickstart)
                self.assertIn("python3 -m venv .venv", quickstart)
                self.assertIn(".venv/bin/python -m pip install -e .", quickstart)
                self.assertIn('ln -s "$PWD" "$HOME/.claude/skills/deep"', quickstart)
                self.assertIn('ln -s "$PWD" "$HOME/.agents/skills/deep"', quickstart)
                for tier in ("Low", "Medium", "High"):
                    self.assertIn(tier, text)
                self.assertIn("Canonical JSON", text)
                self.assertIn("zh-Hant-TW", text)

    def test_readmes_keep_product_surface_and_hide_runtime_armor(self) -> None:
        required_headings = {
            "README.md": ("## Quickstart", "## Tiers", "## Outputs", "## Project Links", "## License"),
            "README.zh-TW.md": ("## 快速開始", "## Tiers", "## 輸出", "## 專案連結", "## License"),
        }
        engineering_terms = (
            "summary.status",
            "tier_contract_met",
            "host-capture",
            "deep-research-release-gate",
            "wheel",
            "sdist",
            "```mermaid",
        )

        for relative, headings in required_headings.items():
            with self.subTest(path=relative):
                text = self.read(relative)
                for heading in headings:
                    with self.subTest(heading=heading):
                        self.assertIn(heading, text)
                self.assertLessEqual(len(text.splitlines()), 90)
                for term in engineering_terms:
                    with self.subTest(term=term):
                        self.assertNotIn(term, text.lower())
                self.assertIn("HARNESS.md", text)
                self.assertIn("CONTRIBUTING.md", text)
                self.assertIn("SECURITY.md", text)

    def test_readmes_link_to_bounded_blind_comparison(self) -> None:
        example = "examples/paired/2026-07-13-sqlite-wal-blind/"
        boundaries = {
            "README.md": "not evidence of general superiority",
            "README.zh-TW.md": "不能證明普遍優於",
        }
        for relative, boundary in boundaries.items():
            with self.subTest(path=relative):
                text = self.read(relative)
                self.assertIn(example, text)
                self.assertIn(boundary, text)

        artifacts = (
            "task.md",
            "adjudication.md",
            "direct-deep-research.md",
            "deep-high.md",
            "blind-verdict.md",
        )
        for name in artifacts:
            with self.subTest(artifact=name):
                self.assertTrue((ROOT / example / name).is_file())

    def test_version_and_release_note_are_b6(self) -> None:
        pyproject = self.read("pyproject.toml")
        changelog = self.read("CHANGELOG.md")

        self.assertIsNotNone(re.search(r'^version = "2\.0\.0b6"$', pyproject, re.MULTILINE))
        self.assertIn("## 2.0.0b6", changelog.split("## 2.0.0b5", 1)[0])
        b6 = changelog.split("## 2.0.0b5", 1)[0]
        for term in (
            "host-capture",
            "v2.0.0b6",
            "證據不足",
            "EVIDENCE_INSUFFICIENT",
            "交付不完整",
            "DELIVERY_INCOMPLETE",
        ):
            with self.subTest(term=term):
                self.assertIn(term, b6)

    def test_harness_execution_acceptance_and_high_verifier_rules(self) -> None:
        harness = " ".join(self.read("HARNESS.md").split())
        self.assertIn("Organizer/host home execution mode", harness)
        self.assertIn("does not exclude an optional external provider route", harness)
        self.assertIn("stage-map entry and request boundary", harness)
        self.assertIn("apply equally to `host_native` and `external_managed`", harness)
        self.assertIn("`檢查方式 => 預期結果`", harness)
        self.assertIn("High MUST include a fresh, context-separated analyst pass", harness)
        for field in (
            "verifier_actor != candidate_actor",
            "packet_claim_ids",
            "recomputable `packet_sha256`",
            "`verdict` in `accept/revise/block`",
            "disposition",
            "completed=true",
            "context_separated=true",
            "produced_candidate=false",
        ):
            with self.subTest(field=field):
                self.assertIn(field, harness)
        self.assertIn("host attestation plus canonical packet binding", harness)
        self.assertIn("proves neither context nor source independence", harness)
        self.assertIn("`host_native` verifier writes only the completed verifier record", harness)
        self.assertIn("no permit or attempt event", harness)
        self.assertIn("`external_managed` verifier additionally requires", harness)
        self.assertIn("completed organizer-pass action", harness)

    def test_version_metadata_matches_runtime_source(self) -> None:
        pyproject = self.read("pyproject.toml")
        declared = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
        self.assertIsNotNone(declared)

        from research_harness import __version__

        self.assertEqual(declared.group(1), __version__)
        self.assertEqual(__version__, "2.0.0b6")

    def test_active_identity_has_no_retired_brand(self) -> None:
        for relative in ("README.md", "README.zh-TW.md", "SKILL.md", "AGENTS.md", "HARNESS.md"):
            with self.subTest(path=relative):
                self.assertNotIn("claude-research-cascade", self.read(relative).lower())

    def test_scenarios_use_current_posture_tier_vocabulary(self) -> None:
        scenarios = self.read("SCENARIOS.md").lower()
        self.assertIn("posture", scenarios)
        self.assertIn("tier", scenarios)
        for retired in ("three-axis", "preset: fast", "preset: standard"):
            with self.subTest(term=retired):
                self.assertNotIn(retired, scenarios)

    def test_harness_distinguishes_credentials_from_execution_readiness(self) -> None:
        harness = self.read("HARNESS.md").lower()
        self.assertIn("credential", harness)
        self.assertIn("execution readiness", harness)
        self.assertIn("not execution readiness", harness)

    def test_skill_bindings_and_source_manifest_remain_present(self) -> None:
        skill = self.read("SKILL.md")
        self.assertIn("Claude Code", skill)
        self.assertIn("OpenAI Codex", skill)
        for relative in (".claude/skills/deep/SKILL.md", ".agents/skills/deep/SKILL.md"):
            with self.subTest(path=relative):
                wrapper = self.read(relative)
                self.assertIn("../../../SKILL.md", wrapper)
                self.assertIn("name: deep", wrapper)

        manifest = self.read("MANIFEST.in")
        for required in (
            "SKILL.md",
            "AGENTS.md",
            "HARNESS.md",
            ".claude",
            ".agents",
            "examples/paired",
        ):
            with self.subTest(path=required):
                self.assertIn(required, manifest)

    def test_v2_medium_fixture_is_host_native_and_readme_is_portable(self) -> None:
        fixture = json.loads(self.read("examples/v2/medium-contract.json"))
        self.assertEqual(fixture["execution"], "host_native")
        self.assertEqual(
            fixture["confirmation"]["card_sha256"],
            contract_card_sha256(fixture),
        )

        readme = self.read("examples/v2/README.md")
        self.assertIn('CLI="$ROOT/.venv/bin/deep-research-state"', readme)
        self.assertIn("intentional evidence-shortfall fixture", readme)
        self.assertIn("`validate` exits `2`", readme)
        self.assertIn("set -e", readme)
        self.assertIn('"$CLI" validate "$SESSION" --json || VALIDATE_EXIT=$?', readme)
        self.assertLess(readme.index("validate \"$SESSION\""), readme.index("render \"$SESSION\""))
        self.assertNotIn("/Users/jechiu/dev/parallax", readme)
        self.assertNotIn("scripts/research_state.py", readme)

    def test_public_v2_example_does_not_teach_hash_confirmation_ceremony(self) -> None:
        readme = self.read("examples/v2/README.md").lower()
        for phrase in (
            "run `prepare`",
            "show the returned card",
            "three hashes",
            "call `confirm` only after",
        ):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, readme)


if __name__ == "__main__":
    unittest.main()
