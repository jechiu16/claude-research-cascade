from __future__ import annotations

import copy
import hashlib
import re
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
    promote_provider_payload,
    purge_raw_artifact,
    recover_pending_purges,
)
from research_harness.boundary import execute_probe
from research_harness.contracts import contract_card_sha256, normalize_contract
from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
)
from research_harness.quota import acquire_permits
from research_harness.state import new_state
from research_harness.storage import apply_state_patch, create_session, load_state
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, confirmed_medium_contract


LATER = "2026-07-10T12:01:00Z"
FIXTURES = Path(__file__).with_name("fixtures")


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


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

    def _make_session(self, name: str, raw_storage_bytes: int | None = None) -> Path:
        resolved = copy.deepcopy(self.registry)
        contract = confirmed_medium_contract(resolved)
        if raw_storage_bytes is not None:
            contract["resource_envelope"]["external"]["raw_storage_bytes"] = raw_storage_bytes
            records = referenced_provider_records(contract, resolved)
            contract["confirmation"] = {
                "confirmed_by": "user",
                "confirmed_at": NOW,
                "card_sha256": contract_card_sha256(contract),
                "registry_sha256": provider_registry_sha256(resolved),
                "referenced_records_sha256": provider_records_sha256(records),
            }
        session = self.root / name
        create_session(session, new_state(contract, NOW, resolved, {}))
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


