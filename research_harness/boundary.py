"""v2 request boundary: turn one acquired permit into one physical request.

Schema status: LOCKED v1 (2026-07-11). The occurrence shape and the adapter
protocol (sync build/parse; async submit/job_token/poll/extract) below are
stable — they have been exercised by three request shapes (sync GET, sync
POST, async submit/poll) across 12 live routes with fail-closed validators
and typed failure modes. Breaking changes require a version bump and a
migration note, not a silent field-list edit.

Design rules (from the v2 decisions ledger):

- One permit, one physical request. A failed or uncertain attempt consumes the
  permit; nothing here refunds anything.
- Raw provider output is preserved verbatim in the session's provider spool
  before any parsing — parse failures never destroy paid bytes.
- The boundary writes retrieval occurrences itself (code provenance). Search
  occurrences are not canonical sources and never support claims directly; the
  Organizer promotes and fetches sources separately.
- Credentials never enter state, events, spool filenames, or fingerprints.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from ._canon import sha256_hex
from .quota import _record_attempt_status_unlocked
from .storage import (
    _apply_boundary_patch_unlocked,
    _atomic_write_bytes_unlocked,
    _load_state_unlocked,
    _read_events_unlocked,
    _recover_session_unlocked,
    session_lock,
)

SPOOL_DIR = "provider_spool"
SYNTHESIS_EXCERPT_LIMIT = 4000
CITATION_LIMIT = 40


class BoundaryError(RuntimeError):
    """The boundary refused or failed to execute a physical request."""


class AdapterParseError(BoundaryError):
    """The provider responded, but the payload does not match the adapter contract."""


class AdapterTerminalFailure(BoundaryError):
    """An async job reached a well-formed provider-reported terminal failure.

    Distinct from AdapterParseError: the payload is NOT malformed (the
    provider clearly says the job failed), so the boundary can confidently
    fail the deep action instead of leaving it harvestable.
    """


@dataclass(frozen=True)
class RequestSpec:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes
    timeout_s: float
    fingerprint_url: Optional[str] = None


@dataclass(frozen=True)
class ParsedResult:
    synthesis_text: str
    citations: list[dict[str, Any]]
    cost_usd: Optional[float]
    usage: dict[str, Any]
    model: str
    kind: str = "search_synthesis"  # search_synthesis / result_listing / paper_listing / record_fetch


def _adapters() -> dict[str, dict[str, Any]]:
    # Function-level import: adapter modules import RequestSpec/ParsedResult
    # from this module, so the registry loads lazily to break the cycle.
    from .adapters import ADAPTERS

    return ADAPTERS


# ── Transport ────────────────────────────────────────────────────────────────

Transport = Callable[[RequestSpec], tuple[int, bytes]]


def _request_fingerprint(spec: RequestSpec) -> str:
    """Hash semantic request bytes while excluding credential-bearing URL parts."""

    return sha256_hex(
        {
            "method": spec.method.upper(),
            "url": spec.fingerprint_url or spec.url,
            "body": spec.body.decode("utf-8"),
        }
    )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_transport(spec: RequestSpec) -> tuple[int, bytes]:
    # body=b"" means "no body": pass None so a GET stays truly bodyless
    # (data=b"" would still attach Content-Length/Content-Type headers).
    request = urllib.request.Request(
        spec.url, data=spec.body or None, headers=spec.headers, method=spec.method
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=spec.timeout_s) as response:
        return response.status, response.read()


# ── Execution ────────────────────────────────────────────────────────────────


def _spool_raw(session_dir: Path, action_id: str, payload: bytes) -> Path:
    spool = session_dir / SPOOL_DIR
    if spool.exists():
        if spool.is_symlink() or not spool.is_dir():
            raise BoundaryError("provider spool path is not a safe directory")
    else:
        spool.mkdir(mode=0o700)
    path = spool / f"{action_id}.raw.json"
    _atomic_write_bytes_unlocked(path, payload)
    return path


def _permit_for(events: list[dict[str, Any]], action_id: str) -> dict[str, Any]:
    """Look up a FRESH permit: acquired exactly once, never yet attempted.

    Used for actions about to make their first physical request: a probe, a
    deep submit, or one poll's transport permit. Not for the deep action on a
    poll call, which is deliberately re-attempted across many polls — see
    _deep_action_lookup.
    """

    permits = [
        event
        for event in events
        if event.get("event") == "permit_acquired" and event.get("action_id") == action_id
    ]
    if len(permits) != 1:
        raise BoundaryError(f"action {action_id} has no unique acquired permit")
    statuses = [
        event
        for event in events
        if event.get("event") == "attempt_status" and event.get("action_id") == action_id
    ]
    if statuses:
        raise BoundaryError(f"action {action_id} was already attempted")
    return permits[0]


def _deep_action_lookup(events: list[dict[str, Any]], action_id: str) -> tuple[dict[str, Any], str]:
    """Look up an already-submitted deep action and its current attempt status.

    Unlike _permit_for, this requires the action to already carry at least
    one attempt_status event (it must have gone through execute_deep_submit),
    and returns the latest status instead of refusing a re-visit — a deep
    action is legitimately revisited by every poll and by deep-timeout.
    """

    permits = [
        event
        for event in events
        if event.get("event") == "permit_acquired" and event.get("action_id") == action_id
    ]
    if len(permits) != 1:
        raise BoundaryError(f"action {action_id} has no unique acquired permit")
    statuses = [
        event["status"]
        for event in events
        if event.get("event") == "attempt_status" and event.get("action_id") == action_id
    ]
    if not statuses:
        raise BoundaryError(f"action {action_id} has not been submitted yet")
    return permits[0], statuses[-1]


def _job_token_for(events: list[dict[str, Any]], action_id: str) -> str:
    """Recover the bare provider-native job token from the ORIGINAL submit's
    accepted event (details {"job": "provider:token"}). A resume's accepted
    event carries {"resume": true} instead of "job", so the first match here
    is always the original submission regardless of how many times the
    action has since been resumed."""

    for event in events:
        if (
            event.get("event") == "attempt_status"
            and event.get("action_id") == action_id
            and event.get("status") == "accepted"
        ):
            details = event.get("details") or {}
            job = details.get("job")
            if isinstance(job, str) and ":" in job:
                return job.partition(":")[2]
    raise BoundaryError(f"deep action {action_id} has no recorded job token")


def _deep_query_hash(events: list[dict[str, Any]], action_id: str) -> str:
    """Recover the query hash journaled at submit time (the "attempted" event
    happens exactly once per deep action, so this is unambiguous)."""

    for event in events:
        if (
            event.get("event") == "attempt_status"
            and event.get("action_id") == action_id
            and event.get("status") == "attempted"
        ):
            details = event.get("details") or {}
            query_hash = details.get("query_hash")
            if isinstance(query_hash, str) and query_hash:
                return query_hash
    raise BoundaryError(f"deep action {action_id} has no recorded query hash")


def _first_status_at(events: list[dict[str, Any]], action_id: str, status: str) -> str:
    for event in events:
        if (
            event.get("event") == "attempt_status"
            and event.get("action_id") == action_id
            and event.get("status") == status
        ):
            at = event.get("at")
            if isinstance(at, str) and at:
                return at
    raise BoundaryError(f"action {action_id} has no {status} event")


def _parse_timestamp(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise BoundaryError(f"timestamp is not ISO-8601: {value!r}") from exc


def _elapsed_seconds(earlier: str, later: str) -> float:
    return (_parse_timestamp(later) - _parse_timestamp(earlier)).total_seconds()


def _bound_route(state: dict[str, Any], route: str, *, mode: str) -> dict[str, Any]:
    """Resolve and bind a route, refusing any transport-mode mismatch.

    `mode` is "sync" for execute_probe or "async" for the deep submit/poll
    path. A route whose registry transport.mode disagrees is refused here —
    this is the one place that keeps the sync and async boundaries from
    silently cross-wiring (an async-only adapter used as if it returned a
    result inline, or vice versa).
    """

    provider = next(
        (item for item in state["capabilities"]["providers"] if item.get("id") == route),
        None,
    )
    if provider is None or provider.get("enabled") is not True:
        raise BoundaryError(f"route {route} is not enabled in the capability snapshot")
    binding = provider.get("execution_binding")
    if binding not in {"v2_request_boundary", "no_network_demo"}:
        raise BoundaryError(f"route {route} is not bound to the v2 request boundary")
    transport_mode = provider.get("transport", {}).get("mode")
    if transport_mode != mode:
        raise BoundaryError(
            f"route {route} transport mode is {transport_mode!r}; this path requires {mode!r}"
        )
    preflight = next(
        (item for item in state["capabilities"]["preflight"] if item.get("provider_id") == route),
        None,
    )
    if preflight is None or preflight.get("ready") is not True:
        raise BoundaryError(f"route {route} preflight is not ready")
    if binding == "no_network_demo":
        return {**provider, "_adapter_key": None}
    adapter_key = f"{provider.get('adapter')}@{provider.get('adapter_version')}"
    if adapter_key not in _adapters():
        raise BoundaryError(f"no bound adapter for {adapter_key}")
    return {**provider, "_adapter_key": adapter_key}


def _demo_result(query: str) -> ParsedResult:
    """Deterministic no-network result: exercises the full lifecycle honestly.

    Demo occurrences are real occurrences (permits, journal, spool, state
    patch), but the registry bars demo routes from ever supporting claims —
    this is the harness demonstrating itself, not producing evidence.
    """

    text = (
        "Demo probe result (no network, no cost).\n"
        f"query: {query}\n"
        "This deterministic payload proves the permit -> attempt -> spool -> "
        "occurrence -> validate -> render loop end to end."
    )
    return ParsedResult(
        synthesis_text=text,
        citations=[],
        cost_usd=0.0,
        usage={"demo": True},
        model="demo-local",
        kind="demo_probe",
    )


def execute_probe(
    session_dir: Path,
    action_id: str,
    query: str,
    now: str,
    transport: Optional[Transport] = None,
    environ: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Execute one already-permitted probe request end to end.

    Lifecycle written to the event journal: attempted, then exactly one of
    completed (occurrence recorded), failed (terminal, permit consumed), or
    uncertain (timeout after send — the provider may have processed it).
    """

    session_dir = Path(session_dir)
    if not isinstance(query, str) or not query.strip():
        raise BoundaryError("query must be a non-empty string")
    transport = transport or _urllib_transport
    env = dict(os.environ if environ is None else environ)

    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise BoundaryError("event history is malformed")
        permit = _permit_for(events, action_id)
        if permit.get("category") != "probe":
            raise BoundaryError("execute_probe only handles probe permits")
        provider = _bound_route(state, permit.get("route"), mode="sync")

        if provider["_adapter_key"] is None:  # no_network_demo route
            _record_attempt_status_unlocked(
                session_dir, action_id, "attempted", now, {"demo": True}
            )
            parsed = _demo_result(query.strip())
            payload = json.dumps(
                {"demo": True, "query": query.strip(), "model": parsed.model},
                ensure_ascii=False,
            ).encode("utf-8")
            spool_path = _spool_raw(session_dir, action_id, payload)
            _record_attempt_status_unlocked(
                session_dir, action_id, "accepted", now, {"demo": True, "spool": spool_path.name}
            )
            return _record_occurrence(
                session_dir, state, provider, action_id, sha256_hex(query.strip()),
                sha256_hex({"demo": query.strip()}), parsed, spool_path, now,
            )

        adapter = _adapters()[provider["_adapter_key"]]

        spec = adapter["build"](query.strip(), env)
        # Fingerprint binds the attempt to the exact request without leaking auth.
        fingerprint = _request_fingerprint(spec)
        wall_cap = state["contract"]["resource_envelope"]["external"].get("max_wall_time_seconds")
        timeout = min(spec.timeout_s, wall_cap) if isinstance(wall_cap, int) else spec.timeout_s
        spec = RequestSpec(spec.method, spec.url, spec.headers, spec.body, float(timeout))

        _record_attempt_status_unlocked(
            session_dir, action_id, "attempted", now, {"fingerprint": fingerprint}
        )
        try:
            status, payload = transport(spec)
        except (socket.timeout, TimeoutError) as exc:
            _record_attempt_status_unlocked(
                session_dir, action_id, "uncertain", now,
                {"error": f"timeout after send: {exc}"},
            )
            raise BoundaryError(f"request timed out; attempt recorded uncertain: {exc}") from exc
        except urllib.error.HTTPError as exc:  # response with error status
            status, payload = exc.code, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            _record_attempt_status_unlocked(
                session_dir, action_id, "failed", now, {"error": f"transport: {exc}"}
            )
            raise BoundaryError(f"transport failed; permit consumed: {exc}") from exc

        spool_path = _spool_raw(session_dir, action_id, payload)
        _record_attempt_status_unlocked(
            session_dir, action_id, "accepted", now,
            {"http_status": status, "spool": spool_path.name},
        )
        if status != 200:
            _record_attempt_status_unlocked(
                session_dir, action_id, "failed", now,
                {"http_status": status, "spool": spool_path.name},
            )
            raise BoundaryError(f"provider returned HTTP {status}; raw payload spooled")
        try:
            parsed = adapter["parse"](payload)
        except AdapterParseError as exc:
            _record_attempt_status_unlocked(
                session_dir, action_id, "failed", now,
                {"error": str(exc)[:300], "spool": spool_path.name},
            )
            raise

        return _record_occurrence(
            session_dir, state, provider, action_id, sha256_hex(query.strip()),
            fingerprint, parsed, spool_path, now,
        )


