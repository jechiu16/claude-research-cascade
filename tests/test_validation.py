from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_harness.artifacts import ingest_fetched_source
from research_harness.storage import apply_state_patch, load_state
from research_harness.validation import _validate_evidence, validate_session
from tests.helpers import (
    NOW,
    append_valid_test_event_line,
    make_complete_pass_session,
    make_incomplete_session,
    make_partial_session,
    make_session_with_demo_evidence,
)


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def test_pass_rejects_missing_load_bearing_raw_artifact(self) -> None:
        session = make_incomplete_session(self.root, "medium", "lookup", "PASS")
        report = validate_session(session)
        self.assertIn("claim.raw_missing", {issue.code for issue in report.errors})

    def test_pass_cannot_succeed_vacuously_with_empty_answer_or_claim_set(self) -> None:
        session = make_incomplete_session(self.root, "medium", "lookup", "PASS")
        state = load_state(session)
        apply_state_patch(
            session,
            [
                {"op": "replace", "path": "/summary/decision", "value": ""},
                {"op": "replace", "path": "/summary/load_bearing_claim_ids", "value": []},
                {"op": "replace", "path": "/claims/0/load_bearing", "value": False},
            ],
            state["session"]["revision"],
            NOW,
        )
        report = validate_session(session)
        codes = {issue.code for issue in report.errors}
        self.assertIn("status.pass_answer_missing", codes)
        self.assertIn("status.pass_claim_set_empty", codes)

    def test_quota_overrun_in_manual_event_fails_validation(self) -> None:
        session = make_complete_pass_session(self.root)
        append_valid_test_event_line(
            session,
            {
                "event": "permit_acquired",
                "at": NOW,
                "action_id": "OVER",
                "stage": "primary_scout",
                "category": "host_retrieval",
                "route": "host-web",
                "invocation_index": 2,
                "count": 99,
                "fingerprint": "sha256:hostile",
            },
        )
        report = validate_session(session)
        self.assertIn("quota.exceeded", {issue.code for issue in report.errors})

    def test_no_network_demo_route_can_never_contribute_evidence(self) -> None:
        session = make_session_with_demo_evidence(self.root)
        report = validate_session(session)
        self.assertIn("evidence.demo_route_forbidden", {issue.code for issue in report.errors})

    def test_discovery_only_provider_payload_cannot_support_evidence(self) -> None:
        state = {
            "evidence": [
                {
                    "id": "E1",
                    "artifact_id": "A1",
                    "source_id": "S1",
                    "origin_id": "O1",
                    "excerpt_start": 0,
                    "excerpt_end": 7,
                    "excerpt": "finding",
                }
            ],
            "sources": [{"id": "S1", "origin_id": "O1"}],
            "source_origins": [{"id": "O1"}],
            "retrieval_occurrences": [],
            "capabilities": {
                "providers": [
                    {
                        "id": "openalex",
                        "evidence_capabilities": {"can_support_claims": False},
                    }
                ]
            },
        }
        artifacts = {
            "A1": {
                "availability": "available",
                "provenance": {
                    "origin_kind": "provider_payload",
                    "provider_id": "openalex",
                },
            }
        }
        issues = []

        _validate_evidence(state, artifacts, {"A1": b"finding"}, issues)

        self.assertIn("evidence.provider_claims_forbidden", {issue.code for issue in issues})

    def test_high_pass_requires_context_separated_verifier(self) -> None:
        session = make_incomplete_session(self.root, "high", "decision", "PASS")
        report = validate_session(session)
        self.assertIn("tier.high_verifier_missing", {issue.code for issue in report.errors})

    def test_complete_medium_lookup_passes_every_gate(self) -> None:
        session = make_complete_pass_session(self.root, "medium", "lookup")
        report = validate_session(session)
        self.assertTrue(report.ok, report.to_dict())

    def test_complete_high_decision_with_separated_verifier_passes(self) -> None:
        session = make_complete_pass_session(self.root, "high", "decision")
        report = validate_session(session)
        self.assertTrue(report.ok, report.to_dict())

    def test_high_verifier_record_must_bind_reserved_verifier_action(self) -> None:
        session = make_complete_pass_session(self.root, "high", "decision")
        state = load_state(session)
        verifier_index = next(
            index
            for index, item in enumerate(state["verification"])
            if item.get("kind") == "verifier"
        )
        apply_state_patch(
            session,
            [
                {
                    "op": "replace",
                    "path": f"/verification/{verifier_index}/action_id",
                    "value": "FORGED",
                }
            ],
            state["session"]["revision"],
            NOW,
        )
        report = validate_session(session)
        self.assertIn("tier.high_verifier_unbound", {issue.code for issue in report.errors})

    def test_empirical_load_bearing_claim_needs_two_independent_origins(self) -> None:
        session = make_complete_pass_session(self.root, "high", "decision")
        state = load_state(session)
        apply_state_patch(
            session,
            [{"op": "replace", "path": "/claims/0/claim_type", "value": "empirical"}],
            state["session"]["revision"],
            NOW,
        )
        report = validate_session(session)
        self.assertIn("claim.origin_independence", {issue.code for issue in report.errors})

    def test_empirical_claim_with_two_independent_raw_origins_passes(self) -> None:
        session = make_complete_pass_session(self.root, "high", "decision")
        state = load_state(session)
        apply_state_patch(
            session,
            [
                {
                    "op": "add",
                    "path": "/source_origins/-",
                    "value": {"id": "O2", "kind": "independent-study", "independent": True},
                },
                {
                    "op": "add",
                    "path": "/sources/-",
                    "value": {
                        "id": "S2",
                        "origin_id": "O2",
                        "tier": "T1",
                        "title": "Independent fixture",
                        "direct_fetch": True,
                    },
                },
                {
                    "op": "add",
                    "path": "/retrieval_occurrences/-",
                    "value": {
                        "id": "R2",
                        "provider_id": "host-web",
                        "source_id": "S2",
                        "action_id": "A2",
                    },
                },
            ],
            state["session"]["revision"],
            NOW,
        )
        payload = b"Independent empirical finding.\n"
        source = self.root / "independent.txt"
        source.write_bytes(payload)
        ingest_fetched_source(
            session,
            source,
            "A2",
            "text/plain",
            "S2",
            "R2",
            "public",
            "session",
            False,
            NOW,
        )
        state = load_state(session)
        apply_state_patch(
            session,
            [
                {
                    "op": "add",
                    "path": "/evidence/-",
                    "value": {
                        "id": "E2",
                        "artifact_id": "A2",
                        "source_id": "S2",
                        "origin_id": "O2",
                        "source_tier": "T1",
                        "excerpt": payload.decode("utf-8"),
                        "excerpt_start": 0,
                        "excerpt_end": len(payload),
                        "entailment": "entailed",
                        "applicability": "checked",
                        "retrieved_at": NOW,
                    },
                },
                {"op": "replace", "path": "/claims/0/claim_type", "value": "empirical"},
                {
                    "op": "replace",
                    "path": "/claims/0/supporting_evidence_ids",
                    "value": ["E1", "E2"],
                },
                {
                    "op": "replace",
                    "path": "/claims/0/source_origin_ids",
                    "value": ["O1", "O2"],
                },
            ],
            state["session"]["revision"],
            NOW,
        )
        report = validate_session(session)
        self.assertTrue(report.ok, report.to_dict())

    def test_existing_html_with_old_state_hash_fails_validation(self) -> None:
        session = make_complete_pass_session(self.root, "medium", "lookup")
        (session / "report.html").write_text(
            '<meta data-state-sha256="stale">', encoding="utf-8"
        )
        report = validate_session(session)
        self.assertIn("report.stale", {issue.code for issue in report.errors})

    def test_partial_requires_safe_reversible_action_independent_of_gap(self) -> None:
        session = make_partial_session(self.root, safe_action=False)
        report = validate_session(session)
        self.assertIn("status.partial_safe_action_missing", {issue.code for issue in report.errors})

    def test_partial_with_independent_safe_reversible_action_passes(self) -> None:
        session = make_partial_session(self.root, safe_action=True)
        report = validate_session(session)
        self.assertTrue(report.ok, report.to_dict())

    def test_mutated_artifact_and_invented_excerpt_fail_integrity(self) -> None:
        session = make_complete_pass_session(self.root)
        state = load_state(session)
        path = session / state["artifact_index"][0]["relative_path"]
        payload = bytearray(path.read_bytes())
        payload[0] = ord("X")
        path.write_bytes(payload)
        report = validate_session(session)
        codes = {issue.code for issue in report.errors}
        self.assertIn("artifact.integrity", codes)
        self.assertIn("evidence.excerpt_mismatch", codes)

    def test_unindexed_raw_file_fails_validation(self) -> None:
        session = make_complete_pass_session(self.root)
        (session / "raw" / "unindexed.txt").write_text("orphan", encoding="utf-8")
        report = validate_session(session)
        self.assertIn("artifact.unindexed", {issue.code for issue in report.errors})


if __name__ == "__main__":
    unittest.main()
