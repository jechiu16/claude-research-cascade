"""Physical request permit accounting and attempt lifecycle enforcement."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .contracts import ACTION_CATEGORIES, contract_card_sha256
from .providers import preflight_contract_routes, provider_records_sha256
from .state import validate_state_document
from .storage import (
    _append_event_unlocked,
    _load_state_unlocked,
    _read_events_unlocked,
    _recover_session_unlocked,
    session_lock,
)


class QuotaError(RuntimeError):
    """Base quota failure."""


class QuotaExceeded(QuotaError):
    """The requested permit is outside the confirmed stage or category envelope."""


class ContractNotConfirmed(QuotaError):
    """The canonical state does not contain a valid user confirmation."""


class DuplicateAction(QuotaError):
    """An action ID was already reserved."""


class InvalidAttemptTransition(QuotaError):
    """An attempt status transition is not allowed."""


def _snapshot_registry(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "providers": state.get("capabilities", {}).get("providers", []),
    }


def _assert_confirmed_and_bound(state: dict[str, Any]) -> None:
    contract = state.get("contract", {})
    confirmation = contract.get("confirmation", {}) if isinstance(contract, dict) else {}
    if confirmation.get("confirmed_by") != "user" or not confirmation.get("confirmed_at"):
        raise ContractNotConfirmed("contract is not user-confirmed")
    capabilities = state.get("capabilities", {})
    if confirmation.get("card_sha256") != contract_card_sha256(contract):
        raise ContractNotConfirmed("confirmed card hash does not match contract")
    if confirmation.get("registry_sha256") != capabilities.get("registry_sha256"):
        raise ContractNotConfirmed("confirmed registry hash does not match state")
    providers = capabilities.get("providers", [])
    if confirmation.get("referenced_records_sha256") != provider_records_sha256(providers):
        raise ContractNotConfirmed("confirmed provider records do not match state")
    state_errors = validate_state_document(state)
    if state_errors:
        raise QuotaExceeded("invalid canonical state: " + "; ".join(state_errors))
    _, preflight_errors = preflight_contract_routes(contract, _snapshot_registry(state), os.environ)
    if preflight_errors:
        raise QuotaExceeded("route preflight failed: " + "; ".join(preflight_errors))


def _permit_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("event") == "permit_acquired"]


def _usage_from_events(events: list[dict[str, Any]]) -> dict[str, int]:
    usage = {category: 0 for category in ACTION_CATEGORIES}
    for event in _permit_events(events):
        category = event.get("category")
        count = event.get("count")
        if category in usage and isinstance(count, int) and not isinstance(count, bool) and count > 0:
            usage[category] += count
    return usage


def permit_usage(session_dir: Path) -> dict[str, int]:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise QuotaError("event history is malformed")
        return _usage_from_events(events)


def acquire_permits(
    session_dir: Path,
    action_id: str,
    stage: str,
    category: str,
    route: str,
    count: int,
    fingerprint: str,
    now: str,
) -> list[dict[str, Any]]:
    """Reserve `count` physical requests for one action, or raise.

    Unlike `new_state`/`execute_probe`, the confirmed-and-bound preflight
    here (`_assert_confirmed_and_bound`) reads the live `os.environ`
    directly and takes no `environ` override — standalone scripts and tests
    that need a different environment must set `os.environ` itself.
    """

    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        _assert_confirmed_and_bound(state)
        if not isinstance(action_id, str) or not action_id:
            raise QuotaExceeded("action_id must be a non-empty string")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise QuotaExceeded("permit count must be a positive integer")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise QuotaExceeded("fingerprint must be a non-empty string")
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise QuotaError("event history is malformed")
        permits = _permit_events(events)
        if any(event.get("action_id") == action_id for event in permits):
            raise DuplicateAction(f"action {action_id} already exists")

        mappings = [
            mapping
            for mapping in state["contract"]["stage_permit_map"]
            if mapping.get("stage") == stage
            and mapping.get("category") == category
            and mapping.get("route") == route
        ]
        if len(mappings) != 1:
            raise QuotaExceeded(f"no exact stage mapping for {stage}/{category}/{route}")
        mapping = mappings[0]
        provider = next(
            (provider for provider in state["capabilities"]["providers"] if provider.get("id") == route),
            None,
        )
        if provider is None or not provider.get("enabled"):
            raise QuotaExceeded(f"route {route} is not enabled")
        multiplicity = provider.get("request_multiplicity", {}).get(category)
        if count != multiplicity:
            raise QuotaExceeded(f"route {route} requires {multiplicity} physical requests per invocation")

        matching = [
            event
            for event in permits
            if event.get("stage") == stage
            and event.get("category") == category
            and event.get("route") == route
        ]
        if len(matching) >= mapping["invocations"]:
            raise QuotaExceeded(f"stage invocation capacity exhausted for {stage}/{category}/{route}")
        used_for_mapping = sum(event["count"] for event in matching)
        if used_for_mapping + count > mapping["count"]:
            raise QuotaExceeded(f"stage request capacity exhausted for {stage}/{category}/{route}")
        usage = _usage_from_events(events)
        ceiling = state["contract"]["resource_envelope"]["physical_ceiling"][category]
        if usage[category] + count > ceiling:
            raise QuotaExceeded(f"physical ceiling exhausted for {category}")

        event = _append_event_unlocked(
            session_dir,
            {
                "event": "permit_acquired",
                "at": now,
                "action_id": action_id,
                "stage": stage,
                "category": category,
                "route": route,
                "invocation_index": len(matching) + 1,
                "count": count,
                "fingerprint": fingerprint,
            },
        )
        return [
            {
                "action_id": action_id,
                "permit_index": index + 1,
                "category": category,
                "route": route,
                "event_hash": event["event_hash"],
            }
            for index in range(count)
        ]


# Keys are the CURRENT status; values are the statuses a transition may
# move TO from there (from_status -> {allowed to_status, ...}).
#
# "uncertain" is reached two ways: attempted -> uncertain (sync timeout-
# after-send, or an async submit/poll transport timeout — never retried,
# ambiguous whether the provider processed it) and accepted -> uncertain
# (async wall-clock exhaustion: execute_deep_timeout, no physical request).
# In both cases the permit stays consumed; nothing here refunds.
#
# uncertain -> accepted is the resume transition: the ONLY way out of
# uncertain. It is journaled with details {"resume": true} by
# execute_deep_poll itself (there is no separate resume verb) the moment a
# poll is attempted against an uncertain deep action, then normal polling
# continues under a freshly acquired transport permit.
ATTEMPT_TRANSITIONS = {
    "acquired": {"attempted"},
    "attempted": {"accepted", "failed", "uncertain"},
    "accepted": {"completed", "failed", "interrupted", "uncertain"},
    "interrupted": {"completed", "failed"},
    "uncertain": {"accepted"},
}


def _record_attempt_status_unlocked(
    session_dir: Path,
    action_id: str,
    status: str,
    now: str,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Append one attempt transition. Caller holds the session lock."""

    events, errors = _read_events_unlocked(session_dir)
    if errors:
        raise QuotaError("event history is malformed")
    if not any(
        event.get("event") == "permit_acquired" and event.get("action_id") == action_id
        for event in events
    ):
        raise InvalidAttemptTransition(f"unknown action {action_id}")
    statuses = [
        event["status"]
        for event in events
        if event.get("event") == "attempt_status" and event.get("action_id") == action_id
    ]
    current = statuses[-1] if statuses else "acquired"
    if status not in ATTEMPT_TRANSITIONS.get(current, set()):
        raise InvalidAttemptTransition(f"cannot transition action {action_id} from {current} to {status}")
    event: dict[str, Any] = {
        "event": "attempt_status",
        "at": now,
        "action_id": action_id,
        "from_status": current,
        "status": status,
    }
    if details is not None:
        if not isinstance(details, dict):
            raise InvalidAttemptTransition("attempt details must be an object")
        event["details"] = details
    return _append_event_unlocked(session_dir, event)


def record_attempt_status(
    session_dir: Path,
    action_id: str,
    status: str,
    now: str,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        return _record_attempt_status_unlocked(session_dir, action_id, status, now, details)