# ── Async deep-engine boundary ──────────────────────────────────────────────
#
# submit is the paid POST: it consumes the already-acquired `deep` permit's
# action and is NEVER retried by this boundary. poll is one physical GET per
# call, consuming a separately-acquired `transport` permit each time — the
# caller (Organizer/CLI) drives the backoff cadence between calls, since the
# session lock must never be held across a sleep. deep-timeout is a free,
# no-network wall-clock check that moves a stuck `accepted` action to
# `uncertain`; the next poll call journals a resume and continues.


def execute_deep_submit(
    session_dir: Path,
    action_id: str,
    query: str,
    now: str,
    transport: Optional[Transport] = None,
    environ: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Submit one already-permitted deep-research job. The paid POST is sent
    at most once: on any ambiguity after the bytes go out (timeout) this
    records `uncertain` and raises rather than retrying.

    Lifecycle written to the event journal: attempted, then exactly one of
    accepted (details include the provider job token), failed (terminal HTTP
    error or malformed accept body; permit consumed), or uncertain (timeout
    after send).
    """

    session_dir = Path(session_dir)
    if not isinstance(query, str) or not query.strip():
        raise BoundaryError("query must be a non-empty string")
    query = query.strip()
    transport = transport or _urllib_transport
    env = dict(os.environ if environ is None else environ)

    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise BoundaryError("event history is malformed")
        permit = _permit_for(events, action_id)
        if permit.get("category") != "deep":
            raise BoundaryError("execute_deep_submit only handles deep permits")
        provider = _bound_route(state, permit.get("route"), mode="async")
        adapter = _adapters()[provider["_adapter_key"]]

        spec = adapter["submit"](query, env)
        # Fingerprint binds the attempt to the exact paid request without leaking auth.
        fingerprint = _request_fingerprint(spec)
        query_hash = sha256_hex(query)

        _record_attempt_status_unlocked(
            session_dir, action_id, "attempted", now,
            {"fingerprint": fingerprint, "query_hash": query_hash},
        )
        try:
            status, payload = transport(spec)
        except (socket.timeout, TimeoutError) as exc:
            _record_attempt_status_unlocked(
                session_dir, action_id, "uncertain", now,
                {"error": f"timeout after send: {exc}"},
            )
            raise BoundaryError(
                f"submit timed out; attempt recorded uncertain (never retried): {exc}"
            ) from exc
        except urllib.error.HTTPError as exc:  # response with error status
            status, payload = exc.code, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            _record_attempt_status_unlocked(
                session_dir, action_id, "failed", now, {"error": f"transport: {exc}"}
            )
            raise BoundaryError(f"submit transport failed; permit consumed: {exc}") from exc

        # Raw accept payload spooled before any parsing: a malformed accept
        # body never loses the paid bytes.
        spool_path = _spool_raw(session_dir, action_id, payload)

        if status != 200:
            _record_attempt_status_unlocked(
                session_dir, action_id, "accepted", now,
                {"http_status": status, "spool": spool_path.name},
            )
            _record_attempt_status_unlocked(
                session_dir, action_id, "failed", now,
                {"http_status": status, "spool": spool_path.name},
            )
            raise BoundaryError(f"provider returned HTTP {status} on submit; raw payload spooled")

        try:
            token = adapter["job_token"](payload)
        except AdapterParseError as exc:
            _record_attempt_status_unlocked(
                session_dir, action_id, "accepted", now,
                {"http_status": status, "spool": spool_path.name},
            )
            _record_attempt_status_unlocked(
                session_dir, action_id, "failed", now,
                {"error": str(exc)[:300], "spool": spool_path.name},
            )
            raise

        job_ref = f"{provider['id']}:{token}"
        _record_attempt_status_unlocked(
            session_dir, action_id, "accepted", now,
            {"job": job_ref, "http_status": status, "spool": spool_path.name},
        )
        return {
            "action_id": action_id,
            "job": job_ref,
            "status": "accepted",
            "spool_path": str(spool_path),
        }


def execute_deep_poll(
    session_dir: Path,
    deep_action_id: str,
    poll_action_id: str,
    now: str,
    transport: Optional[Transport] = None,
    environ: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Execute exactly ONE physical poll GET against an accepted or uncertain
    deep action, consuming a separately-acquired `transport` permit.

    Outcomes:
    - still running: the poll action's own attempt completes (details
      {"job_status": "running"}); the deep action is left untouched.
    - terminal success: the poll action completes; an occurrence is recorded
      against the DEEP action and its attempt transitions to completed.
    - terminal failure (well-formed provider FAILED status): the poll action
      completes (it did its job); the deep action's attempt transitions to
      failed.
    - malformed terminal: the poll action's attempt fails and AdapterParseError
      propagates; the deep action is left untouched (still accepted),
      harvestable by a later poll at zero marginal cost.

    Calling this on an `uncertain` deep action first journals a resume
    transition (uncertain -> accepted, details {"resume": true}) before the
    physical poll — this IS the "harvest after uncertain" path; there is no
    separate resume verb.
    """

    session_dir = Path(session_dir)
    transport = transport or _urllib_transport
    env = dict(os.environ if environ is None else environ)

    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise BoundaryError("event history is malformed")

        deep_permit, deep_status = _deep_action_lookup(events, deep_action_id)
        if deep_permit.get("category") != "deep":
            raise BoundaryError("execute_deep_poll deep_action_id must be a deep action")
        if deep_status not in {"accepted", "uncertain"}:
            raise BoundaryError(
                f"deep action {deep_action_id} is not pollable from status {deep_status!r}"
            )

        poll_permit = _permit_for(events, poll_action_id)
        if poll_permit.get("category") != "transport":
            raise BoundaryError("execute_deep_poll poll_action_id must be a fresh transport permit")
        if poll_permit.get("route") != deep_permit.get("route"):
            raise BoundaryError("poll permit route must match the deep action's route")

        provider = _bound_route(state, deep_permit["route"], mode="async")
        adapter = _adapters()[provider["_adapter_key"]]

        if deep_status == "uncertain":
            _record_attempt_status_unlocked(
                session_dir, deep_action_id, "accepted", now, {"resume": True}
            )

        token = _job_token_for(events, deep_action_id)
        spec = adapter["poll"](token, env)
        poll_fingerprint = _request_fingerprint(spec)

        _record_attempt_status_unlocked(
            session_dir, poll_action_id, "attempted", now, {"fingerprint": poll_fingerprint}
        )
        try:
            status, payload = transport(spec)
        except (socket.timeout, TimeoutError) as exc:
            _record_attempt_status_unlocked(
                session_dir, poll_action_id, "uncertain", now,
                {"error": f"timeout after send: {exc}"},
            )
            raise BoundaryError(f"poll timed out; attempt recorded uncertain: {exc}") from exc
        except urllib.error.HTTPError as exc:
            status, payload = exc.code, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            _record_attempt_status_unlocked(
                session_dir, poll_action_id, "failed", now, {"error": f"transport: {exc}"}
            )
            raise BoundaryError(f"poll transport failed; permit consumed: {exc}") from exc

        poll_spool_path = _spool_raw(session_dir, poll_action_id, payload)
        _record_attempt_status_unlocked(
            session_dir, poll_action_id, "accepted", now,
            {"http_status": status, "spool": poll_spool_path.name},
        )

        if status != 200:
            _record_attempt_status_unlocked(
                session_dir, poll_action_id, "failed", now,
                {"http_status": status, "spool": poll_spool_path.name},
            )
            raise BoundaryError(f"provider returned HTTP {status} on poll; raw payload spooled")

        try:
            parsed = adapter["extract"](payload)
        except AdapterTerminalFailure as exc:
            # The poll itself succeeded (it correctly learned the job failed).
            _record_attempt_status_unlocked(
                session_dir, poll_action_id, "completed", now,
                {"job_status": "failed", "spool": poll_spool_path.name},
            )
            _record_attempt_status_unlocked(
                session_dir, deep_action_id, "failed", now,
                {"error": str(exc)[:300], "spool": poll_spool_path.name},
            )
            raise BoundaryError(f"deep job terminal failure: {exc}") from exc
        except AdapterParseError:
            # Genuinely unreadable payload: the poll attempt itself failed.
            # The deep action is deliberately left untouched (still accepted
            # or freshly resumed) so a later poll can harvest at zero cost.
            _record_attempt_status_unlocked(
                session_dir, poll_action_id, "failed", now,
                {"error": "malformed terminal payload", "spool": poll_spool_path.name},
            )
            raise

        if parsed is None:
            _record_attempt_status_unlocked(
                session_dir, poll_action_id, "completed", now, {"job_status": "running"}
            )
            return {
                "deep_action_id": deep_action_id,
                "poll_action_id": poll_action_id,
                "status": "running",
                "poll_spool_path": str(poll_spool_path),
            }

        _record_attempt_status_unlocked(
            session_dir, poll_action_id, "completed", now,
            {"job_status": "completed", "spool": poll_spool_path.name},
        )
        query_hash = _deep_query_hash(events, deep_action_id)
        result = _record_occurrence(
            session_dir, state, provider, deep_action_id, query_hash,
            poll_fingerprint, parsed, poll_spool_path, now,
        )
        result["status"] = "completed"
        result["poll_action_id"] = poll_action_id
        return result


def execute_deep_timeout(session_dir: Path, action_id: str, now: str) -> dict[str, Any]:
    """Free, no-network wall-clock check: move an `accepted` deep action to
    `uncertain` once the contract's external.max_wall_time_seconds has
    elapsed since the ORIGINAL submission (the first accepted event's `at` —
    a later resume never pushes this deadline out).

    Idempotent and side-effect-free when there is nothing to do: an action
    that is not `accepted`, or has not yet timed out, returns
    {"transitioned": False, ...} rather than raising, so a monitoring loop
    can call this indiscriminately over every deep action in a session.
    """

    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, errors = _read_events_unlocked(session_dir)
        if errors:
            raise BoundaryError("event history is malformed")
        permit, status = _deep_action_lookup(events, action_id)
        if permit.get("category") != "deep":
            raise BoundaryError("execute_deep_timeout only handles deep actions")
        if status != "accepted":
            return {"action_id": action_id, "transitioned": False, "reason": f"status is {status}"}

        submitted_at = _first_status_at(events, action_id, "accepted")
        wall_cap = state["contract"]["resource_envelope"]["external"].get("max_wall_time_seconds")
        if not isinstance(wall_cap, int):
            raise BoundaryError("contract external.max_wall_time_seconds is not configured")
        elapsed = _elapsed_seconds(submitted_at, now)
        if elapsed < wall_cap:
            return {
                "action_id": action_id,
                "transitioned": False,
                "elapsed_seconds": elapsed,
                "max_wall_time_seconds": wall_cap,
            }
        _record_attempt_status_unlocked(
            session_dir, action_id, "uncertain", now,
            {"elapsed_seconds": elapsed, "max_wall_time_seconds": wall_cap},
        )
        return {
            "action_id": action_id,
            "transitioned": True,
            "elapsed_seconds": elapsed,
            "max_wall_time_seconds": wall_cap,
        }


def _record_occurrence(
    session_dir: Path,
    state: dict[str, Any],
    provider: dict[str, Any],
    action_id: str,
    query_hash: str,
    fingerprint: str,
    parsed: ParsedResult,
    spool_path: Path,
    now: str,
) -> dict[str, Any]:
    """Write the occurrence patch and complete the attempt. Caller holds the lock.

    `query_hash` is pre-hashed by the caller rather than taking the raw query
    text: the async poll path recovers it from the journal (the raw query is
    not available at poll time) and the sync path hashes it inline, so both
    callers converge on this one shape.
    """

    occurrence = {
        "id": f"occ-{action_id}",
        "provider_id": provider["id"],
        "action_id": action_id,
        "kind": parsed.kind,
        "query_hash": query_hash,
        "fingerprint": fingerprint,
        "at": now,
        "model": parsed.model,
        "cost_usd": parsed.cost_usd,
        "citation_count": len(parsed.citations),
        "citations": parsed.citations[:CITATION_LIMIT],
        "synthesis_excerpt": parsed.synthesis_text[:SYNTHESIS_EXCERPT_LIMIT],
        "synthesis_truncated": len(parsed.synthesis_text) > SYNTHESIS_EXCERPT_LIMIT,
        "spool": spool_path.name,
    }
    updated = _apply_boundary_patch_unlocked(
        session_dir,
        [{"op": "add", "path": "/retrieval_occurrences/-", "value": occurrence}],
        state["session"]["revision"],
        now,
    )
    _record_attempt_status_unlocked(
        session_dir, action_id, "completed", now,
        {"occurrence_id": occurrence["id"], "cost_usd": parsed.cost_usd,
         "citation_count": len(parsed.citations)},
    )
    return {
        "occurrence": occurrence,
        "revision": updated["session"]["revision"],
        "spool_path": str(spool_path),
    }
