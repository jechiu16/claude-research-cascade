from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_harness.providers import load_provider_registry
from research_harness.quota import (
    ContractNotConfirmed,
    DuplicateAction,
    InvalidAttemptTransition,
    QuotaExceeded,
    _record_attempt_status_unlocked,
    acquire_permits,
    permit_usage,
)
from research_harness.state import new_state
from research_harness.storage import create_session, read_events, session_lock
from tests.helpers import NOW, confirmed_demo_contract


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
        contract = confirmed_demo_contract(route, request_count, probe_ceiling, self.registry)
        state = new_state(contract, NOW, self.registry, {})
        create_session(session, state)
        return session

    def test_unconfirmed_contract_cannot_acquire(self) -> None:
        state_path = self.session / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["contract"]["confirmation"]["confirmed_by"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(ContractNotConfirmed):
            acquire_permits(
                self.session, "A1", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
            )

    def test_atomic_reservation_never_partially_consumes(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A1", "primary_scout", "probe", "demo-probe", 4, "sha256:x", NOW
            )
        self.assertEqual(permit_usage(self.session)["probe"], 0)

    def test_composite_scout_reserves_full_multiplicity(self) -> None:
        session = self._make_session("cascade", "demo-cascade", 4, 4)
        permits = acquire_permits(
            session, "A1", "primary_scout", "probe", "demo-cascade", 4, "sha256:x", NOW
        )
        self.assertEqual(len(permits), 4)
        self.assertEqual(permit_usage(session)["probe"], 4)

    def test_composite_scout_cannot_reserve_partial_multiplicity(self) -> None:
        session = self._make_session("cascade-partial", "demo-cascade", 4, 4)
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                session, "A1", "primary_scout", "probe", "demo-cascade", 1, "sha256:x", NOW
            )

    def test_uncertain_attempt_does_not_refund(self) -> None:
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
        )
        with session_lock(self.session):
            _record_attempt_status_unlocked(self.session, "A1", "attempted", NOW)
            _record_attempt_status_unlocked(self.session, "A1", "uncertain", NOW)
        self.assertEqual(permit_usage(self.session)["probe"], 1)

    def test_second_primary_scout_is_rejected_with_spare_category_capacity(self) -> None:
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "demo-probe", 1, "sha256:a", NOW
        )
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "demo-probe", 1, "sha256:b", NOW
            )

    def test_discovery_cannot_consume_reserved_mapping(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session,
                "A1",
                "primary_scout",
                "organizer_pass",
                "host",
                1,
                "sha256:x",
                NOW,
            )

    def test_local_and_organizer_actions_are_counted_without_external_spend(self) -> None:
        acquire_permits(
            self.session, "L1", "local_applicability", "local", "local", 1, "sha256:l", NOW
        )
        acquire_permits(
            self.session,
            "O1",
            "final_inference_review",
            "organizer_pass",
            "host",
            1,
            "sha256:o",
            NOW,
        )
        usage = permit_usage(self.session)
        self.assertEqual(usage["local"], 1)
        self.assertEqual(usage["organizer_pass"], 1)

    def test_duplicate_action_id_is_rejected(self) -> None:
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
        )
        with self.assertRaises(DuplicateAction):
            acquire_permits(
                self.session, "A1", "primary_scout", "probe", "demo-probe", 1, "sha256:y", NOW
            )

    def test_invalid_attempt_transition_is_rejected(self) -> None:
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
        )
        with self.assertRaises(InvalidAttemptTransition):
            with session_lock(self.session):
                _record_attempt_status_unlocked(self.session, "A1", "completed", NOW)
        self.assertEqual(len(read_events(self.session)[0]), 2)

    # -- action_id format (security regression: path-traversal action_id) --
    #
    # promote_provider_payload and boundary._spool_raw both key a filesystem
    # path off action_id (provider_spool/<action_id>.raw.json). Every
    # permit-gated write path (execute_probe/execute_deep_submit/
    # execute_deep_poll) only ever sees an action_id that already went
    # through acquire_permits, so rejecting a malformed shape here is what
    # closes those paths off. See tests/test_artifacts.py
    # PromoteProviderPayloadTests for the read-side occurrence-injection
    # variant, which does not go through acquire_permits at all.

    def test_acquire_permits_rejects_path_traversal_action_id(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "../../evil", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
            )
        self.assertEqual(permit_usage(self.session)["probe"], 0)

    def test_acquire_permits_rejects_action_id_with_slash(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "a/b", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
            )
        self.assertEqual(permit_usage(self.session)["probe"], 0)

    def test_acquire_permits_rejects_action_id_with_space(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "a b", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
            )
        self.assertEqual(permit_usage(self.session)["probe"], 0)

    def test_acquire_permits_rejects_empty_action_id(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "", "primary_scout", "probe", "demo-probe", 1, "sha256:x", NOW
            )
        self.assertEqual(permit_usage(self.session)["probe"], 0)

    def test_acquire_permits_accepts_conventional_action_ids(self) -> None:
        # Three differently-shaped IDs already in production use (single
        # letter+digit, and a multi-letter prefix+digit), each landing on a
        # distinct stage/category/route slot that confirmed_demo_contract's
        # fixture actually maps -- proves the format gate does not regress
        # any existing convention.
        for action_id, stage, category, route in (
            ("A1", "primary_scout", "probe", "demo-probe"),
            ("D1", "local_applicability", "local", "local"),
            ("CL6", "final_inference_review", "organizer_pass", "host"),
        ):
            acquire_permits(
                self.session, action_id, stage, category, route, 1, f"sha256:{action_id.lower()}", NOW
            )
        usage = permit_usage(self.session)
        self.assertEqual(usage["probe"], 1)
        self.assertEqual(usage["local"], 1)
        self.assertEqual(usage["organizer_pass"], 1)


if __name__ == "__main__":
    unittest.main()
