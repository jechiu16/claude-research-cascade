from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from research_harness.contracts import contract_card_sha256, normalize_contract
from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
)


NOW = "2026-07-10T12:00:00Z"


def draft_medium_contract() -> dict[str, Any]:
    return {
        "posture": "lookup",
        "tier": "medium",
        "scout_route": "host-web",
        "resource_envelope": {
            "physical_ceiling": {
                "probe": 0,
                "deep": 0,
                "processor": 0,
                "network_experiment": 0,
                "transport": 0,
                "host_retrieval": 3,
                "local": 1,
                "organizer_pass": 1,
            },
            "external": {
                "metered_ceiling": {
                    "probe": 0,
                    "deep": 0,
                    "processor": 0,
                    "network_experiment": 0,
                    "transport": 0,
                },
                "max_wall_time_seconds": 3600,
                "allowed_endpoint_classes": [],
                "local_file_egress": False,
                "network_experiment_endpoints": [],
                "estimated_spend_usd": {
                    "minimum": 0.0,
                    "maximum": 0.0,
                    "hard_cap": False,
                },
                "raw_storage_bytes": 10 * 1024 * 1024,
            },
            "host": {
                "context_class": "standard",
                "admitted_characters": 24000,
                "estimated_tokens": 6000,
            },
            "local": {
                "admitted_output_characters": 12000,
                "max_wall_time_seconds": 900,
                "network_egress": False,
            },
        },
        "stage_permit_map": [
            {
                "stage": "primary_scout",
                "category": "host_retrieval",
                "route": "host-web",
                "invocations": 1,
                "count": 1,
                "reserved": False,
            },
            {
                "stage": "local_applicability",
                "category": "local",
                "route": "local",
                "invocations": 1,
                "count": 1,
                "reserved": False,
            },
            {
                "stage": "anti_lock_in",
                "category": "host_retrieval",
                "route": "host-web",
                "invocations": 1,
                "count": 1,
                "reserved": True,
            },
            {
                "stage": "verification",
                "category": "host_retrieval",
                "route": "host-web",
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
        ],
        "evidence_floor": {
            "minimum_load_bearing_claims": 1,
            "require_raw_artifacts": True,
        },
        "artifact_policy": {
            "default_retention": "session",
            "allow_provider_payloads": False,
        },
        "confirmation": {
            "confirmed_by": None,
            "confirmed_at": None,
            "card_sha256": None,
            "registry_sha256": None,
            "referenced_records_sha256": None,
        },
    }


def confirmed_medium_contract(
    registry: dict[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    del environ  # Current no-network routes do not require environment keys.
    resolved = copy.deepcopy(load_provider_registry() if registry is None else registry)
    contract = normalize_contract(draft_medium_contract())
    records = referenced_provider_records(contract, resolved)
    contract["confirmation"] = {
        "confirmed_by": "user",
        "confirmed_at": NOW,
        "card_sha256": contract_card_sha256(contract),
        "registry_sha256": provider_registry_sha256(resolved),
        "referenced_records_sha256": provider_records_sha256(records),
    }
    return contract


def confirmed_contract(
    tier: str = "medium",
    posture: str = "lookup",
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = copy.deepcopy(load_provider_registry() if registry is None else registry)
    contract = normalize_contract(draft_medium_contract())
    contract["tier"] = tier
    contract["posture"] = posture
    if tier == "high":
        contract["resource_envelope"]["physical_ceiling"]["organizer_pass"] = 2
        contract["stage_permit_map"].append(
            {
                "stage": "context_separated_verification",
                "category": "organizer_pass",
                "route": "host",
                "invocations": 1,
                "count": 1,
                "reserved": True,
            }
        )
    records = referenced_provider_records(contract, resolved)
    contract["confirmation"] = {
        "confirmed_by": "user",
        "confirmed_at": NOW,
        "card_sha256": contract_card_sha256(contract),
        "registry_sha256": provider_registry_sha256(resolved),
        "referenced_records_sha256": provider_records_sha256(records),
    }
    return contract


def confirmed_demo_contract(
    route: str = "demo-probe",
    request_count: int = 1,
    probe_ceiling: int = 2,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = copy.deepcopy(load_provider_registry() if registry is None else registry)
    contract = draft_medium_contract()
    contract["tier"] = "custom"
    contract["scout_route"] = route
    contract["resource_envelope"]["physical_ceiling"].update(
        {"probe": probe_ceiling, "host_retrieval": 0}
    )
    contract["stage_permit_map"] = [
        {
            "stage": "primary_scout",
            "category": "probe",
            "route": route,
            "invocations": 1,
            "count": request_count,
            "reserved": False,
        },
        {
            "stage": "local_applicability",
            "category": "local",
            "route": "local",
            "invocations": 1,
            "count": 1,
            "reserved": False,
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
    records = referenced_provider_records(contract, resolved)
    contract["confirmation"] = {
        "confirmed_by": "user",
        "confirmed_at": NOW,
        "card_sha256": contract_card_sha256(contract),
        "registry_sha256": provider_registry_sha256(resolved),
        "referenced_records_sha256": provider_records_sha256(records),
    }
    return contract


def write_overlay(path: Path, providers: list[dict[str, Any]]) -> Path:
    import json

    path.write_text(
        json.dumps({"schema_version": "1.0", "providers": providers}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def append_valid_test_event_line(session_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append a correctly chained hostile fixture without exporting a production bypass."""

    events_path = Path(session_dir) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    prepared = copy.deepcopy(event)
    prepared.pop("event_hash", None)
    prepared["seq"] = len(events) + 1
    prepared["prev_hash"] = events[-1]["event_hash"] if events else None
    payload = json.dumps(
        prepared, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    prepared["event_hash"] = hashlib.sha256(payload).hexdigest()
    line = json.dumps(
        prepared, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"
    fd = os.open(events_path, os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    return prepared


def _complete_action(session: Path, action_id: str) -> None:
    from research_harness.quota import record_attempt_status

    record_attempt_status(session, action_id, "attempted", NOW)
    record_attempt_status(session, action_id, "accepted", NOW)
    record_attempt_status(session, action_id, "completed", NOW)


def make_complete_pass_session(
    root: Path,
    tier: str = "medium",
    posture: str = "lookup",
    *,
    safe_action: bool = False,
) -> Path:
    from research_harness.artifacts import ingest_fetched_source
    from research_harness.quota import acquire_permits
    from research_harness.state import new_state
    from research_harness.storage import apply_state_patch, create_session, load_state

    root = Path(root)
    registry = load_provider_registry()
    contract = confirmed_contract(tier, posture, registry)
    session = root / f"complete-{tier}-{posture}-{uuid.uuid4().hex[:8]}"
    create_session(session, new_state("Choose a bounded implementation", contract, NOW, registry, {}))

    actions = [
        ("A1", "primary_scout", "host_retrieval", "host-web"),
        ("L1", "local_applicability", "local", "local"),
        ("A2", "anti_lock_in", "host_retrieval", "host-web"),
        ("A3", "verification", "host_retrieval", "host-web"),
    ]
    if tier == "high":
        actions.append(("O1", "context_separated_verification", "organizer_pass", "host"))
    for action_id, stage, category, route in actions:
        acquire_permits(
            session,
            action_id,
            stage,
            category,
            route,
            1,
            f"sha256:{action_id.lower()}",
            NOW,
        )
        _complete_action(session, action_id)

    state = load_state(session)
    apply_state_patch(
        session,
        [
            {
                "op": "add",
                "path": "/source_origins/-",
                "value": {"id": "O1", "kind": "primary-authority", "independent": True},
            },
            {
                "op": "add",
                "path": "/sources/-",
                "value": {
                    "id": "S1",
                    "origin_id": "O1",
                    "tier": "T1",
                    "title": "Authoritative fixture",
                    "url": "https://example.test/authoritative",
                    "direct_fetch": True,
                },
            },
            {
                "op": "add",
                "path": "/retrieval_occurrences/-",
                "value": {
                    "id": "R1",
                    "provider_id": "host-web",
                    "source_id": "S1",
                    "action_id": "A1",
                    "retrieved_at": NOW,
                },
            },
        ],
        state["session"]["revision"],
        NOW,
    )

    source_path = root / f"fixture-{uuid.uuid4().hex[:8]}.txt"
    source_bytes = b"Authoritative bounded finding.\n"
    source_path.write_bytes(source_bytes)
    ingest_fetched_source(
        session,
        source_path,
        "A1",
        "text/plain",
        "S1",
        "R1",
        "public",
        "session",
        False,
        NOW,
    )

    verification: list[dict[str, Any]] = [
        {"id": "V1", "kind": "primary_check", "completed": True, "action_id": "A3"}
    ]
    if posture in {"scientific", "decision"} and tier in {"medium", "high"}:
        verification.extend(
            [
                {"id": "V2", "kind": "anti_lock_in", "completed": True, "action_id": "A2"},
                {
                    "id": "V3",
                    "kind": "coverage_audit",
                    "completed": True,
                    "candidate_omissions_dispositioned": True,
                    "action_id": "A3",
                },
            ]
        )
    if tier == "high":
        verification.append(
            {
                "id": "V4",
                "kind": "verifier",
                "completed": True,
                "context_separated": True,
                "produced_candidate": False,
                "action_id": "O1",
            }
        )

    operations: list[dict[str, Any]] = [
        {
            "op": "add",
            "path": "/evidence/-",
            "value": {
                "id": "E1",
                "artifact_id": "A1",
                "source_id": "S1",
                "origin_id": "O1",
                "source_tier": "T1",
                "excerpt": source_bytes.decode("utf-8"),
                "excerpt_start": 0,
                "excerpt_end": len(source_bytes),
                "entailment": "entailed",
                "applicability": "checked",
                "retrieved_at": NOW,
            },
        },
        {
            "op": "add",
            "path": "/claims/-",
            "value": {
                "id": "C1",
                "text": "The bounded finding applies to this decision.",
                "scope": "fixture environment",
                "qualifiers": [],
                "load_bearing": True,
                "claim_type": "source-of-record",
                "status": "corroborated",
                "supporting_evidence_ids": ["E1"],
                "counter_evidence_ids": [],
                "source_origin_ids": ["O1"],
                "applicability": "checked",
                "would_change_if": "the authoritative source changes",
                "engineering_implication_ids": [],
            },
        },
        {"op": "replace", "path": "/summary/status", "value": "PASS"},
        {
            "op": "replace",
            "path": "/summary/decision",
            "value": "Use the bounded reversible implementation.",
        },
        {
            "op": "replace",
            "path": "/summary/load_bearing_claim_ids",
            "value": ["C1"],
        },
    ]
    operations.extend(
        {"op": "add", "path": "/verification/-", "value": record}
        for record in verification
    )
    if posture == "decision":
        operations.append(
            {
                "op": "add",
                "path": "/inference_joints/-",
                "value": {
                    "id": "J1",
                    "claim_ids": ["C1"],
                    "adversarially_reviewed": True,
                    "weakest_joint": True,
                },
            }
        )
    if safe_action:
        operations.append(
            {
                "op": "add",
                "path": "/engineering_handoff/safe_actions/-",
                "value": {
                    "id": "SA1",
                    "description": "Run a reversible spike",
                    "reversible": True,
                    "depends_on_claim_ids": [],
                },
            }
        )
    state = load_state(session)
    apply_state_patch(session, operations, state["session"]["revision"], NOW)
    return session


def make_incomplete_session(
    root: Path,
    tier: str = "medium",
    posture: str = "lookup",
    requested_status: str = "PASS",
) -> Path:
    from research_harness.storage import apply_state_patch, load_state

    session = make_complete_pass_session(root, tier, posture)
    artifact = load_state(session)["artifact_index"][0]
    (session / artifact["relative_path"]).unlink()
    state = load_state(session)
    operations: list[dict[str, Any]] = [
        {"op": "replace", "path": "/summary/status", "value": requested_status}
    ]
    if tier == "high":
        verifier_index = next(
            index
            for index, record in enumerate(state["verification"])
            if record.get("kind") == "verifier"
        )
        operations.append({"op": "remove", "path": f"/verification/{verifier_index}"})
    apply_state_patch(session, operations, state["session"]["revision"], NOW)
    return session


def make_partial_session(root: Path, safe_action: bool) -> Path:
    from research_harness.storage import apply_state_patch, load_state

    session = make_complete_pass_session(root, "medium", "lookup", safe_action=safe_action)
    state = load_state(session)
    apply_state_patch(
        session,
        [
            {"op": "replace", "path": "/summary/status", "value": "PARTIAL"},
            {"op": "replace", "path": "/claims/0/status", "value": "unverified"},
        ],
        state["session"]["revision"],
        NOW,
    )
    return session


def make_session_with_demo_evidence(root: Path) -> Path:
    from research_harness.artifacts import ingest_fetched_source
    from research_harness.quota import acquire_permits
    from research_harness.state import new_state
    from research_harness.storage import apply_state_patch, create_session, load_state

    root = Path(root)
    registry = load_provider_registry()
    contract = confirmed_demo_contract(registry=registry)
    session = root / f"demo-evidence-{uuid.uuid4().hex[:8]}"
    create_session(session, new_state("demo evidence must fail", contract, NOW, registry, {}))
    acquire_permits(
        session, "D1", "primary_scout", "probe", "demo-probe", 1, "sha256:demo", NOW
    )
    _complete_action(session, "D1")
    state = load_state(session)
    apply_state_patch(
        session,
        [
            {"op": "add", "path": "/source_origins/-", "value": {"id": "O1"}},
            {
                "op": "add",
                "path": "/sources/-",
                "value": {"id": "S1", "origin_id": "O1", "tier": "T1", "direct_fetch": True},
            },
            {
                "op": "add",
                "path": "/retrieval_occurrences/-",
                "value": {
                    "id": "R1",
                    "provider_id": "demo-probe",
                    "source_id": "S1",
                    "action_id": "D1",
                },
            },
        ],
        state["session"]["revision"],
        NOW,
    )
    source = root / f"demo-{uuid.uuid4().hex[:8]}.txt"
    source.write_text("demo cannot support evidence\n", encoding="utf-8")
    artifact = ingest_fetched_source(
        session, source, "A1", "text/plain", "S1", "R1", "public", "session", False, NOW
    )
    raw = (session / artifact["relative_path"]).read_bytes()
    state = load_state(session)
    apply_state_patch(
        session,
        [
            {
                "op": "add",
                "path": "/evidence/-",
                "value": {
                    "id": "E1",
                    "artifact_id": "A1",
                    "source_id": "S1",
                    "origin_id": "O1",
                    "source_tier": "T1",
                    "excerpt": raw.decode("utf-8"),
                    "excerpt_start": 0,
                    "excerpt_end": len(raw),
                    "entailment": "entailed",
                    "applicability": "checked",
                },
            },
            {
                "op": "add",
                "path": "/claims/-",
                "value": {
                    "id": "C1",
                    "load_bearing": True,
                    "status": "corroborated",
                    "supporting_evidence_ids": ["E1"],
                    "counter_evidence_ids": [],
                    "source_origin_ids": ["O1"],
                    "applicability": "checked",
                },
            },
            {"op": "replace", "path": "/summary/status", "value": "PASS"},
            {"op": "replace", "path": "/summary/decision", "value": "Invalid demo answer"},
            {
                "op": "replace",
                "path": "/summary/load_bearing_claim_ids",
                "value": ["C1"],
            },
        ],
        state["session"]["revision"],
        NOW,
    )
    return session
