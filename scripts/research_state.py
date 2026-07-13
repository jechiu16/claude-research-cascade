#!/usr/bin/env python3
"""JSON-first Organizer CLI for canonical v2 research sessions."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_harness.artifacts import (
    ingest_fetched_source,
    ingest_local_artifact,
    promote_provider_payload,
)
from research_harness.boundary import (
    execute_deep_poll,
    execute_deep_submit,
    execute_deep_timeout,
    execute_probe,
)
from research_harness.contracts import (
    contract_card_sha256,
    normalize_contract,
    validate_contract,
)
from research_harness.operations import purge_artifact, recover_operation
from research_harness.providers import (
    load_provider_registry,
    preflight_contract_routes,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
)
from research_harness.quota import _record_attempt_status_unlocked, acquire_permits, permit_usage
from research_harness.rendering import render_session_result
from research_harness.state import new_state, state_sha256
from research_harness.storage import (
    _read_events_unlocked,
    _recover_session_unlocked,
    apply_state_patch,
    create_session,
    load_state,
    read_events,
    session_lock,
)
from research_harness.validation import validate_session


# Set by main() from the exact argv it is about to parse (not sys.argv --
# main() also accepts an explicit argv list for in-process callers), right
# before parse_args() and reset in a finally. argparse failures (missing
# required arg, bad --count int) call ArgumentParser.error() and exit(2)
# from inside build_parser().parse_args(argv), before main()'s try/except
# ever runs -- this is the only hook point with both the real error message
# and, for --json callers, a reason to also put a JSON envelope on stdout
# instead of leaving it empty. A class attribute (rather than per-instance)
# is required because subparsers are separate _JSONArgumentParser instances
# created inside build_parser(), before any argv is known.
_JSONArgumentParser_json_mode = False


class _JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        if _JSONArgumentParser_json_mode:
            self.print_usage(sys.stderr)
            print(f"{self.prog}: error: {message}", file=sys.stderr)
            print(
                json.dumps(
                    {"error": message, "command": self.prog.split()[-1] if self.prog else None},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            self.exit(2)
        super().error(message)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    nearest = find_dotenv(usecwd=True)
    if nearest:
        load_dotenv(nearest, override=False)
    load_dotenv(ROOT / ".env", override=False)


def _read_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON from {source}: {exc}") from exc


def _registry(overlay: str | None) -> dict[str, Any]:
    return load_provider_registry(overlay=Path(overlay) if overlay else None)


def _binding(contract: dict[str, Any], registry: dict[str, Any]) -> dict[str, str]:
    records = referenced_provider_records(contract, registry)
    return {
        "card_sha256": contract_card_sha256(contract),
        "registry_sha256": provider_registry_sha256(registry),
        "referenced_records_sha256": provider_records_sha256(records),
    }


def _unconfirmed(contract: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(normalize_contract(contract))
    value["confirmation"] = {
        "confirmed_by": None,
        "confirmed_at": None,
        "card_sha256": None,
        "registry_sha256": None,
        "referenced_records_sha256": None,
    }
    return value


READY_BINDINGS = frozenset(
    {"v2_request_boundary", "host_native_observed", "local", "no_network_demo"}
)


def _provider_readiness(provider: dict[str, Any]) -> tuple[str, str]:
    missing = [item["name"] for item in provider["required_env"] if not item["present"]]
    if not provider["enabled"]:
        return "disabled", "-"
    if provider["execution_binding"] not in READY_BINDINGS:
        return "unbound", "-"
    if missing:
        return "missing-key", ",".join(missing)
    return "ready", "configured" if provider["required_env"] else "none"


def _format_provider_readiness(payload: dict[str, Any]) -> str:
    rows = []
    for provider in payload["providers"]:
        if provider.get("id", "").startswith("test-only-") or "contract-test" in provider.get("roles", []):
            continue
        state, detail = _provider_readiness(provider)
        rows.append((provider["id"], state, detail))
    rows.sort()

    route_width = max(len("ROUTE"), max((len(row[0]) for row in rows), default=0))
    state_width = max(len("STATE"), max((len(row[1]) for row in rows), default=0))
    lines = [
        f"{'ROUTE':<{route_width}}  {'STATE':<{state_width}}  REQUIREMENT",
        f"{'-' * route_width}  {'-' * state_width}  ------------",
    ]
    lines.extend(
        f"{route:<{route_width}}  {state:<{state_width}}  {detail}"
        for route, state, detail in rows
    )
    counts = {state: sum(row[1] == state for row in rows) for state in ("ready", "missing-key", "disabled", "unbound")}
    lines.append(
        "Counts: "
        + ", ".join(f"{state}={counts[state]}" for state in ("ready", "missing-key", "disabled", "unbound"))
    )
    lines.append("Machine output: providers --json")
    return "\n".join(lines) + "\n"


def _validate_prepared_contract(
    contract: dict[str, Any], registry: dict[str, Any], binding: dict[str, str]
) -> None:
    candidate = copy.deepcopy(contract)
    candidate["confirmation"] = {
        "confirmed_by": "user",
        "confirmed_at": "PREPARED",
        **binding,
    }
    errors = validate_contract(
        candidate,
        registry,
        resolved_registry_sha256=binding["registry_sha256"],
    )
    if errors:
        raise ValueError("invalid contract: " + "; ".join(errors))


def command_providers(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    registry = _registry(args.registry_overlay)
    providers = []
    for provider in registry["providers"]:
        providers.append(
            {
                "id": provider["id"],
                "enabled": provider["enabled"],
                "adapter": provider["adapter"],
                "adapter_version": provider["adapter_version"],
                "execution_binding": provider["execution_binding"],
                "adoption_status": provider["adoption_status"],
                "roles": provider["roles"],
                "action_categories": provider["action_categories"],
                "stage_capabilities": provider["stage_capabilities"],
                "request_multiplicity": provider["request_multiplicity"],
                "required_env": [
                    {"name": name, "present": bool(os.environ.get(name))}
                    for name in provider["required_env"]
                ],
                "storage_rights": provider["storage_rights"],
            }
        )
    return {
        "schema_version": registry["schema_version"],
        "registry_sha256": provider_registry_sha256(registry),
        "providers": providers,
    }, 0


def command_prepare(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    contract = _unconfirmed(_read_json(args.contract))
    registry = _registry(args.registry_overlay)
    binding = _binding(contract, registry)
    _validate_prepared_contract(contract, registry, binding)
    preflight, preflight_errors = preflight_contract_routes(contract, registry, os.environ)
    return {
        "contract": contract,
        "binding": binding,
        "preflight": preflight,
        "preflight_errors": preflight_errors,
        "resolved_registry": registry,
    }, 0


def command_confirm(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    prepared = _read_json(args.prepared)
    if not isinstance(prepared, dict):
        raise ValueError("prepared payload must be an object")
    contract = _unconfirmed(prepared.get("contract"))
    binding = prepared.get("binding")
    registry = prepared.get("resolved_registry")
    if not isinstance(binding, dict) or not isinstance(registry, dict):
        raise ValueError("prepared payload is missing binding or resolved_registry")
    if args.card_sha256 != binding.get("card_sha256"):
        raise ValueError("card hash does not match prepared contract")
    if args.registry_sha256 != binding.get("registry_sha256"):
        raise ValueError("registry hash does not match prepared registry")
    if args.referenced_records_sha256 != binding.get("referenced_records_sha256"):
        raise ValueError("referenced-records hash does not match prepared routes")
    recomputed = _binding(contract, registry)
    if recomputed.get("card_sha256") != binding.get("card_sha256"):
        raise ValueError("prepared contract bytes changed after presentation")
    if recomputed != binding:
        raise ValueError("prepared registry binding changed after presentation")
    contract["confirmation"] = {
        "confirmed_by": args.confirmed_by,
        "confirmed_at": args.confirmed_at,
        **binding,
    }
    errors = validate_contract(
        contract,
        registry,
        resolved_registry_sha256=binding["registry_sha256"],
    )
    if errors:
        raise ValueError("confirmed contract is invalid: " + "; ".join(errors))
    return {"contract": contract, "binding": binding}, 0


def command_init(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    contract_payload = _read_json(args.contract)
    if isinstance(contract_payload, dict) and isinstance(contract_payload.get("contract"), dict):
        contract_payload = contract_payload["contract"]
    contract = normalize_contract(contract_payload)
    registry = _registry(args.registry_overlay)
    state = new_state(args.question, contract, args.now or _now(), registry, os.environ)
    session = Path(args.session)
    create_session(session, state)
    return {
        "session_id": state["session"]["id"],
        "state_path": str((session / "state.json").resolve()),
        "state_sha256": state_sha256(state),
    }, 0


def command_patch(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    patch = _read_json(args.patch)
    operations = patch.get("operations") if isinstance(patch, dict) else patch
    if not isinstance(operations, list):
        raise ValueError("patch JSON must be a list or contain an operations list")
    expected = args.expected_revision
    if expected is None:
        expected = load_state(Path(args.session))["session"]["revision"]
    state = apply_state_patch(Path(args.session), operations, expected, args.now or _now())
    return {
        "revision": state["session"]["revision"],
        "state_sha256": state_sha256(state),
    }, 0


def command_permit(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    permits = acquire_permits(
        Path(args.session),
        args.action_id,
        args.stage,
        args.category,
        args.route,
        args.count,
        args.fingerprint,
        args.now or _now(),
    )
    return {"permits": permits, "usage": permit_usage(Path(args.session))}, 0


ATTEMPT_CLI_CATEGORIES = {"organizer_pass", "local", "host_retrieval", "network_experiment"}


def command_attempt(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Journal one attempt-status transition for an acquired action.

    Boundary-executed routes journal their own transitions; host, local,
    organizer-pass, and network-experiment actions (e.g. the High-tier
    context-separated verifier) have no boundary call, so this is their
    only path to `completed`. Boundary-managed categories are refused:
    `_permit_for` rejects any already-attempted action, so journaling one
    here would permanently void its permit without a request. Illegal
    transitions raise InvalidAttemptTransition from the quota core
    unchanged."""

    session = Path(args.session)
    with session_lock(session):
        _recover_session_unlocked(session)
        events, errors = _read_events_unlocked(session)
        if errors:
            raise ValueError("event history is malformed: " + "; ".join(errors))
        permits = [
            event
            for event in events
            if event.get("event") == "permit_acquired"
            and event.get("action_id") == args.action_id
        ]
        if len(permits) != 1:
            raise ValueError(f"action {args.action_id} has no unique acquired permit")
        category = permits[0].get("category")
        if category not in ATTEMPT_CLI_CATEGORIES:
            raise ValueError(
                f"attempt is only for host/local/organizer actions; category {category} "
                "is boundary-managed (execute and deep-* record its transitions)"
            )
        event = _record_attempt_status_unlocked(
            session, args.action_id, args.status, args.now or _now()
        )
    return {
        "action_id": args.action_id,
        "status": args.status,
        "event_hash": event["event_hash"],
    }, 0


