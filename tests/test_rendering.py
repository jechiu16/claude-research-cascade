from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from research_harness.rendering import render_html, render_session_result
from research_harness.state import state_sha256
from research_harness.storage import apply_state_patch, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, make_complete_pass_session


class RenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.session = make_complete_pass_session(self.root)
        self.state = load_state(self.session)
        self.report = validate_session(self.session)

    def test_same_state_renders_identical_bytes(self) -> None:
        first = render_session_result(self.session).path.read_bytes()
        second = render_session_result(self.session).path.read_bytes()
        self.assertEqual(first, second)

    def test_untrusted_content_is_escaped(self) -> None:
        state = copy.deepcopy(self.state)
        state["summary"]["decision"] = '<script>alert("x")</script>'
        document = render_html(state, self.report)
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)

    def test_html_embeds_current_state_hash(self) -> None:
        document = render_html(self.state, self.report)
        self.assertIn(state_sha256(self.state), document)

    def test_state_change_makes_existing_report_stale(self) -> None:
        render_session_result(self.session)
        revision = load_state(self.session)["session"]["revision"]
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/decision", "value": "changed"}],
            revision,
            NOW,
        )
        self.assertIn(
            "report.stale", {issue.code for issue in validate_session(self.session).errors}
        )

    def test_render_records_hash_bound_report_event(self) -> None:
        path = render_session_result(self.session).path
        event = read_events(self.session)[0][-1]
        self.assertEqual(event["event"], "report_generated")
        self.assertEqual(event["state_sha256"], state_sha256(load_state(self.session)))
        self.assertEqual(event["report_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_render_result_returns_exact_validation_and_hashes(self) -> None:
        result = render_session_result(self.session)
        self.assertTrue(result.validation.ok, result.validation.to_dict())
        self.assertEqual(result.state_sha256, state_sha256(load_state(self.session)))
        self.assertEqual(result.report_sha256, hashlib.sha256(result.path.read_bytes()).hexdigest())

    def test_report_has_no_script_or_external_assets(self) -> None:
        document = render_html(self.state, self.report)
        self.assertNotIn("<script", document.lower())
        self.assertNotIn("<link", document.lower())
        self.assertNotIn("@import", document.lower())

    def test_report_uses_traditional_chinese_chrome(self) -> None:
        document = render_html(self.state, self.report)
        self.assertIn('<html lang="zh-Hant-TW">', document)
        for label in (
            "有界研究 / 正式狀態投影",
            "有界結論",
            "研究契約",
            "成本層級",
            "研究模式",
            "初始搜尋路由",
            "實體請求上限",
            "正式主張",
            "證據紀錄",
            "來源標題",
            "來源層級",
            "上下文分離",
            "驗證",
            "工程交接",
            "待釐清問題",
            "決定性檢查結果",
        ):
            with self.subTest(label=label):
                self.assertIn(label, document)

    def test_report_preserves_dynamic_values_in_their_original_language(self) -> None:
        state = copy.deepcopy(self.state)
        state["framing"]["question"] = "Should cache remain enabled?"
        state["summary"]["decision"] = "Keep 42 workers <unchanged>."
        state["claims"][0]["text"] = "Original claim 42 <verbatim>"
        state["sources"][0]["title"] = "Original Source Title"
        state["evidence"][0]["excerpt"] = "Exact evidence 42 <verbatim>"
        document = render_html(state, self.report)
        self.assertIn("Should cache remain enabled?", document)
        self.assertIn("Keep 42 workers &lt;unchanged&gt;.", document)
        self.assertIn("Original claim 42 &lt;verbatim&gt;", document)
        self.assertIn("Original Source Title", document)
        self.assertIn("Exact evidence 42 &lt;verbatim&gt;", document)

    def test_empty_states_and_boolean_labels_are_traditional_chinese(self) -> None:
        state = copy.deepcopy(self.state)
        state["claims"] = []
        state["evidence"] = []
        state["sources"] = []
        state["verification"] = []
        state["engineering_handoff"]["safe_actions"] = []
        state["engineering_handoff"]["constraints"] = []
        state["engineering_handoff"]["acceptance_tests"] = []
        state["open_questions"] = []
        document = render_html(state, self.report)
        for label in (
            "尚未記錄正式主張",
            "尚未納入證據紀錄",
        ):
            with self.subTest(label=label):
                self.assertIn(label, document)
        unnamed_state = copy.deepcopy(self.state)
        unnamed_state["claims"] = [{}]
        self.assertIn("未命名主張", render_html(unnamed_state, self.report))

    def test_boolean_chrome_renders_true_and_false_explicitly(self) -> None:
        self.state["engineering_handoff"]["safe_actions"] = [
            {"id": "A1", "description": "test action", "reversible": True, "depends_on_claim_ids": []}
        ]
        self.state["verification"][0]["context_separated"] = True
        true_document = render_html(self.state, self.report)
        false_state = copy.deepcopy(self.state)
        false_state["sources"][0]["direct_fetch"] = False
        false_state["verification"][0]["completed"] = False
        false_state["verification"][0]["context_separated"] = False
        false_state["engineering_handoff"]["safe_actions"][0]["reversible"] = False
        false_document = render_html(false_state, self.report)

        for fragment in (
            "<td>是</td>",
            "<p>已完成：是</p>",
            "<p>上下文分離：是</p>",
            "<p>可逆：是</p>",
        ):
            with self.subTest(fragment=fragment, state="true"):
                self.assertIn(fragment, true_document)
        for fragment in (
            "<td>否</td>",
            "<p>已完成：否</p>",
            "<p>上下文分離：否</p>",
            "<p>可逆：否</p>",
        ):
            with self.subTest(fragment=fragment, state="false"):
                self.assertIn(fragment, false_document)

    def test_missing_context_separation_is_reported_as_unrecorded(self) -> None:
        state = copy.deepcopy(self.state)
        state["verification"][0].pop("context_separated", None)

        document = render_html(state, self.report)

        self.assertIn("<p>上下文分離：未記錄</p>", document)

    def test_renderer_owned_missing_value_fallbacks_are_traditional_chinese(self) -> None:
        state = copy.deepcopy(self.state)
        state["claims"] = [{}]
        state["evidence"] = [{}]
        state["sources"] = [{}]
        state["source_origins"] = []
        state["verification"] = [{}]
        state["engineering_handoff"]["safe_actions"] = [{}]
        state["contract"].pop("tier", None)
        state["contract"].pop("posture", None)

        document = render_html(state, self.report)

        for fallback in (
            "未記錄狀態",
            "未記錄來源層級",
            "未記錄推論關係",
            "未記錄起源類型",
            "未記錄驗證類型",
            "未記錄成本層級",
            "未記錄研究模式",
            "<td>未記錄</td>",
            "<p>已完成：未記錄</p>",
            "<p>可逆：未記錄</p>",
        ):
            with self.subTest(fallback=fallback):
                self.assertIn(fallback, document)
        for english_fallback in (
            "tier unknown",
            "entailment unknown",
            ">unknown<",
            ">check<",
        ):
            with self.subTest(english_fallback=english_fallback):
                self.assertNotIn(english_fallback, document)

    def test_invalid_session_is_rendered_with_explicit_invalid_label(self) -> None:
        state = load_state(self.session)
        path = self.session / state["artifact_index"][0]["relative_path"]
        path.write_bytes(b"tampered")
        result = render_session_result(self.session)
        self.assertFalse(result.validation.ok)
        self.assertIn("INVALID", result.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
