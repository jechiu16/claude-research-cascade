"""Physical request permit accounting and attempt lifecycle enforcement."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from .contracts import ACTION_CATEGORIES, METERED_CATEGORIES, contract_card_sha256
from .providers import action_cost_class, preflight_contract_routes, provider_records_sha256
from .state import CONTRACT_SEMANTICS_V3, validate_state_document
from .storage import (
    _append_event_unlocked,
    _load_state_unlocked,
    _read_events_unlocked,
    _recover_session_unlocked,
    session_lock,
)


# Same shape as artifacts.ARTIFACT_ID_RE. Lives here (not in ._canon, which is
# scoped to hash-affecting canonical-form primitives, not identifier shape)
# because this module is where action_id is first minted and reserved
# (acquire_permits below is the sole writer of permit_acquired events).
# boundary.py and artifacts.py both key filesystem paths off action_id
# (provider_spool/<action_id>.raw.json); rejecting the shape here, at
# reservation time, is what keeps every downstream permit-gated consumer
# (execute_probe/execute_deep_submit/execute_deep_poll/_spool_raw) from ever
# seeing a path-traversal action_id. artifacts.promote_provider_payload reads
# action_id from a retrieval occurrence instead of a permit (occurrences can
# be patched directly), so it independently re-checks this same pattern.
ACTION_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
HASH64_RE = re.compile(r"^[0-9a-f]{64}$")
BOUNDARY_CATEGORIES = frozenset({"probe", "deep", "transport"})


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


def _cost_usage_from_events(
    events: list[dict[str, Any]], providers: list[dict[str, Any]]
) -> dict[str, int]:
    by_id = {provider.get("id"): provider for provider in providers if isinstance(provider, dict)}
    usage = {"deep": 0, "search": 0, "free": 0}
    for event in _permit_events(events):
        provider = by_id.get(event.get("route"))
        count = event.get("count")
        if provider is None or not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            continue
        cost_class = action_cost_class(provider, str(event.get("category")))
        if cost_class in usage:
            usage[cost_class] += count
    return usage


def cost_usage(session_dir: Path) -> dict[str, int]:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise QuotaError("event history is malformed")
        return _cost_usage_from_events(events, state.get("capabilities", {}).get("providers", []))


def _assert_cost_budget(
    session_dir: Path,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    provider: dict[str, Any],
    category: str,
    count: int,
    now: str,
) -> None:
    budget = state.get("contract", {}).get("resource_envelope", {}).get("cost_budget")
    if not isinstance(budget, dict):
        return
    cost_class = action_cost_class(provider, category)
    if cost_class == "free":
        return
    ceiling = budget.get(cost_class)
    usage = _cost_usage_from_events(
        events, state.get("capabilities", {}).get("providers", [])
    )
    if not isinstance(ceiling, int) or isinstance(ceiling, bool) or usage[cost_class] + count > ceiling:
        if not any(
            event.get("event") == "budget_exhausted" and event.get("cost_class") == cost_class
            for event in events
        ):
            _append_event_unlocked(
                session_dir,
                {
                    "event": "budget_exhausted",
                    "at": now,
                    "cost_class": cost_class,
                    "used": usage[cost_class],
                    "ceiling": ceiling,
                    "rejected_route": provider.get("id"),
                    "rejected_category": category,
                },
            )
        raise QuotaExceeded(f"cost budget exhausted for {cost_class}")


def acquire_permits(
    session_dir: Path,
    action_id: str,
    stage: str,
    category: str,
    route: str,
    count: int,
    now: str,
) -> list[dict[str, Any]]:
    """Reserve a legacy non-boundary action, or raise.

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
        if not isinstance(action_id, str) or ACTION_ID_RE.fullmatch(action_id) is None:
            raise QuotaExceeded(
                "action_id must match ^[A-Za-z][A-Za-z0-9_-]{0,63}$ (non-empty, no path separators)"
            )
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise QuotaExceeded("permit count must be a positive integer")
        if category in METERED_CATEGORIES:
            raise QuotaExceeded(
                f"{category} actions require an implemented request boundary"
            )
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
        _assert_cost_budget(session_dir, state, events, provider, category, count, now)
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

        return _append_permit_unlocked(
            session_dir, action_id, stage, category, route, count,
            len(matching) + 1, now,
        )


