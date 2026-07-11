from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from research_harness.state import new_state, state_sha256
from research_harness.storage import (
    ProtectedStatePath,
    RecoveryError,
    RevisionConflict,
    SessionLockTimeout,
    StateValidationError,
    StorageError,
    _append_event_unlocked,
    _apply_artifact_state_patch_unlocked,
    apply_state_patch,
    create_session,
    load_state,
    read_events,
    recover_session,
    session_lock,
)
from tests.helpers import NOW, confirmed_medium_contract
from research_harness.providers import load_provider_registry


LATER = "2026-07-10T12:01:00Z"


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.session = self.root / "session"
        registry = load_provider_registry()
        contract = confirmed_medium_contract(registry)
        self.state = new_state("Choose a cache", contract, NOW, registry, {})
        create_session(self.session, self.state)

    def test_create_session_writes_state_and_genesis_event(self) -> None:
        loaded = load_state(self.session)
        self.assertEqual(loaded["schema_version"], "2.0")
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        self.assertEqual(events[0]["event"], "session_created")
        self.assertEqual(events[0]["state_sha256"], state_sha256(loaded))

    def test_session_state_and_event_permissions_are_private(self) -> None:
        self.assertEqual(self.session.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.session / "state.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.session / "events.jsonl").stat().st_mode & 0o777, 0o600)

    def test_nested_lock_times_out_without_stealing_owner(self) -> None:
        with session_lock(self.session):
            with self.assertRaises(SessionLockTimeout):
                with session_lock(self.session, timeout_s=0.01):
                    self.fail("nested lock unexpectedly acquired")

    def test_state_transitions_assign_monotonic_hash_chain(self) -> None:
        first = apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/decision", "value": "one"}],
            0,
            NOW,
        )
        apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/decision", "value": "two"}],
            first["session"]["revision"],
            LATER,
        )
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        revisions = [event for event in events if event["event"] == "state_revision"]
        self.assertEqual(revisions[1]["seq"], revisions[0]["seq"] + 1)
        self.assertEqual(revisions[1]["prev_hash"], revisions[0]["event_hash"])

    def test_malformed_trailing_event_is_reported_without_losing_prior_events(self) -> None:
        with (self.session / "events.jsonl").open("ab") as handle:
            handle.write(b'{"event":"broken"')
        events, errors = read_events(self.session)
        self.assertEqual(len(events), 1)
        self.assertEqual(errors, ["events.jsonl:2 invalid JSON"])

    def test_validated_patch_increments_revision_and_records_hashes(self) -> None:
        updated = apply_state_patch(
            self.session,
            [{"op": "replace", "path": "/summary/decision", "value": "Use bounded cache"}],
            0,
            NOW,
        )
        self.assertEqual(updated["session"]["revision"], 1)
        event = read_events(self.session)[0][-1]
        self.assertEqual(event["event"], "state_revision")
        self.assertEqual(event["new_state_sha256"], state_sha256(updated))

    def test_invalid_patch_never_replaces_canonical_state(self) -> None:
        before = load_state(self.session)
        with self.assertRaises(ProtectedStatePath):
            apply_state_patch(
                self.session,
                [{"op": "remove", "path": "/contract"}],
                0,
                NOW,
            )
        self.assertEqual(load_state(self.session), before)

    def test_structurally_invalid_patch_never_replaces_state(self) -> None:
        before = load_state(self.session)
        with self.assertRaises(StateValidationError):
            apply_state_patch(
                self.session,
                [{"op": "replace", "path": "/claims", "value": [{"id": "C1"}, {"id": "C1"}]}],
                0,
                NOW,
            )
        self.assertEqual(load_state(self.session), before)

    def test_stale_revision_is_rejected(self) -> None:
        with self.assertRaises(RevisionConflict):
            apply_state_patch(self.session, [], 9, NOW)

    def test_boolean_revision_is_rejected(self) -> None:
        with self.assertRaises(RevisionConflict):
            apply_state_patch(self.session, [], False, NOW)

    def test_organizer_patch_cannot_change_protected_sections(self) -> None:
        protected = (
            ("/contract/resource_envelope/physical_ceiling/probe", 99),
            ("/capabilities/providers/0/enabled", False),
            ("/session/revision", 99),
            ("/session/id", "forged"),
            ("/artifact_index", []),
        )
        for path, value in protected:
            with self.subTest(path=path), self.assertRaises(ProtectedStatePath):
                apply_state_patch(
                    self.session,
                    [{"op": "replace", "path": path, "value": value}],
                    0,
                    NOW,
                )

    def test_artifact_transition_cannot_modify_contract_or_capabilities(self) -> None:
        for path in ("/contract", "/capabilities"):
            with self.subTest(path=path), self.assertRaises(ProtectedStatePath):
                with session_lock(self.session):
                    _apply_artifact_state_patch_unlocked(
                        self.session,
                        "ingest",
                        [{"op": "replace", "path": path, "value": {}}],
                        0,
                        NOW,
                    )

    def test_recovery_rolls_forward_after_state_replace_before_event_append(self) -> None:
        with mock.patch("research_harness.storage._append_bytes_unlocked", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                apply_state_patch(
                    self.session,
                    [{"op": "replace", "path": "/summary/decision", "value": "new"}],
                    0,
                    NOW,
                )
        self.assertTrue((self.session / "transaction.json").exists())
        recovered = recover_session(self.session)
        self.assertEqual(recovered["resolution"], "rolled_forward")
        self.assertEqual(load_state(self.session)["summary"]["decision"], "new")
        self.assertEqual(read_events(self.session)[0][-1]["event"], "state_revision")
        self.assertFalse((self.session / "transaction.json").exists())

    def test_recovery_rolls_back_before_state_replace(self) -> None:
        with mock.patch("research_harness.storage._replace_state_unlocked", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                apply_state_patch(
                    self.session,
                    [{"op": "replace", "path": "/summary/decision", "value": "new"}],
                    0,
                    NOW,
                )
        recovered = recover_session(self.session)
        self.assertEqual(recovered["resolution"], "rolled_back")
        self.assertEqual(load_state(self.session)["session"]["revision"], 0)

    def test_recovery_repairs_transaction_owned_partial_revision_tail(self) -> None:
        def partial_write(path: Path, payload: bytes) -> None:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, payload[: max(1, len(payload) // 2)])
                os.fsync(fd)
            finally:
                os.close(fd)
            raise OSError("crash")

        with mock.patch("research_harness.storage._append_bytes_unlocked", side_effect=partial_write):
            with self.assertRaises(OSError):
                apply_state_patch(
                    self.session,
                    [{"op": "replace", "path": "/summary/decision", "value": "new"}],
                    0,
                    NOW,
                )
        recovered = recover_session(self.session)
        events, errors = read_events(self.session)
        self.assertEqual(recovered["resolution"], "rolled_forward")
        self.assertEqual(errors, [])
        self.assertEqual(events[-1]["event"], "state_revision")

    def test_recovery_completes_owned_partial_event_without_state_change(self) -> None:
        def partial_write(path: Path, payload: bytes) -> None:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, payload[:7])
                os.fsync(fd)
            finally:
                os.close(fd)
            raise OSError("crash")

        with self.assertRaises(OSError):
            with session_lock(self.session):
                with mock.patch("research_harness.storage._append_bytes_unlocked", side_effect=partial_write):
                    _append_event_unlocked(self.session, {"event": "note", "at": NOW})
        recovered = recover_session(self.session)
        events, errors = read_events(self.session)
        self.assertEqual(recovered["resolution"], "event_rolled_forward")
        self.assertEqual(errors, [])
        self.assertEqual(events[-1]["event"], "note")

    def test_recovery_never_truncates_unowned_malformed_tail(self) -> None:
        with (self.session / "events.jsonl").open("ab") as handle:
            handle.write(b'{"event":"unknown"')
        with self.assertRaises(RecoveryError):
            recover_session(self.session)

    def test_recovery_rejects_parseable_but_forged_event(self) -> None:
        with (self.session / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": "forged", "seq": 2}) + "\n")
        with self.assertRaises(RecoveryError):
            recover_session(self.session)

    def test_undecodable_transaction_json_raises_typed_recovery_error(self) -> None:
        # _read_json's path.read_text(encoding="utf-8") raises
        # UnicodeDecodeError on non-UTF-8 bytes, which the old
        # `except (OSError, json.JSONDecodeError)` did not catch --
        # regression for that untyped-exception escape.
        (self.session / "transaction.json").write_bytes(b"\xff\xfe")
        with self.assertRaises(RecoveryError):
            recover_session(self.session)

    def test_undecodable_state_json_raises_typed_storage_error(self) -> None:
        # Same untyped-exception escape as above, in _load_state_unlocked
        # (path.read_text(encoding="utf-8") -> UnicodeDecodeError).
        (self.session / "state.json").write_bytes(b"\xff\xfe")
        with self.assertRaises(StorageError):
            load_state(self.session)

    def test_recovery_rejects_missing_state_json_instead_of_reporting_clean(self) -> None:
        # No transaction.json, no event.transaction.json, no state.next.json
        # pending -- but state.json itself is gone. Nothing in this WAL
        # protocol ever points a transaction at state.json's absence, so the
        # old code fell straight through to a false {"resolution": "clean"}.
        (self.session / "state.json").unlink()
        with self.assertRaises(RecoveryError):
            recover_session(self.session)

    def test_recovery_rejects_undecodable_state_json_instead_of_reporting_clean(self) -> None:
        (self.session / "state.json").write_bytes(b"\xff\xfe")
        with self.assertRaises(RecoveryError):
            recover_session(self.session)

    def test_recovery_sweeps_orphaned_atomic_write_tmp_files(self) -> None:
        # Simulates a hard crash inside _atomic_write_bytes_unlocked: the temp
        # file (f".{name}.{uuid4().hex}.tmp") was created but the process died
        # before the `except BaseException: temp.unlink(...)` cleanup could
        # run, so it is orphaned on disk forever unless recovery sweeps it.
        orphan1 = self.session / f".state.json.{uuid.uuid4().hex}.tmp"
        orphan2 = self.session / f".transaction.json.{uuid.uuid4().hex}.tmp"
        orphan1.write_bytes(b"partial")
        orphan2.write_bytes(b"partial")
        # Not the atomic-writer's exact pattern (no 32-char hex uuid segment)
        # -- must survive the sweep untouched.
        not_a_match = self.session / ".unrelated.tmp"
        not_a_match.write_text("keep me", encoding="utf-8")

        recovered = recover_session(self.session)

        self.assertEqual(recovered, {"resolution": "clean", "swept_tmp": 2})
        self.assertFalse(orphan1.exists())
        self.assertFalse(orphan2.exists())
        self.assertTrue(not_a_match.exists())

    def test_recovery_reports_zero_swept_tmp_when_nothing_orphaned(self) -> None:
        recovered = recover_session(self.session)
        self.assertEqual(recovered, {"resolution": "clean", "swept_tmp": 0})


if __name__ == "__main__":
    unittest.main()


class LockReleaseMaskingTests(unittest.TestCase):
    def test_body_exception_survives_broken_lock_release(self) -> None:
        import tempfile
        from pathlib import Path

        from research_harness.storage import LOCK_FILE, session_lock

        with tempfile.TemporaryDirectory() as tempdir:
            session = Path(tempdir)
            with self.assertRaises(ValueError):  # the body's error, not StorageError
                with session_lock(session):
                    (session / LOCK_FILE).unlink()  # sabotage the release path
                    raise ValueError("the real diagnosis")

    def test_clean_body_still_fails_loudly_on_broken_release(self) -> None:
        import tempfile
        from pathlib import Path

        from research_harness.storage import LOCK_FILE, StorageError, session_lock

        with tempfile.TemporaryDirectory() as tempdir:
            session = Path(tempdir)
            with self.assertRaises(StorageError):
                with session_lock(session):
                    (session / LOCK_FILE).unlink()
