from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_harness.artifacts import (
    ArtifactExists,
    ArtifactPolicyError,
    SecretDetected,
    ingest_fetched_source,
    ingest_local_artifact,
    ingest_provider_artifact,
    purge_raw_artifact,
    recover_pending_purges,
)
from research_harness.contracts import contract_card_sha256
from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
)
from research_harness.quota import acquire_permits
from research_harness.state import new_state
from research_harness.storage import apply_state_patch, create_session, load_state
from tests.helpers import NOW, confirmed_medium_contract


LATER = "2026-07-10T12:01:00Z"


class ArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source.json"
        self.source.write_text('{"finding":"bounded"}\n', encoding="utf-8")
        self.registry = load_provider_registry()
        self.session = self._make_session("session")
        acquire_permits(
            self.session,
            "L1",
            "local_applicability",
            "local",
            "local",
            1,
            "sha256:local-output",
            NOW,
        )

    def _make_session(
        self,
        name: str,
        registry: dict | None = None,
        raw_storage_bytes: int | None = None,
        allow_provider_payloads: bool | None = None,
    ) -> Path:
        resolved = copy.deepcopy(self.registry if registry is None else registry)
        contract = confirmed_medium_contract(resolved)
        if raw_storage_bytes is not None:
            contract["resource_envelope"]["external"]["raw_storage_bytes"] = raw_storage_bytes
        if allow_provider_payloads is not None:
            contract["artifact_policy"]["allow_provider_payloads"] = allow_provider_payloads
        if raw_storage_bytes is not None or allow_provider_payloads is not None:
            records = referenced_provider_records(contract, resolved)
            contract["confirmation"] = {
                "confirmed_by": "user",
                "confirmed_at": NOW,
                "card_sha256": contract_card_sha256(contract),
                "registry_sha256": provider_registry_sha256(resolved),
                "referenced_records_sha256": provider_records_sha256(records),
            }
        session = self.root / name
        create_session(session, new_state("artifact test", contract, NOW, resolved, {}))
        return session

    def _ingest_local(self, artifact_id: str = "A1") -> dict:
        return ingest_local_artifact(
            self.session,
            self.source,
            artifact_id,
            "application/json",
            "public",
            "session",
            True,
            {"origin_kind": "local_output", "action_id": "L1"},
            NOW,
        )

    def _make_pass_using(
        self,
        artifact_id: str,
        *,
        safe_action: bool,
        safe_action_depends_on: tuple[str, ...] = (),
    ) -> None:
        state = load_state(self.session)
        operations = [
            {
                "op": "add",
                "path": "/evidence/-",
                "value": {"id": "E1", "artifact_id": artifact_id},
            },
            {
                "op": "add",
                "path": "/claims/-",
                "value": {
                    "id": "C1",
                    "status": "corroborated",
                    "supporting_evidence_ids": ["E1"],
                    "counter_evidence_ids": [],
                },
            },
            {"op": "replace", "path": "/summary/status", "value": "PASS"},
            {
                "op": "replace",
                "path": "/summary/load_bearing_claim_ids",
                "value": ["C1"],
            },
        ]
        if safe_action:
            operations.append(
                {
                    "op": "add",
                    "path": "/engineering_handoff/safe_actions/-",
                    "value": {
                        "id": "SA1",
                        "reversible": True,
                        "depends_on_claim_ids": list(safe_action_depends_on),
                    },
                }
            )
        apply_state_patch(self.session, operations, state["session"]["revision"], NOW)

    def _make_provider_session(self, name: str, payload_retention: str, html_allowed: bool) -> Path:
        registry = copy.deepcopy(self.registry)
        provider = next(item for item in registry["providers"] if item["id"] == "host-web")
        provider["storage_rights"].update(
            {
                "payload_retention": payload_retention,
                "html_allowed": html_allowed,
                "allowed_operational_fields": ["action_id"],
            }
        )
        session = self._make_session(name, registry, allow_provider_payloads=True)
        acquire_permits(
            session,
            "ATT1",
            "primary_scout",
            "host_retrieval",
            "host-web",
            1,
            "sha256:provider",
            NOW,
        )
        return session

    def test_ingest_confines_bytes_under_raw_and_records_integrity(self) -> None:
        artifact = self._ingest_local()
        path = self.session / artifact["relative_path"]
        self.assertEqual(path.parent, self.session / "raw")
        self.assertEqual(artifact["sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_state(self.session)["artifact_index"], [artifact])

    def test_secret_like_content_is_rejected_without_persisting(self) -> None:
        self.source.write_text("OPENAI_API_KEY=secret-value", encoding="utf-8")
        with self.assertRaises(SecretDetected):
            self._ingest_local()
        self.assertFalse((self.session / "raw" / "A1.json").exists())
        self.assertEqual(load_state(self.session)["artifact_index"], [])

    def test_env_named_source_is_rejected_without_reading_it_as_an_artifact(self) -> None:
        env_source = self.root / ".env"
        env_source.write_text("ordinary-looking-content", encoding="utf-8")
        with self.assertRaises(SecretDetected):
            ingest_local_artifact(
                self.session,
                env_source,
                "A1",
                "text/plain",
                "public",
                "session",
                False,
                {"origin_kind": "local_output", "action_id": "L1"},
                NOW,
            )

    def test_local_sensitive_requires_redaction_review_and_never_enters_html(self) -> None:
        provenance = {"origin_kind": "user_file", "supplied_by": "user"}
        with self.assertRaises(ArtifactPolicyError):
            ingest_local_artifact(
                self.session,
                self.source,
                "A1",
                "application/json",
                "local-sensitive",
                "session",
                False,
                provenance,
                NOW,
            )
        artifact = ingest_local_artifact(
            self.session,
            self.source,
            "A1",
            "application/json",
            "local-sensitive",
            "session",
            True,
            provenance,
            NOW,
            {"reviewed_by": "user", "reviewed_at": NOW, "method": "manual"},
        )
        self.assertFalse(artifact["include_in_html"])
        self.assertEqual(artifact["redaction_review"]["method"], "manual")

    def test_secret_sensitivity_is_never_persistable(self) -> None:
        with self.assertRaises(SecretDetected):
            ingest_local_artifact(
                self.session,
                self.source,
                "A1",
                "application/json",
                "secret",
                "session",
                False,
                {"origin_kind": "user_file", "supplied_by": "user"},
                NOW,
            )

    def test_artifact_id_traversal_symlink_and_overwrite_are_rejected(self) -> None:
        with self.assertRaises(ArtifactPolicyError):
            ingest_local_artifact(
                self.session,
                self.source,
                "../escape",
                "application/json",
                "public",
                "session",
                True,
                {"origin_kind": "local_output", "action_id": "L1"},
                NOW,
            )
        symlink = self.root / "link.json"
        symlink.symlink_to(self.source)
        with self.assertRaises(ArtifactPolicyError):
            ingest_local_artifact(
                self.session,
                symlink,
                "A2",
                "application/json",
                "public",
                "session",
                True,
                {"origin_kind": "local_output", "action_id": "L1"},
                NOW,
            )
        self._ingest_local()
        with self.assertRaises(ArtifactExists):
            self._ingest_local()

    def test_raw_storage_ceiling_is_enforced_before_persistence(self) -> None:
        session = self._make_session("tiny", raw_storage_bytes=4)
        acquire_permits(
            session, "L1", "local_applicability", "local", "local", 1, "sha256:x", NOW
        )
        with self.assertRaises(ArtifactPolicyError):
            ingest_local_artifact(
                session,
                self.source,
                "A1",
                "application/json",
                "public",
                "session",
                False,
                {"origin_kind": "local_output", "action_id": "L1"},
                NOW,
            )
        self.assertFalse((session / "raw" / "A1.json").exists())

    def test_local_output_requires_a_matching_local_action(self) -> None:
        session = self._make_session("no-local-action")
        with self.assertRaises(ArtifactPolicyError):
            ingest_local_artifact(
                session,
                self.source,
                "A1",
                "application/json",
                "public",
                "session",
                False,
                {"origin_kind": "local_output", "action_id": "L1"},
                NOW,
            )

    def test_managed_provider_spool_cannot_be_relabelled_as_local(self) -> None:
        spool = self.session / "provider_spool"
        spool.mkdir(mode=0o700)
        managed = spool / "ATT1.payload"
        managed.write_bytes(self.source.read_bytes())
        with self.assertRaises(ArtifactPolicyError):
            ingest_local_artifact(
                self.session,
                managed,
                "A1",
                "application/json",
                "public",
                "session",
                False,
                {"origin_kind": "user_file", "supplied_by": "user"},
                NOW,
            )

    def test_fetched_source_requires_matching_source_and_occurrence(self) -> None:
        with self.assertRaises(ArtifactPolicyError):
            ingest_fetched_source(
                self.session,
                self.source,
                "A1",
                "application/json",
                "S1",
                "R1",
                "public",
                "session",
                False,
                NOW,
            )
        state = load_state(self.session)
        apply_state_patch(
            self.session,
            [
                {"op": "add", "path": "/sources/-", "value": {"id": "S1"}},
                {
                    "op": "add",
                    "path": "/retrieval_occurrences/-",
                    "value": {"id": "R1", "provider_id": "host-web", "source_id": "S1"},
                },
            ],
            state["session"]["revision"],
            NOW,
        )
        artifact = ingest_fetched_source(
            self.session,
            self.source,
            "A1",
            "application/json",
            "S1",
            "R1",
            "public",
            "session",
            False,
            NOW,
        )
        self.assertEqual(artifact["provenance"]["origin_kind"], "fetched_source")

    def test_provider_payload_requires_snapshotted_provider_and_attempt(self) -> None:
        with self.assertRaises(ArtifactPolicyError):
            ingest_provider_artifact(
                self.session,
                self.source,
                "A1",
                "application/json",
                "brave",
                "ATT-unknown",
                "public",
                "session",
                False,
                NOW,
            )

    def test_provider_storage_rights_fail_closed_before_persistence(self) -> None:
        session = self._make_provider_session("ephemeral", "ephemeral", False)
        with self.assertRaises(ArtifactPolicyError):
            ingest_provider_artifact(
                session,
                self.source,
                "A1",
                "application/json",
                "host-web",
                "ATT1",
                "public",
                "session",
                False,
                NOW,
            )
        self.assertFalse((session / "raw" / "A1.json").exists())

    def test_provider_payload_cannot_exceed_html_or_retention_rights(self) -> None:
        session = self._make_provider_session("restricted", "session", False)
        for retention, include_in_html in (("persistent", False), ("session", True)):
            with self.subTest(retention=retention, include_in_html=include_in_html):
                with self.assertRaises(ArtifactPolicyError):
                    ingest_provider_artifact(
                        session,
                        self.source,
                        "A1",
                        "application/json",
                        "host-web",
                        "ATT1",
                        "public",
                        retention,
                        include_in_html,
                        NOW,
                    )

    def test_provider_payload_with_bound_rights_and_attempt_is_ingested(self) -> None:
        session = self._make_provider_session("persistent", "persistent", True)
        artifact = ingest_provider_artifact(
            session,
            self.source,
            "A1",
            "application/json",
            "host-web",
            "ATT1",
            "public",
            "persistent",
            True,
            NOW,
        )
        self.assertEqual(artifact["provenance"]["provider_id"], "host-web")
        self.assertEqual(artifact["provenance"]["attempt_or_occurrence_id"], "ATT1")

    def test_purge_blocks_by_default_before_removing_load_bearing_bytes(self) -> None:
        self._ingest_local()
        self._make_pass_using("A1", safe_action=False)
        tombstone = purge_raw_artifact(
            self.session, "A1", "retention expired", "BLOCKED", (), NOW
        )
        state = load_state(self.session)
        self.assertEqual(state["summary"]["status"], "BLOCKED")
        self.assertEqual(state["claims"][0]["status"], "unverified")
        self.assertEqual(tombstone["availability"], "purged")
        self.assertFalse((self.session / tombstone["former_relative_path"]).exists())
        self.assertTrue(tombstone["requires_revalidation"])

    def test_purge_allows_partial_only_with_independent_safe_reversible_action(self) -> None:
        self._ingest_local()
        self._make_pass_using("A1", safe_action=True)
        tombstone = purge_raw_artifact(
            self.session, "A1", "retention expired", "PARTIAL", ("SA1",), NOW
        )
        self.assertEqual(load_state(self.session)["summary"]["status"], "PARTIAL")
        self.assertEqual(tombstone["availability"], "purged")

    def test_purge_rejects_partial_when_safe_action_depends_on_affected_claim(self) -> None:
        self._ingest_local()
        self._make_pass_using("A1", safe_action=True, safe_action_depends_on=("C1",))
        with self.assertRaises(ArtifactPolicyError):
            purge_raw_artifact(
                self.session, "A1", "retention expired", "PARTIAL", ("SA1",), NOW
            )
        self.assertTrue((self.session / "raw" / "A1.json").exists())

    def test_purge_resumes_after_unlink_before_tombstone(self) -> None:
        self._ingest_local()
        self._make_pass_using("A1", safe_action=False)
        with mock.patch(
            "research_harness.artifacts._finalize_purge_tombstone", side_effect=OSError("crash")
        ):
            with self.assertRaises(OSError):
                purge_raw_artifact(
                    self.session, "A1", "retention expired", "BLOCKED", (), NOW
                )
        self.assertEqual(
            load_state(self.session)["artifact_index"][0]["availability"], "purge_pending"
        )
        self.assertFalse((self.session / "raw" / "A1.json").exists())
        tombstone = recover_pending_purges(self.session, LATER)[0]
        self.assertEqual(tombstone["availability"], "purged")
        self.assertEqual(tombstone["purged_at"], LATER)


if __name__ == "__main__":
    unittest.main()