def _append_permit_unlocked(
    session_dir: Path,
    action_id: str,
    stage: str,
    category: str,
    route: str,
    count: int,
    invocation_index: int,
    now: str,
    *,
    fingerprint: Optional[str] = None,
    initial_status: Optional[str] = None,
    query_hash: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Append one permit event after quota checks have passed."""

    if category in BOUNDARY_CATEGORIES:
        if initial_status != "attempted":
            raise QuotaExceeded("boundary permits must start with initial_status=attempted")
        if not isinstance(fingerprint, str) or HASH64_RE.fullmatch(fingerprint) is None:
            raise QuotaExceeded("boundary fingerprint must be 64 lowercase hex characters")
        if category in {"probe", "deep"}:
            if not isinstance(query_hash, str) or HASH64_RE.fullmatch(query_hash) is None:
                raise QuotaExceeded("probe/deep query_hash must be 64 lowercase hex characters")
        elif query_hash is not None:
            raise QuotaExceeded("non-deep boundary actions cannot carry query_hash")
    elif category in METERED_CATEGORIES:
        raise QuotaExceeded(f"{category} actions require an implemented request boundary")
    elif (
        initial_status is not None
        or fingerprint is not None
        or query_hash is not None
    ):
        raise QuotaExceeded("legacy permits cannot carry boundary-only fields")

    event_data: dict[str, Any] = {
        "event": "permit_acquired",
        "at": now,
        "action_id": action_id,
        "stage": stage,
        "category": category,
        "route": route,
        "invocation_index": invocation_index,
        "count": count,
    }
    if fingerprint is not None:
        event_data["fingerprint"] = fingerprint
    if initial_status is not None:
        event_data["initial_status"] = initial_status
    if query_hash is not None:
        event_data["query_hash"] = query_hash
    event = _append_event_unlocked(session_dir, event_data)
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


def _reserve_boundary_action_unlocked(
    session_dir: Path,
    action_id: str,
    stage: str,
    category: str,
    route: str,
    count: int,
    fingerprint: str,
    now: str,
    *,
    query_hash: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Reserve a boundary request and mark it attempted in one journal event.

    The caller must hold the session lock and must have already built the
    actual RequestSpec. This function deliberately has no public caller path.
    """

    if category not in BOUNDARY_CATEGORIES:
        raise QuotaExceeded(f"{category} is not a boundary-managed category")
    if not isinstance(action_id, str) or ACTION_ID_RE.fullmatch(action_id) is None:
        raise QuotaExceeded(
            "action_id must match ^[A-Za-z][A-Za-z0-9_-]{0,63}$ (non-empty, no path separators)"
        )
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise QuotaExceeded("permit count must be a positive integer")
    if not isinstance(fingerprint, str) or HASH64_RE.fullmatch(fingerprint) is None:
        raise QuotaExceeded("boundary fingerprint must be 64 lowercase hex characters")
    if category in {"probe", "deep"}:
        if not isinstance(query_hash, str) or HASH64_RE.fullmatch(query_hash) is None:
            raise QuotaExceeded("probe/deep query_hash must be 64 lowercase hex characters")
    elif query_hash is not None:
        raise QuotaExceeded("non-deep boundary actions cannot carry query_hash")
    state = _load_state_unlocked(session_dir)
    if state.get("session", {}).get("contract_semantics") != CONTRACT_SEMANTICS_V3:
        raise QuotaExceeded(f"boundary actions require contract_semantics={CONTRACT_SEMANTICS_V3}")
    _assert_confirmed_and_bound(state)
    events, errors = _read_events_unlocked(session_dir)
    if errors:
        raise QuotaError("event history is malformed")
    permits = _permit_events(events)
    if any(event.get("action_id") == action_id for event in permits):
        raise DuplicateAction(f"action {action_id} already exists")
    mappings = [
        mapping for mapping in state["contract"]["stage_permit_map"]
        if mapping.get("stage") == stage
        and mapping.get("category") == category
        and mapping.get("route") == route
    ]
    if len(mappings) != 1:
        raise QuotaExceeded(f"no exact stage mapping for {stage}/{category}/{route}")
    matching = [
        event for event in permits
        if event.get("stage") == stage
        and event.get("category") == category
        and event.get("route") == route
    ]
    mapping = mappings[0]
    if len(matching) >= mapping["invocations"]:
        raise QuotaExceeded(f"stage invocation capacity exhausted for {stage}/{category}/{route}")
    used_for_mapping = sum(event["count"] for event in matching)
    if used_for_mapping + count > mapping["count"]:
        raise QuotaExceeded(f"stage request capacity exhausted for {stage}/{category}/{route}")
    usage = _usage_from_events(events)
    ceiling = state["contract"]["resource_envelope"]["physical_ceiling"][category]
    if usage[category] + count > ceiling:
        raise QuotaExceeded(f"physical ceiling exhausted for {category}")
    provider = next(
        (provider for provider in state["capabilities"]["providers"] if provider.get("id") == route),
        None,
    )
    if provider is None or provider.get("enabled") is not True:
        raise QuotaExceeded(f"route {route} is not enabled")
    _assert_cost_budget(session_dir, state, events, provider, category, count, now)
    multiplicity = provider.get("request_multiplicity", {}).get(category)
    if count != multiplicity:
        raise QuotaExceeded(f"route {route} requires {multiplicity} physical requests per invocation")
    return _append_permit_unlocked(
        session_dir,
        action_id,
        stage,
        category,
        route,
        count,
        len(matching) + 1,
        now,
        fingerprint=fingerprint,
        initial_status="attempted",
        query_hash=query_hash,
    )


# Keys are the CURRENT status; values are the statuses a transition may
# move TO from there (from_status -> {allowed to_status, ...}).
#
# "uncertain" is reached two ways: attempted -> uncertain (sync timeout-
# after-send, or an async submit/poll transport timeout — never retried,
# ambiguous whether the provider processed it) and accepted -> uncertain
# (async wall-clock exhaustion: execute_deep_timeout, no physical request).
# In both cases the boundary action/request count stays consumed; nothing here refunds.
#
# uncertain -> accepted is the resume transition: the ONLY way out of
# uncertain. It is journaled with details {"resume": true} by
# execute_deep_poll itself (there is no separate resume verb) the moment a
# poll is attempted against an uncertain deep action, then normal polling
# continues under a newly reserved boundary transport action.
ATTEMPT_TRANSITIONS = {
    "acquired": {"attempted"},
    "attempted": {"accepted", "failed", "uncertain"},
    "accepted": {"completed", "failed", "uncertain"},
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
    permit = next(
        event for event in events
        if event.get("event") == "permit_acquired" and event.get("action_id") == action_id
    )
    statuses = [
        event["status"]
        for event in events
        if event.get("event") == "attempt_status" and event.get("action_id") == action_id
    ]
    current = statuses[-1] if statuses else permit.get("initial_status", "acquired")
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
