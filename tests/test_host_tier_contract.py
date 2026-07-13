from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from research_harness._canon import sha256_hex
from research_harness.artifacts import ArtifactPolicyError, ingest_host_capture
from research_harness.contracts import contract_card_sha256
from research_harness.rendering import finalize_session_result, render_session_result
from research_harness.state import new_state
from research_harness.storage import apply_state_patch, create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_contract


class HostTierContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.session = self._make_session("medium", axes=True)

    def _capture(
        self,
        artifact_id: str,
        source_url: str,
        payload: bytes,
        *,
        source_title: str = "Captured source",
        upstream_key: str = "upstream-1",
        purpose: str = "resolve the named gap",
        fidelity: str = "raw_http",
    ) -> dict:
        return ingest_host_capture(
            self.session,
            artifact_id,
            source_url,
            source_title,
            upstream_key,
            payload,
            fidelity,
            NOW,
            purpose,
        )

    def _verifier_record(
        self, claims: list[dict], *, record_id: str = "V-HIGH"
    ) -> dict:
        return {
            "id": record_id,
            "kind": "verifier",
            "completed": True,
            "context_separated": True,
            "produced_candidate": False,
            "verifier_actor": "host-verifier",
            "candidate_actor": "candidate-organizer",
            "packet_claim_ids": [claim["id"] for claim in claims],
            "packet_sha256": sha256_hex(claims),
            "verdict": "accept",
            "disposition": "accepted the bounded claim packet",
        }

    def _link_claim(self, evidence: list[dict], *, include_verifier: bool = True) -> None:
        state = load_state(self.session)
        operations: list[dict] = []
        for item in evidence:
            index = item["id"][1:]
            operations.extend(
                [
                    {
                        "op": "add",
                        "path": "/source_origins/-",
                        "value": {"id": f"O{index}", "kind": "host"},
                    },
                    {
                        "op": "add",
                        "path": "/sources/-",
                        "value": {
                            "id": f"S{index}",
                            "origin_id": f"O{index}",
                            "url": item["source_url"],
                            "title": item.get("source_title", "Captured source"),
                            "canonical_source_key": item["canonical_source_key"],
                            "upstream_key": item.get("upstream_key", "upstream-1"),
                            "direct_fetch": True,
                        },
                    },
                ]
            )
            operations.append(
                {
                    "op": "add",
                    "path": "/evidence/-",
                    "value": {
                        "id": item["id"],
                        "artifact_id": item["artifact_id"],
                        "source_id": f"S{index}",
                        "origin_id": f"O{index}",
                        "excerpt_start": 0,
                        "excerpt_end": len(item["payload"]),
                        "excerpt": item["payload"].decode("utf-8"),
                    },
                }
            )
        claim_record = {
            "id": "C1",
            "text": "Captured finding applies to this bounded decision.",
            "would_change_if": "the captured source changes",
            "load_bearing": True,
            "supporting_evidence_ids": [item["id"] for item in evidence],
        }
        operations.extend(
            [
                {
                    "op": "add",
                    "path": "/claims/-",
                    "value": claim_record,
                },
                {
                    "op": "replace",
                    "path": "/summary/load_bearing_claim_ids",
                    "value": ["C1"],
                },
                {"op": "replace", "path": "/summary/status", "value": "PARTIAL"},
                {"op": "replace", "path": "/summary/human_status", "value": "已完成研究判斷"},
                {"op": "replace", "path": "/summary/human_recommendation", "value": "建議採用"},
                {"op": "replace", "path": "/summary/decision", "value": "採用此有界結論"},
                {
                    "op": "replace",
                    "path": "/engineering_handoff/constraints",
                    "value": ["若來源改變則重新評估"],
                },
                {
                    "op": "replace",
                    "path": "/engineering_handoff/safe_actions",
                    "value": [{"id": "A1", "description": "保留可逆試行", "reversible": True, "depends_on_claim_ids": []}],
                },
                {
                    "op": "replace",
                    "path": "/engineering_handoff/acceptance_tests",
                    "value": ["rerun validation => tier contract remains met"],
                },
            ]
        )
        if state["contract"]["tier"] == "high" and include_verifier:
            operations.append(
                {
                    "op": "add",
                    "path": "/verification/-",
                    "value": self._verifier_record([claim_record]),
                }
            )
        apply_state_patch(self.session, operations, state["session"]["revision"], NOW)

    def test_host_capture_preserves_bytes_lineage_and_creates_no_transactions(self) -> None:
        payload = b"raw host bytes\x00\xff"
        artifact = self._capture(
            "HC1",
            "https://example.test/source",
            payload,
            upstream_key="HTTPS://Example.COM:443/upstream#fragment",
            fidelity="host_rendered",
        )

        self.assertEqual(artifact["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual((self.session / artifact["relative_path"]).read_bytes(), payload)
        self.assertEqual(artifact["provenance"]["origin_kind"], "host_capture")
        self.assertEqual(artifact["host_capture"]["canonical_source_key"], "https://example.test/source")
        self.assertEqual(artifact["host_capture"]["source_url"], "https://example.test/source")
        self.assertEqual(artifact["host_capture"]["source_title"], "Captured source")
        self.assertEqual(artifact["host_capture"]["upstream_key"], "https://example.com/upstream")
        self.assertEqual(artifact["host_capture"]["fidelity"], "host_rendered")
        self.assertEqual(artifact["host_capture"]["captured_at"], NOW)
        self.assertEqual(artifact["host_capture"]["marginal_purpose"], "resolve the named gap")
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        self.assertEqual([event["event"] for event in events], ["session_created", "state_revision"])
        self.assertTrue(validate_session(self.session).integrity_ok)

    def test_host_native_package_without_captures_is_evidence_insufficient(self) -> None:
        report = validate_session(self.session)

        self.assertFalse(report.tier_contract_met, report.to_dict())
        self.assertIn("tier.capture_missing", {issue.code for issue in report.warnings})

    def test_legacy_contract_without_axes_retains_old_semantics(self) -> None:
        state = new_state(confirmed_contract("medium"), NOW, None, {})
        state["contract"].pop("execution")
        state["contract"].pop("durability")
        state["session"].pop("contract_semantics")
        state["contract"]["confirmation"]["card_sha256"] = contract_card_sha256(state["contract"])
        self.session = self.root / "legacy-session"
        create_session(self.session, state)

        report = validate_session(self.session)

        self.assertTrue(report.tier_contract_met, report.to_dict())
        self.assertTrue(report.ok, report.to_dict())
        self.assertNotIn("tier.capture_missing", {issue.code for issue in report.issues})

    def test_host_capture_rejects_external_managed_contract(self) -> None:
        self.session = self._make_session("medium", axes=False)
        with self.assertRaisesRegex(ArtifactPolicyError, "host-native"):
            self._capture("HC1", "https://example.test/source", b"direct finding")

    def test_organizer_cannot_patch_contract_semantics_marker(self) -> None:
        from research_harness.storage import ProtectedStatePath

        state = load_state(self.session)
        for operation in (
            {"op": "replace", "path": "/session/contract_semantics", "value": "legacy"},
            {"op": "remove", "path": "/session/contract_semantics"},
            {"op": "add", "path": "/session/contract_semantics", "value": "pure_trigger_v2"},
        ):
            with self.subTest(operation=operation), self.assertRaises(ProtectedStatePath):
                apply_state_patch(
                    self.session,
                    [operation],
                    state["session"]["revision"],
                    NOW,
                )

    def test_medium_requires_each_load_bearing_claim_to_link_a_direct_capture(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        report = validate_session(self.session)
        self.assertTrue(report.tier_contract_met, report.to_dict())
        self.assertNotIn("tier.medium_direct_capture_missing", {issue.code for issue in report.issues})

    def test_high_requires_distinct_source_key_and_hash_and_links_both_captures(self) -> None:
        self.session = self._make_session("high", axes=True)
        first = self._capture("HC1", "https://example.test/a", b"finding A", upstream_key="upstream-a")
        second = self._capture("HC2", "https://example.test/b", b"finding B", upstream_key="upstream-b")
        self._link_claim(
            [
                {"id": "E1", "artifact_id": first["id"], "source_url": "https://example.test/a", "canonical_source_key": "https://example.test/a", "upstream_key": "upstream-a", "payload": b"finding A"},
                {"id": "E2", "artifact_id": second["id"], "source_url": "https://example.test/b", "canonical_source_key": "https://example.test/b", "upstream_key": "upstream-b", "payload": b"finding B"},
            ]
        )
        report = validate_session(self.session)
        self.assertTrue(report.tier_contract_met, report.to_dict())
        self.assertTrue(report.integrity_ok, report.to_dict())

    def test_high_duplicate_hash_does_not_satisfy_two_capture_floor(self) -> None:
        self.session = self._make_session("high", axes=True)
        first = self._capture("HC1", "https://example.test/a", b"same finding")
        second = self._capture("HC2", "https://example.test/b", b"same finding")
        self._link_claim(
            [
                {"id": "E1", "artifact_id": first["id"], "source_url": "https://example.test/a", "canonical_source_key": "https://example.test/a", "payload": b"same finding"},
                {"id": "E2", "artifact_id": second["id"], "source_url": "https://example.test/b", "canonical_source_key": "https://example.test/b", "payload": b"same finding"},
            ]
        )
        report = validate_session(self.session)
        self.assertFalse(report.tier_contract_met, report.to_dict())
        self.assertIn("tier.high_capture_diversity", {issue.code for issue in report.warnings})

    def test_high_same_known_upstream_still_satisfies_two_source_floor(self) -> None:
        self.session = self._make_session("high", axes=True)
        first = self._capture("HC1", "https://example.test/a", b"finding A", upstream_key="same-upstream")
        second = self._capture("HC2", "https://example.test/b", b"finding B", upstream_key="same-upstream")
        self._link_claim(
            [
                {"id": "E1", "artifact_id": first["id"], "source_url": "https://example.test/a", "canonical_source_key": "https://example.test/a", "upstream_key": "same-upstream", "payload": b"finding A"},
                {"id": "E2", "artifact_id": second["id"], "source_url": "https://example.test/b", "canonical_source_key": "https://example.test/b", "upstream_key": "same-upstream", "payload": b"finding B"},
            ]
        )
        report = validate_session(self.session)
        self.assertTrue(report.tier_contract_met, report.to_dict())
        self.assertIn("上游關係：</strong>相同", render_session_result(self.session).path.read_text(encoding="utf-8"))

    def test_host_native_human_completeness_is_a_warning_gate(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/human_recommendation", "value": ""}],
            state["session"]["revision"],
            NOW,
        )
        report = validate_session(self.session)
        self.assertFalse(report.tier_contract_met, report.to_dict())
        self.assertFalse(report.errors, report.to_dict())

    def test_each_human_completeness_gap_is_warning_only_and_insufficient(self) -> None:
        missing_fields = (
            ("/summary/human_status", ""),
            ("/summary/human_status", "證據不足"),
            ("/summary/human_status", "EVIDENCE_INSUFFICIENT"),
            ("/summary/human_status", "交付不完整"),
            ("/summary/human_status", "DELIVERY_INCOMPLETE"),
            ("/summary/human_recommendation", ""),
            ("/summary/decision", ""),
            ("/claims/0/text", ""),
            ("/engineering_handoff/constraints", []),
            ("/engineering_handoff/safe_actions", []),
            ("/engineering_handoff/acceptance_tests", []),
            ("/engineering_handoff/acceptance_tests", ["x"]),
        )
        for index, (path, value) in enumerate(missing_fields):
            with self.subTest(path=path):
                self.session = self._make_session("medium", axes=True, label=str(index))
                artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
                self._link_claim(
                    [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
                )
                state = load_state(self.session)
                operations = [{"op": "replace", "path": path, "value": value}]
                if path == "/engineering_handoff/constraints":
                    operations.extend(
                        [
                            {"op": "replace", "path": "/open_questions", "value": []},
                            {"op": "replace", "path": "/claims/0/would_change_if", "value": ""},
                        ]
                    )
                if path == "/engineering_handoff/safe_actions":
                    operations.append(
                        {"op": "replace", "path": "/summary/status", "value": "BLOCKED"}
                    )
                apply_state_patch(self.session, operations, state["session"]["revision"], NOW)
                report = validate_session(self.session)
                self.assertFalse(report.tier_contract_met, report.to_dict())
                self.assertFalse(report.errors, report.to_dict())
                first_screen = render_session_result(self.session).path.read_text(encoding="utf-8").split('<details class="kernel-details">', 1)[0]
                self.assertEqual(report.human_status, "交付不完整")
                self.assertIn("BLOCKED / DELIVERY_INCOMPLETE", first_screen + render_session_result(self.session).path.read_text(encoding="utf-8"))
                self.assertIn("補齊交付要件後重新產生報告", first_screen)
                self.assertNotIn("尚缺足夠的直接來源，結論可能改變", first_screen)

    def test_complete_host_package_has_deliverable_human_surface(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        report = validate_session(self.session)
        self.assertTrue(report.ok, report.to_dict())
        first_screen = render_session_result(self.session).path.read_text(encoding="utf-8").split('<details class="kernel-details">', 1)[0]
        for value in ("已完成研究判斷", "建議採用", "採用此有界結論", "Captured source", "若來源改變則重新評估", "A1"):
            self.assertIn(value, first_screen)
        self.assertEqual(first_screen.count('<article class="safe-action">'), 1)

    def test_blank_whitespace_and_non_string_limitations_do_not_pass(self) -> None:
        cases = (
            ("/engineering_handoff/constraints", ["", "  ", 1]),
            ("/open_questions", [{"id": "Q1"}]),
            ("/claims/0/would_change_if", " "),
        )
        for index, (path, value) in enumerate(cases):
            with self.subTest(path=path):
                self.session = self._make_session("medium", axes=True, label=f"blank-{index}")
                artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
                self._link_claim(
                    [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
                )
                state = load_state(self.session)
                operations = [{"op": "replace", "path": path, "value": value}]
                for other_path in (
                    "/engineering_handoff/constraints",
                    "/open_questions",
                    "/claims/0/would_change_if",
                ):
                    if other_path != path:
                        operations.append({"op": "replace", "path": other_path, "value": [] if other_path != "/claims/0/would_change_if" else ""})
                apply_state_patch(self.session, operations, state["session"]["revision"], NOW)
                report = validate_session(self.session)
                self.assertFalse(report.tier_contract_met, report.to_dict())
                self.assertFalse(report.errors, report.to_dict())

    def test_host_evidence_rejects_source_key_mismatch(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://other.test/source", "canonical_source_key": "https://other.test/source", "payload": b"direct finding"}]
        )

        report = validate_session(self.session)

        self.assertIn("evidence.host_capture_source_key_mismatch", {issue.code for issue in report.errors})
        self.assertFalse(report.tier_contract_met)

    def test_high_missing_second_capture_renders_evidence_insufficient(self) -> None:
        self.session = self._make_session("high", axes=True)
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/human_recommendation", "value": "建議採用"}],
            state["session"]["revision"],
            NOW,
        )
        document = render_session_result(self.session).path.read_text(encoding="utf-8")
        self.assertIn("證據不足", document)
        self.assertIn("證據不足，暫不作肯定建議", document)
        self.assertNotIn("<h2>建議採用</h2>", document)
        payload = validate_session(self.session).to_dict()
        self.assertFalse(payload["tier_contract_met"])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["integrity_ok"])
        self.assertEqual(payload["human_status"], "證據不足")

    def test_in_progress_is_delivery_incomplete_and_finalizer_seals_matching_status(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/status", "value": "IN_PROGRESS"}],
            state["session"]["revision"],
            NOW,
        )

        report = validate_session(self.session)
        self.assertFalse(report.tier_contract_met, report.to_dict())
        self.assertEqual(report.human_status, "交付不完整")
        self.assertIn("tier.terminal_status_missing", {issue.code for issue in report.warnings})

        rendered = finalize_session_result(self.session, NOW)
        sealed = load_state(self.session)
        self.assertEqual(sealed["summary"]["status"], "BLOCKED")
        self.assertEqual(sealed["summary"]["human_status"], "交付不完整")
        self.assertFalse(rendered.validation.tier_contract_met)
        self.assertIn(
            "BLOCKED / DELIVERY_INCOMPLETE", rendered.path.read_text(encoding="utf-8")
        )

    def test_invalid_acceptance_grammar_is_delivery_incomplete(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        for value in ("x", " -> expected", "check -> ", " => expected", "check => "):
            with self.subTest(value=value):
                state = load_state(self.session)
                apply_state_patch(
                    self.session,
                    [
                        {
                            "op": "replace",
                            "path": "/engineering_handoff/acceptance_tests",
                            "value": [value],
                        }
                    ],
                    state["session"]["revision"],
                    NOW,
                )

                report = validate_session(self.session)
                self.assertFalse(report.tier_contract_met, report.to_dict())
                self.assertEqual(report.human_status, "交付不完整")
                self.assertIn(
                    "tier.acceptance_tests_missing",
                    {issue.code for issue in report.warnings},
                )

    def test_any_acceptance_test_with_nonempty_check_and_expected_is_sufficient(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        for value in (" check => expected ", "command -> 65 passed"):
            with self.subTest(value=value):
                state = load_state(self.session)
                apply_state_patch(
                    self.session,
                    [
                        {
                            "op": "replace",
                            "path": "/engineering_handoff/acceptance_tests",
                            "value": ["x", value],
                        }
                    ],
                    state["session"]["revision"],
                    NOW,
                )

                report = validate_session(self.session)
                self.assertTrue(report.tier_contract_met, report.to_dict())
                self.assertNotIn(
                    "tier.acceptance_tests_missing", {issue.code for issue in report.issues}
                )

    def test_high_verifier_minimum_is_required_without_host_accounting(self) -> None:
        self.session = self._make_session("high", axes=True, label="verifier")
        first = self._capture("HC1", "https://example.test/a", b"finding A")
        second = self._capture("HC2", "https://example.test/b", b"finding B")
        evidence = [
            {"id": "E1", "artifact_id": first["id"], "source_url": "https://example.test/a", "canonical_source_key": "https://example.test/a", "payload": b"finding A"},
            {"id": "E2", "artifact_id": second["id"], "source_url": "https://example.test/b", "canonical_source_key": "https://example.test/b", "payload": b"finding B"},
        ]
        self._link_claim(evidence, include_verifier=False)

        missing = validate_session(self.session)
        self.assertFalse(missing.tier_contract_met, missing.to_dict())
        self.assertEqual(missing.human_status, "交付不完整")
        self.assertIn("tier.high_verifier_missing", {issue.code for issue in missing.warnings})
        self.assertNotIn("host.accounting", {issue.code for issue in missing.issues})

        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [
                {
                    "op": "add",
                    "path": "/verification/-",
                    "value": self._verifier_record(state["claims"]),
                }
            ],
            state["session"]["revision"],
            NOW,
        )
        complete = validate_session(self.session)
        self.assertTrue(complete.tier_contract_met, complete.to_dict())

    def test_high_verifier_attestation_rejects_forged_or_mismatched_fields(self) -> None:
        cases = {
            "flags-only": {
                "id": "V-HIGH",
                "kind": "verifier",
                "completed": True,
                "context_separated": True,
                "produced_candidate": False,
            },
            "missing-actor": {"verifier_actor": ""},
            "same-actor": {
                "verifier_actor": "candidate-organizer",
                "candidate_actor": "candidate-organizer",
            },
            "claim-ids": {"packet_claim_ids": ["C2"]},
            "packet-hash": {"packet_sha256": "0" * 64},
            "verdict": {"verdict": "approve"},
            "disposition": {"disposition": ""},
        }
        for label, changes in cases.items():
            with self.subTest(label=label):
                self.session = self._make_session("high", axes=True, label=label)
                first = self._capture("HC1", "https://example.test/a", b"finding A")
                second = self._capture("HC2", "https://example.test/b", b"finding B")
                self._link_claim(
                    [
                        {"id": "E1", "artifact_id": first["id"], "source_url": "https://example.test/a", "canonical_source_key": "https://example.test/a", "payload": b"finding A"},
                        {"id": "E2", "artifact_id": second["id"], "source_url": "https://example.test/b", "canonical_source_key": "https://example.test/b", "payload": b"finding B"},
                    ],
                    include_verifier=False,
                )
                state = load_state(self.session)
                record = self._verifier_record(state["claims"])
                if label == "flags-only":
                    record = changes
                else:
                    record.update(changes)
                apply_state_patch(
                    self.session,
                    [{"op": "add", "path": "/verification/-", "value": record}],
                    state["session"]["revision"],
                    NOW,
                )

                report = validate_session(self.session)
                self.assertFalse(report.tier_contract_met, report.to_dict())
                self.assertIn(
                    "tier.high_verifier_invalid", {issue.code for issue in report.warnings}
                )

    def test_high_verifier_packet_hash_changes_with_claim_record(self) -> None:
        self.session = self._make_session("high", axes=True, label="packet-mutation")
        first = self._capture("HC1", "https://example.test/a", b"finding A")
        second = self._capture("HC2", "https://example.test/b", b"finding B")
        self._link_claim(
            [
                {"id": "E1", "artifact_id": first["id"], "source_url": "https://example.test/a", "canonical_source_key": "https://example.test/a", "payload": b"finding A"},
                {"id": "E2", "artifact_id": second["id"], "source_url": "https://example.test/b", "canonical_source_key": "https://example.test/b", "payload": b"finding B"},
            ]
        )
        self.assertTrue(validate_session(self.session).tier_contract_met)
        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/claims/0/text", "value": "mutated claim"}],
            state["session"]["revision"],
            NOW,
        )

        report = validate_session(self.session)
        self.assertFalse(report.tier_contract_met, report.to_dict())
        self.assertIn("tier.high_verifier_invalid", {issue.code for issue in report.warnings})

    def test_high_pass_does_not_exempt_verifier_existence(self) -> None:
        self.session = self._make_session("high", axes=True, label="pass-verifier")
        first = self._capture("HC1", "https://example.test/a", b"finding A")
        second = self._capture("HC2", "https://example.test/b", b"finding B")
        self._link_claim(
            [
                {"id": "E1", "artifact_id": first["id"], "source_url": "https://example.test/a", "canonical_source_key": "https://example.test/a", "payload": b"finding A"},
                {"id": "E2", "artifact_id": second["id"], "source_url": "https://example.test/b", "canonical_source_key": "https://example.test/b", "payload": b"finding B"},
            ],
            include_verifier=False,
        )
        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/status", "value": "PASS"}],
            state["session"]["revision"],
            NOW,
        )

        report = validate_session(self.session)
        self.assertIn("tier.high_verifier_missing", {issue.code for issue in report.errors})
        self.assertEqual(
            sum(issue.code == "tier.high_verifier_missing" for issue in report.issues), 1
        )
        self.assertNotIn("host.accounting", {issue.code for issue in report.issues})

    def test_finalizer_seals_semantically_invalid_pass_even_when_tier_floor_is_met(self) -> None:
        artifact = self._capture("HC1", "https://example.test/source", b"direct finding")
        self._link_claim(
            [{"id": "E1", "artifact_id": artifact["id"], "source_url": "https://example.test/source", "canonical_source_key": "https://example.test/source", "payload": b"direct finding"}]
        )
        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/status", "value": "PASS"}],
            state["session"]["revision"],
            NOW,
        )

        before = validate_session(self.session)
        self.assertTrue(before.integrity_ok, before.to_dict())
        self.assertTrue(before.tier_contract_met, before.to_dict())
        self.assertFalse(before.ok, before.to_dict())
        self.assertTrue(before.errors, before.to_dict())

        rendered = finalize_session_result(self.session, NOW)
        sealed = load_state(self.session)
        self.assertEqual(sealed["summary"]["status"], "BLOCKED")
        self.assertEqual(sealed["summary"]["human_status"], "交付不完整")
        self.assertFalse(rendered.validation.tier_contract_met)
        self.assertIn(
            "BLOCKED / DELIVERY_INCOMPLETE", rendered.path.read_text(encoding="utf-8")
        )

    def test_host_capture_lineage_cannot_be_added_by_generic_organizer_patch(self) -> None:
        from research_harness.storage import ProtectedStatePath

        state = load_state(self.session)
        with self.assertRaises(ProtectedStatePath):
            apply_state_patch(
                self.session,
                [{"op": "add", "path": "/artifact_index/-", "value": {"id": "forged"}}],
                state["session"]["revision"],
                NOW,
            )

    def _make_session(self, tier: str, *, axes: bool = False, label: str = "") -> Path:
        session = self.root / f"{tier}-session-{axes}-{label or 'default'}"
        contract = confirmed_contract(tier)
        if axes:
            contract["execution"] = "host_native"
            contract["durability"] = "canonical_package"
            from research_harness.contracts import contract_card_sha256

            contract["confirmation"]["card_sha256"] = contract_card_sha256(contract)
        create_session(session, new_state(contract, NOW, None, {}))
        return session


if __name__ == "__main__":
    unittest.main()
