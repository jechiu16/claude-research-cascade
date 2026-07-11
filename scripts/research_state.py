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

from research_harness.artifacts import ingest_fetched_source, ingest_local_artifact
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
from research_harness.quota import acquire_permits, permit_usage
from research_harness.rendering import render_session_result
from research_harness.state import new_state, state_sha256
from research_harness.storage import apply_state_patch, create_session, load_state
from research_harness.validation import validate_session


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    contract = normalize_contract(_read_json(args.contract))
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
    return report.to_dict(), 0 if report.ok else 1


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
    parser = argparse.ArgumentParser(description="Canonical v2 research session runtime")
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

    status = subparsers.add_parser("status", help="show canonical status and quota use")
    status.add_argument("session")
    _add_json_flag(status)
    status.set_defaults(handler=command_status)

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
    args = build_parser().parse_args(argv)
    try:
        payload, code = args.handler(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
