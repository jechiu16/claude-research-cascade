"""v2 request boundary: turn one acquired permit into one physical request.

DRAFT schema notice: the occurrence shape and adapter protocol below serve in
draft status until two or three adapters and at least one real session have
exercised them. Do not treat field lists here as locked.

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


@dataclass(frozen=True)
class RequestSpec:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes
    timeout_s: float


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


def _urllib_transport(spec: RequestSpec) -> tuple[int, bytes]:
    # body=b"" means "no body": pass None so a GET stays truly bodyless
    # (data=b"" would still attach Content-Length/Content-Type headers).
    request = urllib.request.Request(
        spec.url, data=spec.body or None, headers=spec.headers, method=spec.method
    )
    with urllib.request.urlopen(request, timeout=spec.timeout_s) as response:
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


def _bound_route(state: dict[str, Any], route: str) -> dict[str, Any]:
    provider = next(
        (item for item in state["capabilities"]["providers"] if item.get("id") == route),
        None,
    )
    if provider is None or provider.get("enabled") is not True:
        raise BoundaryError(f"route {route} is not enabled in the capability snapshot")
    binding = provider.get("execution_binding")
    if binding not in {"v2_request_boundary", "no_network_demo"}:
        raise BoundaryError(f"route {route} is not bound to the v2 request boundary")
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
        provider = _bound_route(state, permit.get("route"))

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
                session_dir, state, provider, action_id, query.strip(),
                sha256_hex({"demo": query.strip()}), parsed, spool_path, now,
            )

        adapter = _adapters()[provider["_adapter_key"]]

        spec = adapter["build"](query.strip(), env)
        # Fingerprint binds the attempt to the exact request without leaking auth.
        fingerprint = sha256_hex({"url": spec.url, "body": spec.body.decode("utf-8")})
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
            session_dir, state, provider, action_id, query.strip(),
            fingerprint, parsed, spool_path, now,
        )


def _record_occurrence(
    session_dir: Path,
    state: dict[str, Any],
    provider: dict[str, Any],
    action_id: str,
    query: str,
    fingerprint: str,
    parsed: ParsedResult,
    spool_path: Path,
    now: str,
) -> dict[str, Any]:
    """Write the occurrence patch and complete the attempt. Caller holds the lock."""

    occurrence = {
        "id": f"occ-{action_id}",
        "provider_id": provider["id"],
        "action_id": action_id,
        "kind": parsed.kind,
        "query_hash": sha256_hex(query),
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