def _demo_contract(registry: dict[str, Any]) -> dict[str, Any]:
    """Confirmed zero-network demo contract: one demo-probe, one organizer pass.

    Running `demo` IS the confirmation — the route is no-network, no-key,
    no-cost by registry construction, so the trigger the card protects
    (external spend) cannot fire.
    """

    contract = {
        "posture": "lookup",
        "tier": "custom",
        "execution": "external_managed",
        "durability": "canonical_package",
        "scout_route": "demo-probe",
        "resource_envelope": {
            "physical_ceiling": {
                "probe": 1, "deep": 0, "processor": 0, "network_experiment": 0,
                "transport": 0, "host_retrieval": 0, "local": 0, "organizer_pass": 1,
            },
            "external": {
                "metered_ceiling": {
                    "probe": 0, "deep": 0, "processor": 0,
                    "network_experiment": 0, "transport": 0,
                },
                "max_wall_time_seconds": 60,
                "allowed_endpoint_classes": [],
                "local_file_egress": False,
                "network_experiment_endpoints": [],
                "estimated_spend_usd": {"minimum": 0.0, "maximum": 0.0, "hard_cap": True},
                "raw_storage_bytes": 1024 * 1024,
            },
            "host": {"context_class": "lean", "admitted_characters": 4000, "estimated_tokens": 1000},
            "local": {"admitted_output_characters": 0, "max_wall_time_seconds": 60, "network_egress": False},
        },
        "stage_permit_map": [
            {"stage": "primary_scout", "category": "probe", "route": "demo-probe",
             "invocations": 1, "count": 1, "reserved": False},
            {"stage": "final_inference_review", "category": "organizer_pass", "route": "host",
             "invocations": 1, "count": 1, "reserved": True},
        ],
        "evidence_floor": {"minimum_load_bearing_claims": 1, "require_raw_artifacts": True},
        "artifact_policy": {"default_retention": "session", "allow_provider_payloads": False},
    }
    contract = normalize_contract(contract)
    contract["confirmation"] = {
        "confirmed_by": "user",
        "confirmed_at": _now(),
        **_binding(contract, registry),
    }
    return contract


