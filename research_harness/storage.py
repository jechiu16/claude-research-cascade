"""Crash-consistent session state and append-only operational events."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import socket
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from ._canon import canonical_json as _canonical_json, sha256_hex
from .state import state_sha256, validate_state_document


STATE_FILE = "state.json"
EVENTS_FILE = "events.jsonl"
STATE_NEXT_FILE = "state.next.json"
STATE_TRANSACTION_FILE = "transaction.json"
EVENT_TRANSACTION_FILE = "event.transaction.json"
LOCK_FILE = ".session.lock"

# _atomic_write_bytes_unlocked names its scratch file
# f".{path.name}.{uuid.uuid4().hex}.tmp" next to the real target. Its
# `except BaseException: temp.unlink(missing_ok=True)` cleanup never runs on
# a hard kill (SIGKILL, power loss), which orphans that file forever. This
# pattern is what the clean-path recovery sweep matches -- deliberately
# strict (a 32-char lowercase hex uuid segment) so it never touches an
# unrelated dotfile a caller might have dropped in the session directory.
_ORPHAN_TMP_PATTERN = re.compile(r"^\..+\.[0-9a-f]{32}\.tmp$")

ORGANIZER_ROOTS = frozenset(
    {
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
    }
)


class StorageError(RuntimeError):
    """Base storage failure."""


class RevisionConflict(StorageError):
    """The caller attempted to patch a stale state revision."""


class StateValidationError(StorageError):
    """A candidate state failed structural validation."""


class ProtectedStatePath(StorageError):
    """A patch attempted to modify a protected canonical section."""


class RecoveryError(StorageError):
    """Recovery could not prove a safe deterministic repair."""


class SessionLockTimeout(StorageError):
    """The session lock could not be acquired within the deadline."""


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _atomic_write_bytes_unlocked(path: Path, payload: bytes) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, path)
        _fsync_dir(path.parent)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _atomic_write_json_unlocked(path: Path, value: Any) -> None:
    _atomic_write_bytes_unlocked(path, _canonical_json(value) + b"\n")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"cannot read {path.name}: {exc}") from exc


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _break_stale_lock(lock_path: Path) -> bool:
    if lock_path.is_symlink():
        return False
    try:
        record = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if record.get("hostname") != socket.gethostname():
        return False
    pid = record.get("pid")
    if not isinstance(pid, int) or _pid_exists(pid):
        return False
    try:
        lock_path.unlink()
        _fsync_dir(lock_path.parent)
        return True
    except FileNotFoundError:
        return True


@contextmanager
def session_lock(session_dir: Path, timeout_s: float = 5.0) -> Iterator[None]:
    session_dir = Path(session_dir)
    if not session_dir.is_dir() or session_dir.is_symlink():
        raise StorageError("session directory must be an existing non-symlink directory")
    lock_path = session_dir / LOCK_FILE
    token = uuid.uuid4().hex
    record = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "acquired_at_unix": time.time(),
        "token": token,
    }
    payload = _canonical_json(record) + b"\n"
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if _break_stale_lock(lock_path):
                continue
            if time.monotonic() >= deadline:
                raise SessionLockTimeout(f"timed out acquiring {lock_path}")
            time.sleep(0.025)
            continue
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(session_dir)
        break
    def _release() -> None:
        try:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise StorageError("session lock disappeared before release")
        if current.get("token") != token:
            raise StorageError("session lock ownership changed unexpectedly")
        lock_path.unlink()
        _fsync_dir(session_dir)

    try:
        yield
    except BaseException:
        # The body's exception is the diagnosis; a broken release must not
        # replace it. Best-effort unlock, then re-raise the original.
        try:
            _release()
        except Exception:
            pass
        raise
    _release()


def _load_state_unlocked(session_dir: Path) -> dict[str, Any]:
    path = Path(session_dir) / STATE_FILE
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageError(f"cannot load state.json: {exc}") from exc
    if not isinstance(value, dict):
        raise StorageError("state.json must contain an object")
    return value


def load_state(session_dir: Path) -> dict[str, Any]:
    return _load_state_unlocked(Path(session_dir))


def _events_bytes(session_dir: Path) -> bytes:
    path = Path(session_dir) / EVENTS_FILE
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return b""


def _read_events_unlocked(session_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    payload = _events_bytes(session_dir)
    if not payload:
        return [], []
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    lines = payload.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for index, line in enumerate(lines, start=1):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"events.jsonl:{index} invalid JSON")
            continue
        if not isinstance(value, dict):
            errors.append(f"events.jsonl:{index} must be an object")
            continue
        events.append(value)
    return events, errors


def read_events(session_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    return _read_events_unlocked(Path(session_dir))


def _event_hash(event_without_hash: dict[str, Any]) -> str:
    return sha256_hex(event_without_hash)


def _event_chain_errors(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    previous_hash: Optional[str] = None
    for expected_seq, event in enumerate(events, start=1):
        if event.get("seq") != expected_seq:
            errors.append(f"event {expected_seq} sequence mismatch")
        if event.get("prev_hash") != previous_hash:
            errors.append(f"event {expected_seq} previous hash mismatch")
        stored_hash = event.get("event_hash")
        unhashed = {key: value for key, value in event.items() if key != "event_hash"}
        if not isinstance(stored_hash, str) or stored_hash != _event_hash(unhashed):
            errors.append(f"event {expected_seq} hash mismatch")
        previous_hash = stored_hash if isinstance(stored_hash, str) else None
    return errors


def _prepare_event_unlocked(session_dir: Path, event: dict[str, Any]) -> tuple[dict[str, Any], bytes, int, str]:
    events, errors = _read_events_unlocked(session_dir)
    chain_errors = _event_chain_errors(events) if not errors else []
    if errors or chain_errors:
        raise RecoveryError("cannot append after malformed event history")
    prepared = copy.deepcopy(event)
    prepared.pop("event_hash", None)
    prepared["seq"] = len(events) + 1
    prepared["prev_hash"] = events[-1].get("event_hash") if events else None
    prepared["event_hash"] = _event_hash(prepared)
    line = _canonical_json(prepared) + b"\n"
    prefix = _events_bytes(session_dir)
    return prepared, line, len(prefix), hashlib.sha256(prefix).hexdigest()


def _append_bytes_unlocked(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def _remove_unlocked(path: Path) -> None:
    path.unlink(missing_ok=True)
    _fsync_dir(path.parent)


def _sweep_orphaned_tmp_unlocked(session_dir: Path) -> int:
    """Unlink hard-crash-orphaned atomic-writer scratch files.

    Only direct children of session_dir are considered (never recurses into
    raw/, which has its own unrelated .{artifact_id}.tmp convention for
    artifact payload staging) and only names matching the atomic writer's
    exact pattern are removed.
    """
    swept = 0
    for entry in session_dir.iterdir():
        if entry.is_file() and not entry.is_symlink() and _ORPHAN_TMP_PATTERN.match(entry.name):
            _remove_unlocked(entry)
            swept += 1
    return swept


def _append_prepared_event_unlocked(session_dir: Path, line: bytes) -> None:
    _append_bytes_unlocked(Path(session_dir) / EVENTS_FILE, line)


def _append_event_unlocked(session_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    session_dir = Path(session_dir)
    if (session_dir / EVENT_TRANSACTION_FILE).exists() or (session_dir / STATE_TRANSACTION_FILE).exists():
        raise RecoveryError("cannot append while a transaction is pending")
    prepared, line, boundary, prefix_hash = _prepare_event_unlocked(session_dir, event)
    transaction = {
        "kind": "event",
        "events_size_before": boundary,
        "events_prefix_sha256": prefix_hash,
        "event_line": line.decode("utf-8"),
        "event_hash": prepared["event_hash"],
    }
    _atomic_write_json_unlocked(session_dir / EVENT_TRANSACTION_FILE, transaction)
    _append_prepared_event_unlocked(session_dir, line)
    _remove_unlocked(session_dir / EVENT_TRANSACTION_FILE)
    return prepared


def _verify_prefix(payload: bytes, boundary: int, expected_hash: str) -> None:
    if not isinstance(boundary, int) or isinstance(boundary, bool) or boundary < 0:
        raise RecoveryError("event transaction boundary is malformed")
    if not isinstance(expected_hash, str):
        raise RecoveryError("event transaction prefix hash is malformed")
    if len(payload) < boundary:
        raise RecoveryError("event history is shorter than transaction boundary")
    if hashlib.sha256(payload[:boundary]).hexdigest() != expected_hash:
        raise RecoveryError("event history changed before transaction boundary")


def _recover_event_payload_unlocked(session_dir: Path, transaction: dict[str, Any]) -> bool:
    try:
        boundary = transaction["events_size_before"]
        prefix_hash = transaction["events_prefix_sha256"]
        line = transaction["event_line"].encode("utf-8")
        expected_event_hash = transaction["event_hash"]
    except (KeyError, AttributeError) as exc:
        raise RecoveryError("event transaction is malformed") from exc
    if not isinstance(boundary, int) or not isinstance(prefix_hash, str):
        raise RecoveryError("event transaction boundary is malformed")
    try:
        event = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError("event transaction line is malformed") from exc
    if not line.endswith(b"\n") or not isinstance(event, dict):
        raise RecoveryError("event transaction line is malformed")
    stored_event_hash = event.get("event_hash")
    unhashed = {key: value for key, value in event.items() if key != "event_hash"}
    if (
        not isinstance(expected_event_hash, str)
        or stored_event_hash != expected_event_hash
        or stored_event_hash != _event_hash(unhashed)
    ):
        raise RecoveryError("event transaction hash is invalid")
    payload = _events_bytes(session_dir)
    _verify_prefix(payload, boundary, prefix_hash)
    tail = payload[boundary:]
    if tail == line:
        return False
    if not line.startswith(tail):
        raise RecoveryError("event tail is not owned by the pending transaction")
    events_path = session_dir / EVENTS_FILE
    fd = os.open(events_path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.ftruncate(fd, boundary)
        os.fsync(fd)
    finally:
        os.close(fd)
    _append_prepared_event_unlocked(session_dir, line)
    return True


def _recover_session_unlocked(session_dir: Path) -> dict[str, Any]:
    session_dir = Path(session_dir)
    state_tx_path = session_dir / STATE_TRANSACTION_FILE
    event_tx_path = session_dir / EVENT_TRANSACTION_FILE
    if state_tx_path.exists() and event_tx_path.exists():
        raise RecoveryError("state and event transactions cannot both be pending")
    if state_tx_path.exists():
        transaction = _read_json(state_tx_path)
        if not isinstance(transaction, dict) or transaction.get("kind") != "state":
            raise RecoveryError("state transaction is malformed")
        current_hash = state_sha256(_load_state_unlocked(session_dir))
        previous_hash = transaction.get("previous_state_sha256")
        next_hash = transaction.get("next_state_sha256")
        if current_hash == previous_hash:
            payload = _events_bytes(session_dir)
            _verify_prefix(
                payload,
                transaction.get("events_size_before"),
                transaction.get("events_prefix_sha256"),
            )
            if len(payload) != transaction["events_size_before"]:
                raise RecoveryError("event bytes changed before state replacement")
            _remove_unlocked(session_dir / STATE_NEXT_FILE)
            _remove_unlocked(state_tx_path)
            resolution = "rolled_back"
        elif current_hash == next_hash:
            _recover_event_payload_unlocked(session_dir, transaction)
            _remove_unlocked(session_dir / STATE_NEXT_FILE)
            _remove_unlocked(state_tx_path)
            resolution = "rolled_forward"
        else:
            raise RecoveryError("state hash matches neither side of pending transaction")
        events, errors = _read_events_unlocked(session_dir)
        if errors or _event_chain_errors(events):
            raise RecoveryError("event history remains malformed after state recovery")
        return {"resolution": resolution}
    if event_tx_path.exists():
        transaction = _read_json(event_tx_path)
        if not isinstance(transaction, dict) or transaction.get("kind") != "event":
            raise RecoveryError("event transaction is malformed")
        _recover_event_payload_unlocked(session_dir, transaction)
        _remove_unlocked(event_tx_path)
        events, errors = _read_events_unlocked(session_dir)
        if errors or _event_chain_errors(events):
            raise RecoveryError("event history remains malformed after event recovery")
        return {"resolution": "event_rolled_forward"}
    events, errors = _read_events_unlocked(session_dir)
    if errors or _event_chain_errors(events):
        raise RecoveryError("unowned malformed event history cannot be repaired")
    staged = session_dir / STATE_NEXT_FILE
    if staged.exists():
        _remove_unlocked(staged)
        return {"resolution": "discarded_uncommitted_state"}
    # No pending transaction and nothing staged is only "clean" if state.json
    # itself is actually there and readable -- a missing or undecodable
    # state.json is not something this WAL protocol tracks at all (no
    # transaction.json ever pointed at it), so it would otherwise fall
    # straight through to a false "clean" verdict.
    try:
        _load_state_unlocked(session_dir)
    except StorageError as exc:
        raise RecoveryError(f"state.json is missing or unreadable: {exc}") from exc
    swept_tmp = _sweep_orphaned_tmp_unlocked(session_dir)
    return {"resolution": "clean", "swept_tmp": swept_tmp}


def recover_session(session_dir: Path) -> dict[str, Any]:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        return _recover_session_unlocked(session_dir)


def create_session(session_dir: Path, state: dict[str, Any]) -> None:
    session_dir = Path(session_dir)
    errors = validate_state_document(state)
    if errors:
        raise StateValidationError("; ".join(errors))
    session_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    with session_lock(session_dir):
        _atomic_write_json_unlocked(session_dir / STATE_FILE, state)
        _append_event_unlocked(
            session_dir,
            {
                "event": "session_created",
                "at": state["session"]["created_at"],
                "session_id": state["session"]["id"],
                "revision": 0,
                "state_sha256": state_sha256(state),
            },
        )


def _decode_pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise StateValidationError("JSON Pointer path must start with /")
    if path == "/":
        return [""]
    return [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]


def _check_allowed_root(path: str, allowed_roots: frozenset[str]) -> None:
    tokens = _decode_pointer(path)
    if not tokens or tokens[0] not in allowed_roots:
        raise ProtectedStatePath(f"state path {path} is protected")


def _resolve_parent(document: Any, tokens: list[str]) -> tuple[Any, str]:
    current = document
    for token in tokens[:-1]:
        if isinstance(current, dict):
            if token not in current:
                raise StateValidationError(f"JSON Pointer segment {token} does not exist")
            current = current[token]
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise StateValidationError(f"JSON Pointer list segment {token} is invalid") from exc
        else:
            raise StateValidationError("JSON Pointer traverses a scalar")
    return current, tokens[-1]


def _apply_operation(document: dict[str, Any], operation: dict[str, Any]) -> None:
    if not isinstance(operation, dict):
        raise StateValidationError("patch operation must be an object")
    op = operation.get("op")
    if op not in {"add", "replace", "remove"}:
        raise StateValidationError(f"unsupported patch operation {op}")
    tokens = _decode_pointer(operation.get("path"))
    parent, token = _resolve_parent(document, tokens)
    if isinstance(parent, dict):
        if op in {"replace", "remove"} and token not in parent:
            raise StateValidationError(f"patch target {operation.get('path')} does not exist")
        if op == "remove":
            del parent[token]
        else:
            parent[token] = copy.deepcopy(operation.get("value"))
        return
    if isinstance(parent, list):
        if op == "add" and token == "-":
            parent.append(copy.deepcopy(operation.get("value")))
            return
        try:
            index = int(token)
        except ValueError as exc:
            raise StateValidationError(f"patch list index {token} is invalid") from exc
        if op == "add":
            if index < 0 or index > len(parent):
                raise StateValidationError(f"patch list index {index} is out of range")
            parent.insert(index, copy.deepcopy(operation.get("value")))
        elif op == "replace":
            if index < 0 or index >= len(parent):
                raise StateValidationError(f"patch list index {index} is out of range")
            parent[index] = copy.deepcopy(operation.get("value"))
        else:
            if index < 0 or index >= len(parent):
                raise StateValidationError(f"patch list index {index} is out of range")
            del parent[index]
        return
    raise StateValidationError("patch target parent is a scalar")


def _replace_state_unlocked(session_dir: Path) -> None:
    os.replace(session_dir / STATE_NEXT_FILE, session_dir / STATE_FILE)
    _fsync_dir(session_dir)


def _commit_patch_unlocked(
    session_dir: Path,
    operations: list[dict[str, Any]],
    expected_revision: int,
    now: str,
    allowed_roots: frozenset[str],
    transition_kind: str,
) -> dict[str, Any]:
    current = _load_state_unlocked(session_dir)
    revision = current.get("session", {}).get("revision")
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
        raise RevisionConflict("expected revision must be a non-negative integer")
    if revision != expected_revision:
        raise RevisionConflict(f"expected revision {expected_revision}, found {revision}")
    for operation in operations:
        _check_allowed_root(operation.get("path") if isinstance(operation, dict) else "", allowed_roots)
    candidate = copy.deepcopy(current)
    for operation in operations:
        _apply_operation(candidate, operation)
    candidate["session"]["revision"] = revision + 1
    candidate["session"]["updated_at"] = now
    errors = validate_state_document(candidate)
    if errors:
        raise StateValidationError("; ".join(errors))

    previous_hash = state_sha256(current)
    next_hash = state_sha256(candidate)
    patch_hash = sha256_hex(operations)
    prepared, line, boundary, prefix_hash = _prepare_event_unlocked(
        session_dir,
        {
            "event": "state_revision",
            "at": now,
            "transition_kind": transition_kind,
            "revision": revision + 1,
            "previous_state_sha256": previous_hash,
            "new_state_sha256": next_hash,
            "patch_sha256": patch_hash,
        },
    )
    _atomic_write_json_unlocked(session_dir / STATE_NEXT_FILE, candidate)
    transaction = {
        "kind": "state",
        "previous_state_sha256": previous_hash,
        "next_state_sha256": next_hash,
        "patch_sha256": patch_hash,
        "revision": revision + 1,
        "events_size_before": boundary,
        "events_prefix_sha256": prefix_hash,
        "event_line": line.decode("utf-8"),
        "event_hash": prepared["event_hash"],
    }
    _atomic_write_json_unlocked(session_dir / STATE_TRANSACTION_FILE, transaction)
    _replace_state_unlocked(session_dir)
    _append_prepared_event_unlocked(session_dir, line)
    _remove_unlocked(session_dir / STATE_TRANSACTION_FILE)
    return candidate


def apply_state_patch(
    session_dir: Path,
    operations: list[dict[str, Any]],
    expected_revision: int,
    now: str,
) -> dict[str, Any]:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        return _commit_patch_unlocked(
            session_dir,
            operations,
            expected_revision,
            now,
            ORGANIZER_ROOTS,
            "organizer",
        )


# Boundary-authored writes: the request boundary records retrieval occurrences
# itself (code provenance, not Organizer prose), so its patches carry their own
# transition kind and a deliberately narrow root allowlist.
BOUNDARY_ROOTS = frozenset({"retrieval_occurrences"})


def _apply_boundary_patch_unlocked(
    session_dir: Path,
    operations: list[dict[str, Any]],
    expected_revision: int,
    now: str,
) -> dict[str, Any]:
    return _commit_patch_unlocked(
        Path(session_dir),
        operations,
        expected_revision,
        now,
        BOUNDARY_ROOTS,
        "boundary:occurrence",
    )


def _apply_artifact_state_patch_unlocked(
    session_dir: Path,
    transition_kind: str,
    operations: list[dict[str, Any]],
    expected_revision: int,
    now: str,
) -> dict[str, Any]:
    allowed_by_kind = {
        "ingest": frozenset({"artifact_index"}),
        "purge_pending": frozenset({"artifact_index", "claims", "summary"}),
        "purge_tombstone": frozenset({"artifact_index"}),
    }
    allowed = allowed_by_kind.get(transition_kind)
    if allowed is None:
        raise ProtectedStatePath(f"unknown artifact transition {transition_kind}")
    if transition_kind in {"purge_pending", "purge_tombstone"}:
        for operation in operations:
            path = operation.get("path", "") if isinstance(operation, dict) else ""
            if path.startswith("/summary/") and path != "/summary/status":
                raise ProtectedStatePath(f"artifact transition cannot modify {path}")
    return _commit_patch_unlocked(
        Path(session_dir),
        operations,
        expected_revision,
        now,
        allowed,
        f"artifact:{transition_kind}",
    )
