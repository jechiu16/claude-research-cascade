from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from research_harness.contracts import normalize_contract, validate_contract
from research_harness.providers import (
    ProviderRegistryError,
    load_provider_registry,
    preflight_contract_routes,
    provider_registry_sha256,
    validate_provider_registry,
)
from tests.helpers import confirmed_contract, confirmed_medium_contract, draft_medium_contract, write_overlay


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_provider_registry()
        self.contract = confirmed_medium_contract(self.registry)

    def test_confirmed_contract_normalizes_all_physical_ceilings(self) -> None:
        contract = normalize_contract(self.contract)
        self.assertEqual(contract["resource_envelope"]["physical_ceiling"]["host_retrieval"], 3)
        self.assertEqual(contract["resource_envelope"]["physical_ceiling"]["local"], 1)
        self.assertEqual(contract["resource_envelope"]["physical_ceiling"]["organizer_pass"], 1)
        self.assertEqual(validate_contract(contract, self.registry), [])

    def test_unconfirmed_contract_is_rejected(self) -> None:
        contract = draft_medium_contract()
        self.assertIn("contract is not user-confirmed", validate_contract(contract, self.registry))

    def test_malformed_contract_returns_errors_instead_of_raising(self) -> None:
        malformed = {"resource_envelope": "not-an-object"}
        errors = validate_contract(malformed, self.registry)
        self.assertIn("contract is not user-confirmed", errors)
        self.assertIn("resource envelope is required", errors)

    def test_explicit_empty_registry_is_not_replaced_by_default(self) -> None:
        errors = validate_contract(self.contract, {})
        self.assertIn("provider registry schema_version must be 1.0", errors)

    def test_undecodable_registry_file_raises_typed_provider_registry_error(self) -> None:
        # _load_json's path.read_text(encoding="utf-8") raises
        # UnicodeDecodeError on non-UTF-8 bytes, which the old
        # `except (OSError, json.JSONDecodeError)` did not catch --
        # regression for that untyped-exception escape (mirrors storage.py's
        # _read_json / _load_state_unlocked fix).
        with tempfile.TemporaryDirectory() as tempdir:
            bad_path = Path(tempdir) / "registry.json"
            bad_path.write_bytes(b"\xff\xfe")
            with self.assertRaises(ProviderRegistryError):
                load_provider_registry(path=bad_path)

    def test_confirmation_binds_card_and_resolved_registry_hashes(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resource_envelope"]["physical_ceiling"]["host_retrieval"] += 1
        self.assertIn(
            "confirmed card hash does not match contract",
            validate_contract(contract, self.registry),
        )

    def test_confirmed_contract_rejects_different_registry_overlay(self) -> None:
        host = copy.deepcopy(next(p for p in self.registry["providers"] if p["id"] == "host-web"))
        host["roles"] = ["scout", "fetch"]
        with tempfile.TemporaryDirectory() as tempdir:
            overlay = write_overlay(Path(tempdir) / "overlay.json", [host])
            overlaid = load_provider_registry(overlay=overlay)
        errors = validate_contract(self.contract, overlaid)
        self.assertIn("confirmed registry hash does not match resolved registry", errors)

    def test_preflight_records_presence_without_secret_values(self) -> None:
        records, errors = preflight_contract_routes(
            self.contract,
            self.registry,
            {"TOKEN": "secret-value"},
        )
        self.assertEqual(errors, [])
        self.assertNotIn("secret-value", json.dumps(records))

    def test_negative_or_boolean_ceiling_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resource_envelope"]["physical_ceiling"]["deep"] = True
        self.assertIn(
            "physical ceiling deep must be a non-negative integer",
            validate_contract(contract, self.registry),
        )

    def test_contract_requires_exactly_one_primary_scout(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["stage_permit_map"].append(copy.deepcopy(contract["stage_permit_map"][0]))
        self.assertIn(
            "exactly one primary_scout mapping with one invocation is required",
            validate_contract(contract, self.registry),
        )

    def test_medium_requires_reserved_post_result_reinforcement(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["stage_permit_map"] = [
            mapping
            for mapping in contract["stage_permit_map"]
            if mapping["stage"] not in {"anti_lock_in", "verification"}
        ]
        self.assertIn(
            "medium and high tiers require reserved post-result reinforcement",
            validate_contract(contract, self.registry),
        )

    def test_high_requires_reserved_context_separated_verifier_capacity(self) -> None:
        contract = confirmed_contract("high", "decision", self.registry)
        verifier = next(
            mapping
            for mapping in contract["stage_permit_map"]
            if mapping["stage"] == "context_separated_verification"
        )
        self.assertTrue(verifier["reserved"])
        missing = copy.deepcopy(contract)
        missing["stage_permit_map"] = [
            mapping
            for mapping in missing["stage_permit_map"]
            if mapping["stage"] != "context_separated_verification"
        ]
        self.assertIn(
            "high tier requires reserved context-separated verifier capacity",
            validate_contract(missing, self.registry),
        )

    def test_host_external_and_local_envelopes_are_distinct(self) -> None:
        contract = normalize_contract(self.contract)
        self.assertEqual(contract["resource_envelope"]["host"]["context_class"], "standard")
        self.assertEqual(contract["resource_envelope"]["external"]["metered_ceiling"]["probe"], 0)
        self.assertEqual(contract["resource_envelope"]["external"]["metered_ceiling"]["transport"], 0)
        self.assertEqual(contract["resource_envelope"]["local"]["admitted_output_characters"], 12000)
        self.assertEqual(contract["resource_envelope"]["local"]["max_wall_time_seconds"], 900)

    def test_metered_subceiling_cannot_exceed_physical_ceiling(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resource_envelope"]["external"]["metered_ceiling"]["deep"] = 2
        self.assertIn("metered ceiling deep exceeds physical ceiling", validate_contract(contract, self.registry))

    def test_network_experiment_requires_endpoint_policy(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resource_envelope"]["physical_ceiling"]["network_experiment"] = 1
        contract["resource_envelope"]["external"]["metered_ceiling"]["network_experiment"] = 1
        self.assertIn("network experiment endpoint policy is required", validate_contract(contract, self.registry))

    def test_route_must_exist_and_support_stage_category(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["stage_permit_map"][0]["route"] = "unknown-search"
        self.assertIn(
            "route unknown-search is not enabled in capability registry",
            validate_contract(contract, self.registry),
        )
        contract["stage_permit_map"][0]["route"] = "deepseek"
        self.assertIn(
            "route deepseek is not enabled in capability registry",
            validate_contract(contract, self.registry),
        )

    def test_physical_count_must_match_route_multiplicity(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["stage_permit_map"][0]["count"] = 2
        self.assertIn(
            "route host-web invocation/count must be 1/1 for host_retrieval",
            validate_contract(contract, self.registry),
        )

    def test_registry_overlay_can_add_disabled_candidate(self) -> None:
        # "test-only-unbound-candidate" (see the permanent sentinel note on
        # test_enabled_external_route_requires_bound_interceptor_and_adoption
        # below) -- this test needs a record that is guaranteed to still be
        # disabled; brave served that role until adapter/brave built it out
        # for real (2026-07-11), same trap the sentinel was reserved for.
        candidate = copy.deepcopy(
            next(p for p in self.registry["providers"] if p["id"] == "test-only-unbound-candidate")
        )
        candidate["docs_verified_at"] = "2026-07-11"
        with tempfile.TemporaryDirectory() as tempdir:
            overlay = write_overlay(Path(tempdir) / "overlay.json", [candidate])
            registry = load_provider_registry(overlay=overlay)
        self.assertEqual(validate_provider_registry(registry), [])
        sentinel = next(p for p in registry["providers"] if p["id"] == "test-only-unbound-candidate")
        self.assertFalse(sentinel["enabled"])

    def test_registry_overlay_cannot_enable_unbound_candidate(self) -> None:
        # Same permanent sentinel: it never leaves execution_binding
        # "legacy_unbound", so this stays a true "unbound candidate" case
        # instead of chasing whichever real provider is still unbound today.
        candidate = copy.deepcopy(
            next(p for p in self.registry["providers"] if p["id"] == "test-only-unbound-candidate")
        )
        candidate["enabled"] = True
        with tempfile.TemporaryDirectory() as tempdir:
            overlay = write_overlay(Path(tempdir) / "overlay.json", [candidate])
            with self.assertRaises(ProviderRegistryError):
                load_provider_registry(overlay=overlay)

    def test_registry_overlay_rejects_duplicate_provider_records(self) -> None:
        candidate = copy.deepcopy(next(p for p in self.registry["providers"] if p["id"] == "brave"))
        with tempfile.TemporaryDirectory() as tempdir:
            overlay = write_overlay(Path(tempdir) / "overlay.json", [candidate, candidate])
            with self.assertRaises(ProviderRegistryError):
                load_provider_registry(overlay=overlay)

    def test_registry_overlay_cannot_change_binding_or_multiplicity(self) -> None:
        host = copy.deepcopy(next(p for p in self.registry["providers"] if p["id"] == "host-web"))
        variants = []
        changed_binding = copy.deepcopy(host)
        changed_binding["execution_binding"] = "v2_request_boundary"
        variants.append(changed_binding)
        changed_count = copy.deepcopy(host)
        changed_count["request_multiplicity"]["host_retrieval"] = 2
        variants.append(changed_count)
        broader_storage = copy.deepcopy(host)
        broader_storage["storage_rights"]["payload_retention"] = "persistent"
        broader_storage["storage_rights"]["html_allowed"] = True
        variants.append(broader_storage)
        with tempfile.TemporaryDirectory() as tempdir:
            for index, variant in enumerate(variants):
                with self.subTest(index=index):
                    overlay = write_overlay(Path(tempdir) / f"overlay-{index}.json", [variant])
                    with self.assertRaises(ProviderRegistryError):
                        load_provider_registry(overlay=overlay)

    def test_enabled_external_route_requires_bound_interceptor_and_adoption(self) -> None:
        # "test-only-unbound-candidate" is a permanent synthetic registry
        # record (relies entirely on provider_defaults, so it always stays on
        # execution_binding "legacy_unbound") reserved exactly for this test.
        # Earlier versions of this test hardcoded a real candidate id
        # (sonar, then brave, then mojeek in turn) and broke every time that
        # candidate's adapter got built out for real. Do not point this back
        # at a real provider id — see research_harness/adapters/README.md.
        registry = copy.deepcopy(self.registry)
        sentinel = next(p for p in registry["providers"] if p["id"] == "test-only-unbound-candidate")
        sentinel["enabled"] = True
        errors = validate_provider_registry(registry)
        self.assertIn("enabled external route test-only-unbound-candidate is not v2-bound", errors)
        sentinel["execution_binding"] = "v2_request_boundary"
        errors = validate_provider_registry(registry)
        self.assertIn("enabled external route test-only-unbound-candidate lacks adoption evidence", errors)

    def test_enabled_external_adoption_evidence_must_be_nonempty(self) -> None:
        # Same permanent sentinel as above — moved for consistency. This test
        # overrides every field it touches, so it never actually depended on
        # brave specifically; pinning it to a real candidate id was still a
        # latent trap for the next adapter builder.
        registry = copy.deepcopy(self.registry)
        sentinel = next(p for p in registry["providers"] if p["id"] == "test-only-unbound-candidate")
        sentinel["enabled"] = True
        sentinel["execution_binding"] = "v2_request_boundary"
        sentinel["adoption_status"] = "validated"
        sentinel["adoption_evidence"] = []
        sentinel["storage_rights"]["payload_retention"] = "session"
        errors = validate_provider_registry(registry)
        self.assertIn("enabled external route test-only-unbound-candidate lacks adoption evidence", errors)

    def test_enabled_sonar_route_is_v2_bound_with_adoption_evidence(self) -> None:
        sonar = next(p for p in self.registry["providers"] if p["id"] == "sonar")
        self.assertTrue(sonar["enabled"])
        self.assertEqual(sonar["execution_binding"], "v2_request_boundary")
        self.assertEqual(validate_provider_registry(self.registry), [])

    def test_enabled_route_rejects_sunset_or_unknown_storage_policy(self) -> None:
        registry = copy.deepcopy(self.registry)
        host = next(p for p in registry["providers"] if p["id"] == "host-web")
        host["lifecycle"]["status"] = "sunset"
        host["storage_rights"]["payload_retention"] = "unknown"
        errors = validate_provider_registry(registry)
        self.assertIn("enabled route host-web is sunset", errors)
        self.assertIn("enabled route host-web has unknown storage rights", errors)

    def test_registry_hash_does_not_depend_on_record_order(self) -> None:
        reversed_registry = copy.deepcopy(self.registry)
        reversed_registry["providers"].reverse()
        self.assertEqual(
            provider_registry_sha256(self.registry),
            provider_registry_sha256(reversed_registry),
        )


if __name__ == "__main__":
    unittest.main()