class PromoteProviderPayloadTests(unittest.TestCase):
    """promote_provider_payload: boundary-spooled payloads -> artifact_index.

    A standalone TestCase (not a subclass of ArtifactTests -- subclassing a
    TestCase for setUp reuse would re-run every inherited test_* method under
    this class too) with its own minimal fixture: a tempdir and the loaded
    provider registry, plus a helper to build a confirmed probe-route
    session with artifact_policy.allow_provider_payloads overridden.
    """

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.registry = load_provider_registry()

    def _make_provider_session(
        self,
        name: str,
        route: str,
        *,
        allow_provider_payloads: bool,
    ) -> Path:
        """A confirmed probe-route session, with artifact_policy overridden
        after the fact (mirrors confirmed_demo_contract's own confirm step:
        mutate, then recompute the card/registry/records hashes so the
        contract stays internally consistent)."""

        resolved = copy.deepcopy(self.registry)
        contract = confirmed_demo_contract(
            route=route, request_count=1, probe_ceiling=1, registry=resolved
        )
        contract["artifact_policy"]["allow_provider_payloads"] = allow_provider_payloads
        records = referenced_provider_records(contract, resolved)
        contract["confirmation"] = {
            "confirmed_by": "user",
            "confirmed_at": NOW,
            "card_sha256": contract_card_sha256(contract),
            "registry_sha256": provider_registry_sha256(resolved),
            "referenced_records_sha256": provider_records_sha256(records),
        }
        session = self.root / name
        create_session(session, new_state(contract, NOW, resolved, {}))
        return session

    def _execute_and_promote(
        self,
        session: Path,
        route: str,
        action_id: str,
        artifact_id: str,
        *,
        transport=None,
        environ: dict[str, str] | None = None,
        query: str = "jechiu16/agent-deep-research-trigger",
    ) -> dict:
        acquire_permits(
            session, action_id, "primary_scout", "probe", route, 1, f"fp-{action_id.lower()}", NOW
        )
        execute_probe(session, action_id, query, NOW, transport=transport, environ=environ or {})
        return promote_provider_payload(session, action_id, artifact_id, "session", False, NOW)

    def test_promote_requires_contract_to_allow_provider_payloads(self) -> None:
        session = self._make_provider_session(
            "no-provider-payloads", "github", allow_provider_payloads=False
        )
        acquire_permits(session, "A1", "primary_scout", "probe", "github", 1, "fp-a1", NOW)
        execute_probe(
            session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
            transport=fixture_transport("github_success.json"), environ={},
        )
        with self.assertRaises(ArtifactPolicyError):
            promote_provider_payload(session, "A1", "PA1", "session", False, NOW)
        self.assertEqual(load_state(session)["artifact_index"], [])

    def test_promote_requires_a_recorded_occurrence_for_the_action(self) -> None:
        session = self._make_provider_session(
            "no-occurrence", "github", allow_provider_payloads=True
        )
        with self.assertRaises(ArtifactPolicyError):
            promote_provider_payload(session, "GHOST", "PA1", "session", False, NOW)
        self.assertEqual(load_state(session)["artifact_index"], [])

    def test_promote_rejects_path_traversal_action_id_from_injected_occurrence(self) -> None:
        # Security regression. An occurrence's action_id can be written
        # directly by a state patch (organizer tooling), which never goes
        # through acquire_permits -- so a crafted action_id like
        # "../../pwned" used to walk provider_spool/<action_id>.raw.json
        # straight out of the session directory and ingest whatever regular
        # file it found there as a "public" provider-payload evidence
        # artifact. Reproduces that exact path.
        session = self._make_provider_session(
            "traversal-occurrence", "github", allow_provider_payloads=True
        )
        # A real provider_spool/ must already exist on disk for the OS to
        # walk ".." back out of it -- true of any session that has run one
        # legitimate action, so exercise one honestly first.
        acquire_permits(session, "A1", "primary_scout", "probe", "github", 1, "fp-a1", NOW)
        execute_probe(
            session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
            transport=fixture_transport("github_success.json"), environ={},
        )

        # session/provider_spool/../../pwned.raw.json resolves to
        # session.parent / "pwned.raw.json" -- outside the session entirely.
        bait_path = self.root / "pwned.raw.json"
        bait_bytes = b'{"exfiltrated": "outside the session directory"}\n'
        bait_path.write_bytes(bait_bytes)

        malicious_action_id = "../../pwned"
        state = load_state(session)
        apply_state_patch(
            session,
            [
                {
                    "op": "add",
                    "path": "/retrieval_occurrences/-",
                    "value": {
                        "id": "occ-evil",
                        "provider_id": "github",
                        "action_id": malicious_action_id,
                    },
                }
            ],
            state["session"]["revision"],
            NOW,
        )

        with self.assertRaises(ArtifactPolicyError):
            promote_provider_payload(session, malicious_action_id, "PWNED1", "session", False, NOW)

        self.assertEqual(load_state(session)["artifact_index"], [])
        # Nothing was ever ingested: the format gate fires before
        # _ensure_raw_dir, so raw/ was never even created.
        self.assertFalse((session / "raw").exists())
        # The external file itself is untouched (proves it was never
        # opened/copied, not just that the artifact record was rolled back).
        self.assertEqual(bait_path.read_bytes(), bait_bytes)

    def test_promote_confine_rejects_traversal_even_if_format_gate_is_bypassed(self) -> None:
        # Defense in depth. Even if a future change (or bug) neutered the
        # ACTION_ID_RE format gate, the independent confinement check on the
        # resolved spool path must still refuse a path-traversal action_id
        # on its own -- proven here by patching the format gate itself into
        # a no-op and confirming the traversal is still blocked.
        session = self._make_provider_session(
            "traversal-confine-only", "github", allow_provider_payloads=True
        )
        acquire_permits(session, "A1", "primary_scout", "probe", "github", 1, "fp-a1", NOW)
        execute_probe(
            session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
            transport=fixture_transport("github_success.json"), environ={},
        )

        bait_path = self.root / "pwned2.raw.json"
        bait_bytes = b'{"exfiltrated": "confine-only bypass probe"}\n'
        bait_path.write_bytes(bait_bytes)

        malicious_action_id = "../../pwned2"
        state = load_state(session)
        apply_state_patch(
            session,
            [
                {
                    "op": "add",
                    "path": "/retrieval_occurrences/-",
                    "value": {
                        "id": "occ-evil2",
                        "provider_id": "github",
                        "action_id": malicious_action_id,
                    },
                }
            ],
            state["session"]["revision"],
            NOW,
        )

        permissive = re.compile(r".*")
        with mock.patch("research_harness.artifacts.ACTION_ID_RE", permissive):
            with self.assertRaises(ArtifactPolicyError):
                promote_provider_payload(session, malicious_action_id, "PWNED2", "session", False, NOW)

        self.assertEqual(load_state(session)["artifact_index"], [])
        self.assertEqual(bait_path.read_bytes(), bait_bytes)

    def test_promote_refuses_deep_category_providers(self) -> None:
        # perplexity's action_categories include "deep": its async result is
        # spooled under provider_spool/<poll_action_id>.raw.json by
        # execute_deep_poll, never under the submitted action_id recorded on
        # the retrieval occurrence -- that action_id's own spool file (if
        # any) is only the submit-accept stub. A synthetic occurrence is
        # enough to exercise the guard; no real submit/poll cycle is needed
        # since the rejection must happen before any spool file is read.
        #
        # confirmed_demo_contract/_make_provider_session always map
        # primary_scout to category "probe", which perplexity's
        # stage_capabilities (["investigation", "anti_lock_in"]) do not
        # support, so this needs its own minimal contract referencing
        # perplexity through a stage/category it actually supports (mirrors
        # tests/test_async_boundary.py's inline _deep_contract).
        resolved = copy.deepcopy(self.registry)
        contract = normalize_contract(
            {
                "question": "deep promote guard test",
                "posture": "lookup",
                "tier": "custom",
                "execution": "external_managed",
                "durability": "canonical_package",
                "scout_route": "demo-probe",
                "resource_envelope": {
                    "physical_ceiling": {
                        "probe": 1, "deep": 1, "processor": 0, "network_experiment": 0,
                        "transport": 0, "host_retrieval": 0, "local": 0, "organizer_pass": 0,
                    },
                    "external": {
                        "metered_ceiling": {
                            "probe": 0, "deep": 1, "processor": 0,
                            "network_experiment": 0, "transport": 0,
                        },
                        "max_wall_time_seconds": 1200,
                        "allowed_endpoint_classes": [],
                        "local_file_egress": False,
                        "network_experiment_endpoints": [],
                        "estimated_spend_usd": {"minimum": 0.0, "maximum": 1.0, "hard_cap": False},
                        "raw_storage_bytes": 10 * 1024 * 1024,
                    },
                    "host": {"context_class": "lean", "admitted_characters": 8000, "estimated_tokens": 2000},
                    "local": {"admitted_output_characters": 0, "max_wall_time_seconds": 60, "network_egress": False},
                },
                "stage_permit_map": [
                    {"stage": "primary_scout", "category": "probe", "route": "demo-probe",
                     "invocations": 1, "count": 1, "reserved": False},
                    {"stage": "investigation", "category": "deep", "route": "perplexity",
                     "invocations": 1, "count": 1, "reserved": False},
                ],
                "evidence_floor": {"minimum_load_bearing_claims": 1, "require_raw_artifacts": True},
                "artifact_policy": {"default_retention": "session", "allow_provider_payloads": True},
            }
        )
        records = referenced_provider_records(contract, resolved)
        contract["confirmation"] = {
            "confirmed_by": "user",
            "confirmed_at": NOW,
            "card_sha256": contract_card_sha256(contract),
            "registry_sha256": provider_registry_sha256(resolved),
            "referenced_records_sha256": provider_records_sha256(records),
        }
        session = self.root / "perplexity-deep-promote-guard"
        create_session(
            session,
            new_state(contract, NOW, resolved, {"PERPLEXITY_API_KEY": "test-perplexity-key"}),
        )
        state = load_state(session)
        apply_state_patch(
            session,
            [
                {
                    "op": "add",
                    "path": "/retrieval_occurrences/-",
                    "value": {"id": "occ-A1", "provider_id": "perplexity", "action_id": "A1"},
                }
            ],
            state["session"]["revision"],
            NOW,
        )
        with self.assertRaises(ArtifactPolicyError) as ctx:
            promote_provider_payload(session, "A1", "PA1", "session", False, NOW)
        self.assertIn("deep payloads spool under poll action ids", str(ctx.exception))
        self.assertEqual(load_state(session)["artifact_index"], [])

    def test_promote_github_payload_lands_under_raw_with_provider_provenance(self) -> None:
        session = self._make_provider_session(
            "github-promote", "github", allow_provider_payloads=True
        )
        artifact = self._execute_and_promote(
            session, "github", "A1", "PA1",
            transport=fixture_transport("github_success.json"),
        )
        self.assertEqual(artifact["id"], "PA1")
        self.assertEqual(artifact["provenance"]["origin_kind"], "provider_payload")
        self.assertEqual(artifact["provenance"]["provider_id"], "github")
        self.assertEqual(load_state(session)["artifact_index"], [artifact])
        raw_path = session / artifact["relative_path"]
        self.assertEqual(raw_path, session / "raw" / "PA1.json")
        self.assertTrue(raw_path.exists())
        self.assertEqual(
            raw_path.read_bytes(), (FIXTURES / "github_success.json").read_bytes()
        )

    def test_promoted_github_payload_can_support_a_claim_without_provider_claims_forbidden(
        self,
    ) -> None:
        session = self._make_provider_session(
            "github-evidence", "github", allow_provider_payloads=True
        )
        artifact = self._execute_and_promote(
            session, "github", "A1", "PA1",
            transport=fixture_transport("github_success.json"),
        )
        raw_bytes = (session / artifact["relative_path"]).read_bytes()

        state = load_state(session)
        apply_state_patch(
            session,
            [
                {"op": "add", "path": "/source_origins/-", "value": {"id": "O1"}},
                {
                    "op": "add",
                    "path": "/sources/-",
                    "value": {"id": "S1", "origin_id": "O1", "tier": "T1", "direct_fetch": True},
                },
                {
                    "op": "add",
                    "path": "/evidence/-",
                    "value": {
                        "id": "E1",
                        "artifact_id": "PA1",
                        "source_id": "S1",
                        "origin_id": "O1",
                        "source_tier": "T1",
                        "excerpt": raw_bytes.decode("utf-8"),
                        "excerpt_start": 0,
                        "excerpt_end": len(raw_bytes),
                        "entailment": "entailed",
                        "applicability": "checked",
                    },
                },
                {
                    "op": "add",
                    "path": "/claims/-",
                    "value": {
                        "id": "C1",
                        "load_bearing": True,
                        "status": "corroborated",
                        "supporting_evidence_ids": ["E1"],
                        "counter_evidence_ids": [],
                        "source_origin_ids": ["O1"],
                        "applicability": "checked",
                    },
                },
            ],
            state["session"]["revision"],
            NOW,
        )

        report = validate_session(session, check_report=False)
        codes = {issue.code for issue in report.issues}
        # This is the branch this whole feature exists to activate: a
        # can_support_claims=true provider's promoted payload must not be
        # treated as claim-forbidden, and its lineage/storage-rights must
        # check out cleanly (proving the provenance shape written by
        # promote_provider_payload is exactly what validation.py expects).
        self.assertNotIn("evidence.provider_claims_forbidden", codes)
        self.assertNotIn("artifact.provenance", codes)
        self.assertNotIn("artifact.storage_rights", codes)

    def test_promoted_discovery_only_payload_cannot_support_a_claim(self) -> None:
        # crossref's registry record is evidence_capabilities.can_support_
        # claims=false (a discovery/listing route, not a source of record)
        # but -- unlike demo-probe/demo-cascade, whose storage_rights.
        # payload_retention is "forbidden" and so refuse promotion outright
        # -- crossref's payload_retention is "session", so promotion itself
        # succeeds and the can_support_claims gate is the only thing that
        # can catch it. The demo contract also ships allow_provider_payloads
        # =false, so this uses the allowing variant to isolate the
        # can_support_claims gate from the contract gate.
        session = self._make_provider_session(
            "crossref-evidence-forbidden", "crossref", allow_provider_payloads=True
        )
        artifact = self._execute_and_promote(
            session, "crossref", "X1", "PX1",
            transport=fixture_transport("crossref_success.json"),
            query="dynamic factor model nowcasting",
        )
        raw_bytes = (session / artifact["relative_path"]).read_bytes()

        state = load_state(session)
        apply_state_patch(
            session,
            [
                {"op": "add", "path": "/source_origins/-", "value": {"id": "O1"}},
                {
                    "op": "add",
                    "path": "/sources/-",
                    "value": {"id": "S1", "origin_id": "O1", "tier": "T1", "direct_fetch": True},
                },
                {
                    "op": "add",
                    "path": "/evidence/-",
                    "value": {
                        "id": "E1",
                        "artifact_id": "PX1",
                        "source_id": "S1",
                        "origin_id": "O1",
                        "source_tier": "T1",
                        "excerpt": raw_bytes.decode("utf-8"),
                        "excerpt_start": 0,
                        "excerpt_end": len(raw_bytes),
                        "entailment": "entailed",
                        "applicability": "checked",
                    },
                },
                {
                    "op": "add",
                    "path": "/claims/-",
                    "value": {
                        "id": "C1",
                        "load_bearing": True,
                        "status": "corroborated",
                        "supporting_evidence_ids": ["E1"],
                        "counter_evidence_ids": [],
                        "source_origin_ids": ["O1"],
                        "applicability": "checked",
                    },
                },
            ],
            state["session"]["revision"],
            NOW,
        )

        report = validate_session(session, check_report=False)
        self.assertIn(
            "evidence.provider_claims_forbidden", {issue.code for issue in report.errors}
        )


if __name__ == "__main__":
    unittest.main()
