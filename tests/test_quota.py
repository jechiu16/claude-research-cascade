from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from research_harness.boundary import BoundaryError, execute_probe
from research_harness.contracts import contract_card_sha256, normalize_contract
from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
)
from research_harness.quota import (
    ContractNotConfirmed,
    DuplicateAction,
    InvalidAttemptTransition,
    QuotaExceeded,
    _record_attempt_status_unlocked,
    _reserve_boundary_action_unlocked,
    acquire_permits,
    cost_usage,
    permit_usage,
)
from research_harness.state import new_state
from research_harness.rendering import finalize_session_result
from research_harness.storage import create_session, load_state, read_events, session_lock
from tests.helpers import NOW, confirmed_demo_contract, draft_host_led_contract


class QuotaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.registry = load_provider_registry()
        self.session = self._make_session("session")

    def _make_session(
        self,
        name: str,
        route: str = "demo-probe",
        request_count: int = 1,
        probe_ceiling: int = 2,
    ) -> Path:
        session = self.root / name
        contract = confirmed_demo_contract(
            route=route,
            request_count=request_count,
            probe_ceiling=probe_ceiling,
            registry=self.registry,
        )
        create_session(session, new_state(contract, NOW, self.registry, {}))
        return session

    def _acquire_legacy(self, session: Path, action_id: str = "L1") -> None:
        acquire_permits(session, action_id, "local_applicability", "local", "local", 1, NOW)

    def _make_cost_limited_session(self) -> Path:
        registry = copy.deepcopy(self.registry)
        demo = next(provider for provider in registry["providers"] if provider["id"] == "demo-probe")
        demo["cost_class"] = "search"
        demo["stage_capabilities"].append("verification")
        contract = draft_host_led_contract()
        contract["scout_route"] = "demo-probe"
        physical = contract["resource_envelope"]["physical_ceiling"]
        physical.update({category: 0 for category in physical})
        physical.update({"probe": 2, "organizer_pass": 1})
        contract["resource_envelope"]["external"]["metered_ceiling"].update(
            {category: 0 for category in contract["resource_envelope"]["external"]["metered_ceiling"]}
        )
        contract["resource_envelope"]["cost_budget"] = {
            "profile": "light",
            "deep": 0,
            "search": 1,
            "free": "unlimited",
        }
        contract["stage_permit_map"] = [
            {
                "stage": "primary_scout",
                "category": "probe",
                "route": "demo-probe",
                "invocations": 1,
                "count": 1,
                "reserved": False,
            },
            {
                "stage": "verification",
                "category": "probe",
                "route": "demo-probe",
                "invocations": 1,
                "count": 1,
                "reserved": True,
            },
            {
                "stage": "final_inference_review",
                "category": "organizer_pass",
                "route": "host",
                "invocations": 1,
                "count": 1,
                "reserved": True,
            },
        ]
        contract = normalize_contract(contract)
        records = referenced_provider_records(contract, registry)
        contract["confirmation"] = {
            "confirmed_by": "user",
            "confirmed_at": NOW,
            "card_sha256": contract_card_sha256(contract),
            "registry_sha256": provider_registry_sha256(registry),
            "referenced_records_sha256": provider_records_sha256(records),
        }
        session = self.root / "cost-limited"
        create_session(session, new_state(contract, NOW, registry, {}))
        return session

    def test_unconfirmed_contract_cannot_acquire(self) -> None:
        state_path = self.session / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["contract"]["confirmation"]["confirmed_by"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(ContractNotConfirmed):
            self._acquire_legacy(self.session)

    def test_boundary_categories_cannot_be_separately_acquired(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(self.session, "P1", "primary_scout", "probe", "demo-probe", 1, NOW)
        self.assertEqual(permit_usage(self.session)["probe"], 0)

    def test_actual_boundary_reserves_full_composite_multiplicity(self) -> None:
        session = self._make_session("cascade", "demo-cascade", 4, 4)
        execute_probe(session, "A1", "primary_scout", "demo-cascade", "q", NOW)
        self.assertEqual(permit_usage(session)["probe"], 4)

    def test_boundary_rejects_partial_composite_reservation(self) -> None:
        session = self._make_session("cascade-partial", "demo-cascade", 4, 4)
        with self.assertRaises(QuotaExceeded):
            with session_lock(session):
                _reserve_boundary_action_unlocked(
                    session,
                    "A1",
                    "primary_scout",
                    "probe",
                    "demo-cascade",
                    1,
                    "0" * 64,
                    NOW,
                )
        self.assertEqual(permit_usage(session)["probe"], 0)

    def test_boundary_stage_exhaustion_does_not_block_spare_legacy_category(self) -> None:
        execute_probe(self.session, "A1", "primary_scout", "demo-probe", "q", NOW)
        with self.assertRaises(BoundaryError):
            execute_probe(self.session, "A2", "primary_scout", "demo-probe", "q", NOW)
        self._acquire_legacy(self.session)

    def test_cost_budget_stops_second_external_call_without_consuming_it(self) -> None:
        session = self._make_cost_limited_session()
        execute_probe(session, "A1", "primary_scout", "demo-probe", "q1", NOW)
        with self.assertRaisesRegex(BoundaryError, "cost budget exhausted for search"):
            execute_probe(session, "A2", "verification", "demo-probe", "q2", NOW)
        self.assertEqual(cost_usage(session), {"deep": 0, "search": 1, "free": 0})
        self.assertEqual(permit_usage(session)["probe"], 1)
        events, errors = read_events(session)
        self.assertEqual(errors, [])
        self.assertEqual(
            sum(event.get("event") == "budget_exhausted" for event in events), 1
        )

        rendered = finalize_session_result(session, NOW)
        state = load_state(session)
        gap = next(
            item for item in state["open_questions"] if item["id"] == "budget-exhausted-search"
        )
        self.assertIn("現有材料交付", gap["question"])
        self.assertTrue(rendered.path.exists())

    def test_action_id_conventions_and_path_safety_are_enforced_by_boundary(self) -> None:
        for action_id in ("A1", "D1", "CL6"):
            session = self._make_session(action_id)
            execute_probe(session, action_id, "primary_scout", "demo-probe", "q", NOW)
        for index, action_id in enumerate(("../../evil", "a/b", "a b")):
            session = self._make_session(f"invalid-{index}")
            with self.assertRaises(BoundaryError):
                execute_probe(session, action_id, "primary_scout", "demo-probe", "q", NOW)

    def test_legacy_permit_has_acquired_lifecycle_without_fingerprint(self) -> None:
        self._acquire_legacy(self.session)
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        permit = next(event for event in events if event.get("action_id") == "L1")
        self.assertNotIn("fingerprint", permit)
        self.assertNotIn("initial_status", permit)
        self.assertEqual(permit_usage(self.session)["local"], 1)

    def test_uncertain_legacy_attempt_does_not_refund(self) -> None:
        self._acquire_legacy(self.session)
        with session_lock(self.session):
            _record_attempt_status_unlocked(self.session, "L1", "attempted", NOW)
            _record_attempt_status_unlocked(self.session, "L1", "uncertain", NOW)
        self.assertEqual(permit_usage(self.session)["local"], 1)

    def test_second_legacy_action_is_rejected_when_mapping_is_exhausted(self) -> None:
        self._acquire_legacy(self.session)
        with self.assertRaises(QuotaExceeded):
            self._acquire_legacy(self.session, "L2")

    def test_local_and_organizer_actions_are_counted_without_external_spend(self) -> None:
        self._acquire_legacy(self.session)
        acquire_permits(self.session, "O1", "final_inference_review", "organizer_pass", "host", 1, NOW)
        usage = permit_usage(self.session)
        self.assertEqual(usage["local"], 1)
        self.assertEqual(usage["organizer_pass"], 1)

    def test_duplicate_legacy_action_id_is_rejected(self) -> None:
        self._acquire_legacy(self.session)
        with self.assertRaises(DuplicateAction):
            self._acquire_legacy(self.session)

    def test_invalid_legacy_attempt_transition_is_rejected(self) -> None:
        self._acquire_legacy(self.session)
        with self.assertRaises(InvalidAttemptTransition):
            with session_lock(self.session):
                _record_attempt_status_unlocked(self.session, "L1", "completed", NOW)

    def test_legacy_action_id_validation_blocks_path_traversal(self) -> None:
        with self.assertRaises(QuotaExceeded):
            self._acquire_legacy(self.session, "../../evil")
        self.assertEqual(permit_usage(self.session)["local"], 0)

    def test_legacy_action_id_validation_blocks_slash_space_and_empty(self) -> None:
        for action_id in ("a/b", "a b", ""):
            with self.assertRaises(QuotaExceeded):
                self._acquire_legacy(self.session, action_id)
        self.assertEqual(permit_usage(self.session)["local"], 0)


if __name__ == "__main__":
    unittest.main()