def command_demo(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    from research_harness.quota import acquire_permits as _acquire
    from research_harness.state import new_state as _new_state
    from research_harness.storage import create_session as _create

    registry = _registry(None)
    contract = _demo_contract(registry)
    question = args.question or "demo: prove the permit->attempt->occurrence->validate->render loop"
    now = args.now or _now()
    session = Path(args.session)
    state = _new_state(question, contract, now, registry, os.environ)
    _create(session, state)
    _acquire(session, "demo-1", "primary_scout", "probe", "demo-probe", 1, "demo", now)
    executed = execute_probe(session, "demo-1", question, now)
    rendered = render_session_result(session)
    return {
        "session_id": state["session"]["id"],
        "occurrence": executed["occurrence"]["id"],
        "report_path": str(rendered.path.resolve()),
        "validation_ok": rendered.validation.ok,
        "next": "open the report, then read SKILL.md for the real flow "
                "(prepare -> confirm -> init -> permit -> execute -> validate -> render)",
    }, 0 if rendered.validation.ok else 1


def command_execute(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result = execute_probe(
        Path(args.session),
        args.action_id,
        args.query,
        args.now or _now(),
    )
    return result, 0


def command_deep_submit(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result = execute_deep_submit(
        Path(args.session),
        args.action_id,
        args.query,
        args.now or _now(),
    )
    return result, 0


def command_deep_poll(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result = execute_deep_poll(
        Path(args.session),
        args.action_id,
        args.poll_action_id,
        args.now or _now(),
    )
    return result, 0


def command_deep_timeout(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result = execute_deep_timeout(
        Path(args.session),
        args.action_id,
        args.now or _now(),
    )
    return result, 0


def command_deep_pending(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Free (no lock, no permit): scan the journal for deep actions that are
    accepted or uncertain (submitted but not yet terminal) and print their
    job tokens so an operator can decide whether to keep polling or resume."""

    events, errors = read_events(Path(args.session))
    if errors:
        raise ValueError("event history is malformed: " + "; ".join(errors))
    deep_actions: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event") == "permit_acquired" and event.get("category") == "deep":
            action_id = event.get("action_id")
            if isinstance(action_id, str):
                deep_actions[action_id] = {"route": event.get("route"), "status": "acquired", "job": None}
    for event in events:
        if event.get("event") != "attempt_status":
            continue
        action_id = event.get("action_id")
        if action_id not in deep_actions:
            continue
        deep_actions[action_id]["status"] = event.get("status")
        details = event.get("details") or {}
        job = details.get("job")
        if isinstance(job, str):
            deep_actions[action_id]["job"] = job
    pending = [
        {"action_id": action_id, **info}
        for action_id, info in sorted(deep_actions.items())
        if info["status"] in {"accepted", "uncertain"}
    ]
    return {"pending": pending}, 0


def command_status(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    state = load_state(Path(args.session))
    validation = validate_session(Path(args.session))
    return {
        "session_id": state["session"]["id"],
        "revision": state["session"]["revision"],
        "summary": state["summary"],
        "usage": permit_usage(Path(args.session)),
        "validation": validation.to_dict(),
    }, 0


def command_citations(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Free, read-only harvest of citations recorded on retrieval occurrences.

    This is the verification-stage collection list: the Organizer samples
    from its `unverified` remainder and directly fetches (host-web permit)
    a chosen citation, turning it into fetched_source evidence instead of a
    listing-only reference. Citations are deduplicated by url across every
    retrieval occurrence (optionally narrowed to one --action-id) and each
    is marked `directly_verified` when state.sources already has a matching
    url with `direct_fetch: true`. Zero network, no lock acquired, no state
    write -- same read as the `status` subcommand.
    """

    state = load_state(Path(args.session))
    direct_fetch_urls = {
        source.get("url")
        for source in state.get("sources", [])
        if isinstance(source, dict)
        and source.get("direct_fetch") is True
        and isinstance(source.get("url"), str)
    }
    by_url: dict[str, dict[str, Any]] = {}
    for occurrence in state.get("retrieval_occurrences", []):
        if not isinstance(occurrence, dict):
            continue
        action_id = occurrence.get("action_id")
        if args.action_id and action_id != args.action_id:
            continue
        for citation in occurrence.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            url = citation.get("url")
            if not isinstance(url, str) or not url:
                continue
            entry = by_url.setdefault(
                url,
                {
                    "title": citation.get("title"),
                    "url": url,
                    "occurrence_action_ids": [],
                    "directly_verified": url in direct_fetch_urls,
                },
            )
            if isinstance(action_id, str) and action_id not in entry["occurrence_action_ids"]:
                entry["occurrence_action_ids"].append(action_id)
    citations = sorted(by_url.values(), key=lambda item: item["url"])
    unverified = sum(1 for item in citations if not item["directly_verified"])
    return {"citations": citations, "total": len(citations), "unverified": unverified}, 0


def command_artifact_add(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.origin_kind in {"provider_payload", "processor_output"}:
        raise ValueError("provider artifacts require a bound adapter operation")
    sensitivity = args.sensitivity
    if sensitivity is None:
        sensitivity = "public" if args.origin_kind == "fetched_source" else "local-sensitive"
    now = args.now or _now()
    if args.origin_kind == "fetched_source":
        artifact = ingest_fetched_source(
            Path(args.session),
            Path(args.source),
            args.artifact_id,
            args.media_type,
            args.source_id,
            args.fetch_occurrence_id,
            sensitivity,
            args.retention,
            args.include_in_html,
            now,
        )
    elif args.origin_kind in {"local_output", "user_file"}:
        provenance = {"origin_kind": args.origin_kind}
        if args.origin_kind == "local_output":
            provenance["action_id"] = args.action_id
        else:
            provenance["supplied_by"] = args.supplied_by
        review = None
        if any((args.reviewed_by, args.reviewed_at, args.review_method)):
            review = {
                "reviewed_by": args.reviewed_by,
                "reviewed_at": args.reviewed_at,
                "method": args.review_method,
            }
        artifact = ingest_local_artifact(
            Path(args.session),
            Path(args.source),
            args.artifact_id,
            args.media_type,
            sensitivity,
            args.retention,
            args.include_in_html,
            provenance,
            now,
            review,
        )
    else:
        raise ValueError("origin_kind must be local_output, user_file, or fetched_source")
    return {"artifact": artifact}, 0


def command_promote(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    artifact = promote_provider_payload(
        Path(args.session),
        args.action_id,
        args.artifact_id,
        args.retention,
        args.include_in_html,
        args.now or _now(),
    )
    return {"artifact": artifact}, 0


def command_artifact_purge(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result = purge_artifact(
        Path(args.session),
        args.artifact_id,
        args.reason,
        args.requested_status,
        tuple(args.safe_action_id),
        args.now or _now(),
    )
    return result, 0


def command_recover(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    return recover_operation(Path(args.session), args.now or _now()), 0


def command_validate(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report = validate_session(Path(args.session))
    return report.to_dict(), 0 if report.ok else 1 if report.errors else 2


def command_render(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    rendered = render_session_result(Path(args.session))
    return {
        "report_path": str(rendered.path.resolve()),
        "state_sha256": rendered.state_sha256,
        "report_sha256": rendered.report_sha256,
        "validation": rendered.validation.to_dict(),
    }, 0


def command_view(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report = Path(args.session) / "report.html"
    if not report.exists():
        report = render_session_result(Path(args.session)).path
    opened = webbrowser.open(report.resolve().as_uri())
    return {"report_path": str(report.resolve()), "opened": bool(opened)}, 0


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="print exactly one JSON object")


def build_parser() -> argparse.ArgumentParser:
    parser = _JSONArgumentParser(description="Canonical v2 research session runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    providers = subparsers.add_parser("providers", help="list secret-free provider capabilities")
    providers.add_argument("--registry-overlay")
    _add_json_flag(providers)
    providers.set_defaults(handler=command_providers)

    prepare = subparsers.add_parser("prepare", help="prepare an unconfirmed contract card")
    prepare.add_argument("--contract", required=True)
    prepare.add_argument("--registry-overlay")
    _add_json_flag(prepare)
    prepare.set_defaults(handler=command_prepare)

    confirm = subparsers.add_parser("confirm", help="bind the exact displayed contract card")
    confirm.add_argument("--prepared", required=True)
    confirm.add_argument("--card-sha256", required=True)
    confirm.add_argument("--registry-sha256", required=True)
    confirm.add_argument("--referenced-records-sha256", required=True)
    confirm.add_argument("--confirmed-at", required=True)
    confirm.add_argument("--confirmed-by", required=True)
    _add_json_flag(confirm)
    confirm.set_defaults(handler=command_confirm)

    init = subparsers.add_parser("init", help="create a canonical v2 session")
    init.add_argument("session")
    init.add_argument("--question", required=True)
    init.add_argument("--contract", required=True)
    init.add_argument("--registry-overlay")
    init.add_argument("--now")
    _add_json_flag(init)
    init.set_defaults(handler=command_init)

    patch = subparsers.add_parser("patch", help="apply a revision-checked Organizer patch")
    patch.add_argument("session")
    patch.add_argument("--patch", required=True)
    patch.add_argument("--expected-revision", type=int)
    patch.add_argument("--now")
    _add_json_flag(patch)
    patch.set_defaults(handler=command_patch)

    permit = subparsers.add_parser("permit", help="reserve exact physical requests")
    permit.add_argument("session")
    permit.add_argument("--action-id", required=True)
    permit.add_argument("--stage", required=True)
    permit.add_argument("--category", required=True)
    permit.add_argument("--route", required=True)
    permit.add_argument("--count", required=True, type=int)
    permit.add_argument("--fingerprint", required=True)
    permit.add_argument("--now")
    _add_json_flag(permit)
    permit.set_defaults(handler=command_permit)

    attempt = subparsers.add_parser(
        "attempt", help="journal one attempt-status transition for an acquired action"
    )
    attempt.add_argument("session")
    attempt.add_argument("--action-id", required=True)
    attempt.add_argument(
        "--status",
        required=True,
        choices=["attempted", "accepted", "failed", "uncertain", "completed"],
    )
    attempt.add_argument("--now")
    _add_json_flag(attempt)
    attempt.set_defaults(handler=command_attempt)

    demo = subparsers.add_parser(
        "demo", help="one-command no-network end-to-end session (permit -> occurrence -> report.html)"
    )
    demo.add_argument("session", help="directory to create for the demo session")
    demo.add_argument("--question")
    demo.add_argument("--now")
    _add_json_flag(demo)
    demo.set_defaults(handler=command_demo)

    execute = subparsers.add_parser(
        "execute", help="run one permitted probe through the v2 request boundary"
    )
    execute.add_argument("session")
    execute.add_argument("--action-id", required=True, help="an acquired, un-attempted permit action")
    execute.add_argument("--query", required=True)
    execute.add_argument("--now")
    _add_json_flag(execute)
    execute.set_defaults(handler=command_execute)

    deep_submit = subparsers.add_parser(
        "deep-submit", help="submit an async deep-research job (paid POST, never retried)"
    )
    deep_submit.add_argument("session")
    deep_submit.add_argument("--action-id", required=True, help="an acquired, un-attempted deep permit action")
    deep_submit.add_argument("--query", required=True)
    deep_submit.add_argument("--now")
    _add_json_flag(deep_submit)
    deep_submit.set_defaults(handler=command_deep_submit)

    deep_poll = subparsers.add_parser(
        "deep-poll", help="one physical poll of an accepted/uncertain deep job"
    )
    deep_poll.add_argument("session")
    deep_poll.add_argument("--action-id", required=True, help="the deep action being polled")
    deep_poll.add_argument(
        "--poll-action-id", required=True, help="a freshly acquired transport permit action"
    )
    deep_poll.add_argument("--now")
    _add_json_flag(deep_poll)
    deep_poll.set_defaults(handler=command_deep_poll)

    deep_timeout = subparsers.add_parser(
        "deep-timeout",
        help="free wall-clock check: move an accepted deep action to uncertain past its contract cap",
    )
    deep_timeout.add_argument("session")
    deep_timeout.add_argument("--action-id", required=True)
    deep_timeout.add_argument("--now")
    _add_json_flag(deep_timeout)
    deep_timeout.set_defaults(handler=command_deep_timeout)

    deep_pending = subparsers.add_parser(
        "deep-pending", help="free: list accepted/uncertain deep actions and their job tokens"
    )
    deep_pending.add_argument("session")
    _add_json_flag(deep_pending)
    deep_pending.set_defaults(handler=command_deep_pending)

    status = subparsers.add_parser("status", help="show canonical status and quota use")
    status.add_argument("session")
    _add_json_flag(status)
    status.set_defaults(handler=command_status)

    citations = subparsers.add_parser(
        "citations", help="free: harvest deduplicated citations for verification-stage sampling"
    )
    citations.add_argument("session")
    citations.add_argument("--action-id", help="limit to citations recorded on one retrieval occurrence")
    _add_json_flag(citations)
    citations.set_defaults(handler=command_citations)

    add = subparsers.add_parser("artifact-add", help="securely ingest local or fetched bytes")
    add.add_argument("session")
    add.add_argument("--source", required=True)
    add.add_argument("--artifact-id", required=True)
    add.add_argument("--media-type", required=True)
    add.add_argument("--origin-kind", required=True)
    add.add_argument("--action-id")
    add.add_argument("--supplied-by")
    add.add_argument("--source-id")
    add.add_argument("--fetch-occurrence-id")
    add.add_argument("--provider-id")
    add.add_argument("--attempt-id")
    add.add_argument("--sensitivity")
    add.add_argument("--retention", default="session")
    add.add_argument("--include-in-html", action="store_true")
    add.add_argument("--reviewed-by")
    add.add_argument("--reviewed-at")
    add.add_argument("--review-method")
    add.add_argument("--now")
    _add_json_flag(add)
    add.set_defaults(handler=command_artifact_add)

    promote = subparsers.add_parser(
        "promote", help="promote a boundary-spooled provider payload into the artifact index"
    )
    promote.add_argument("session")
    promote.add_argument("--action-id", required=True, help="the completed action whose occurrence to promote")
    promote.add_argument("--artifact-id", required=True)
    promote.add_argument("--retention", default="session")
    promote.add_argument("--include-in-html", action="store_true")
    promote.add_argument("--now")
    _add_json_flag(promote)
    promote.set_defaults(handler=command_promote)

    purge = subparsers.add_parser("artifact-purge", help="purge, revalidate, and rerender")
    purge.add_argument("session")
    purge.add_argument("--artifact-id", required=True)
    purge.add_argument("--reason", required=True)
    purge.add_argument("--requested-status", choices=("PARTIAL", "BLOCKED"), default="BLOCKED")
    purge.add_argument("--safe-action-id", action="append", default=[])
    purge.add_argument("--now")
    _add_json_flag(purge)
    purge.set_defaults(handler=command_artifact_purge)

    recover = subparsers.add_parser("recover", help="recover WAL and authorized pending purges")
    recover.add_argument("session")
    recover.add_argument("--now")
    _add_json_flag(recover)
    recover.set_defaults(handler=command_recover)

    validate = subparsers.add_parser("validate", help="run every deterministic gate")
    validate.add_argument("session")
    _add_json_flag(validate)
    validate.set_defaults(handler=command_validate)

    render = subparsers.add_parser("render", help="render deterministic report.html")
    render.add_argument("session")
    _add_json_flag(render)
    render.set_defaults(handler=command_render)

    view = subparsers.add_parser("view", help="open report.html in the default browser")
    view.add_argument("session")
    _add_json_flag(view)
    view.set_defaults(handler=command_view)
    return parser


def main(argv: list[str] | None = None) -> int:
    global _JSONArgumentParser_json_mode
    _load_dotenv_if_available()
    effective_argv = sys.argv[1:] if argv is None else list(argv)
    _JSONArgumentParser_json_mode = "--json" in effective_argv
    try:
        args = build_parser().parse_args(argv)
    finally:
        _JSONArgumentParser_json_mode = False
    try:
        payload, code = args.handler(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.json:
            print(
                json.dumps(
                    {"error": str(exc), "command": args.command},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        return 1
    if args.command == "providers" and not args.json:
        print(_format_provider_readiness(payload), end="")
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
