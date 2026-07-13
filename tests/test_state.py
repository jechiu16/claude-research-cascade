from __future__ import annotations

import copy
import unittest

from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
)
from research_harness.contracts import contract_card_sha256
from research_harness.state import new_state, state_sha256, validate_state_document
from tests.helpers import NOW, confirmed_medium_contract


class StateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_provider_registry()
        self.contract = confirmed_medium_contract(self.registry)

    def test_state_snapshots_only_referenced_capabilities_and_hashes(self) -> None:
        state = new_state("Choose a cache", self.contract, NOW, self.registry, {})
        self.assertEqual(state["capabilities"]["registry_sha256"], provider_registry_sha256(self.registry))
        self.assertEqual(
            state["capabilities"]["referenced_records_sha256"],
            provider_records_sha256(state["capabilities"]["providers"]),
        )
        self.assertEqual(
            {provider["id"] for provider in state["capabilities"]["providers"]},
            {"host-web", "local", "host"},
        )
        serialized = str(state["capabilities"]["preflight"])
        self.assertNotIn("secret", serialized)

    def test_new_state_creates_every_canonical_section(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        expected = {
            "schema_version",
            "session",
            "contract",
            "capabilities",
            "framing",
            "summary",
            "hypotheses",
            "planned_checks",
            "observations",
            "retrieval_occurrences",
            "claims",
            "evidence",
            "sources",
            "source_origins",
            "branch_manifests",
            "evidence_deltas",
            "action_metrics",
            "inference_joints",
            "engineering_handoff",
            "open_questions",
            "verification",
            "artifact_index",
        }
        self.assertEqual(set(state), expected)
        self.assertEqual(state["session"]["contract_semantics"], "pure_trigger_v1")
        self.assertEqual(state["session"]["revision"], 0)
        self.assertEqual(validate_state_document(state), [])

    def test_state_document_rejects_missing_sections_and_duplicate_ids(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        del state["claims"]
        state["evidence"] = [{"id": "E1"}, {"id": "E1"}]
        errors = validate_state_document(state)
        self.assertIn("state section claims is required", errors)
        self.assertIn("duplicate evidence id E1", errors)

    def test_new_state_rejects_missing_contract_axes(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract.pop("execution")
        contract.pop("durability")
        contract["confirmation"]["card_sha256"] = contract_card_sha256(contract)
        with self.assertRaisesRegex(ValueError, "execution and durability axes are required"):
            new_state("Q", contract, NOW, self.registry, {})

    def test_persisted_legacy_state_remains_valid_without_axes(self) -> None:
        legacy = copy.deepcopy(new_state("Q", self.contract, NOW, self.registry, {}))
        legacy["contract"].pop("execution")
        legacy["contract"].pop("durability")
        legacy["session"].pop("contract_semantics")
        legacy["contract"]["confirmation"]["card_sha256"] = contract_card_sha256(legacy["contract"])
        self.assertEqual(validate_state_document(legacy), [])

    def test_semantics_marker_requires_paired_axes(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        state["contract"].pop("execution")
        state["contract"].pop("durability")
        state["contract"]["confirmation"]["card_sha256"] = contract_card_sha256(state["contract"])
        errors = validate_state_document(state)
        self.assertIn("contract: contract execution and durability axes are required", errors)

    def test_state_document_rejects_broken_references(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        state["claims"] = [{"id": "C1", "supporting_evidence_ids": ["E-missing"]}]
        errors = validate_state_document(state)
        self.assertIn("claim C1 references missing evidence E-missing", errors)

    def test_state_document_rejects_summary_reference_to_missing_claim(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        state["summary"]["load_bearing_claim_ids"] = ["C-missing"]
        errors = validate_state_document(state)
        self.assertIn("summary references missing claim C-missing", errors)

    def test_state_document_detects_capability_snapshot_tampering(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        tampered = copy.deepcopy(state)
        tampered["capabilities"]["providers"][0]["enabled"] = False
        errors = validate_state_document(tampered)
        self.assertIn("capability referenced-records hash mismatch", errors)

    def test_state_document_rejects_preflight_secret_or_unknown_fields(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        state["capabilities"]["preflight"][0]["value"] = "secret-value"
        errors = validate_state_document(state)
        self.assertIn("capability preflight record contains forbidden fields", errors)

    def test_state_document_rejects_preflight_provider_mismatch(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        state["capabilities"]["preflight"][0]["provider_id"] = "unknown-provider"
        errors = validate_state_document(state)
        self.assertIn("capability preflight references missing provider unknown-provider", errors)

    def test_state_document_handles_malformed_provider_record_without_crashing(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        state["capabilities"]["providers"].append("not-an-object")
        errors = validate_state_document(state)
        self.assertIn("capability snapshot: provider record 3 must be an object", errors)

    def test_state_hash_is_stable_and_sensitive_to_content(self) -> None:
        state = new_state("Q", self.contract, NOW, self.registry, {})
        self.assertEqual(state_sha256(state), state_sha256(copy.deepcopy(state)))
        changed = copy.deepcopy(state)
        changed["summary"]["decision"] = "Changed"
        self.assertNotEqual(state_sha256(state), state_sha256(changed))

    def test_session_ids_do_not_collide_for_same_question_and_timestamp(self) -> None:
        first = new_state("Q", self.contract, NOW, self.registry, {})
        second = new_state("Q", self.contract, NOW, self.registry, {})
        self.assertNotEqual(first["session"]["id"], second["session"]["id"])


if __name__ == "__main__":
    unittest.main()
