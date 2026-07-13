"""Canonical v2 state construction, structural validation, and hashing."""

from __future__ import annotations

import copy
import os
import uuid
from typing import Any, Mapping, Optional

from ._canon import sha256_hex
from .contracts import normalize_contract, validate_contract, _validate_persisted_contract
from .providers import (
    load_provider_registry,
    preflight_contract_routes,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
    validate_provider_registry,
)


SCHEMA_VERSION = "2.0"
CONTRACT_SEMANTICS = "pure_trigger_v1"
REQUIRED_SECTIONS = (
    "schema_version",
    "session",
    "contract",
    "capabilities",
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
    "artifact_index",
)
ID_SECTIONS = (
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
    "open_questions",
    "verification",
    "artifact_index",
)


def state_sha256(state: dict[str, Any]) -> str:
    return sha256_hex(state)


def _session_id() -> str:
    return f"deep-{uuid.uuid4().hex}"


def new_state(
    question: str,
    contract: dict[str, Any],
    now: str,
    registry: Optional[dict[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if not isinstance(now, str) or not now:
        raise ValueError("now must be a non-empty timestamp")
    resolved = copy.deepcopy(load_provider_registry() if registry is None else registry)
    normalized = normalize_contract(contract)
    errors = validate_contract(normalized, resolved)
    preflight, preflight_errors = preflight_contract_routes(
        normalized,
        resolved,
        environ if environ is not None else os.environ,
    )
    errors.extend(preflight_errors)
    if errors:
        raise ValueError("invalid research contract: " + "; ".join(errors))
    providers = referenced_provider_records(normalized, resolved)
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session": {
            "id": _session_id(),
            "revision": 0,
            "created_at": now,
            "updated_at": now,
            "contract_semantics": CONTRACT_SEMANTICS,
        },
        "contract": normalized,
        "capabilities": {
            "registry_sha256": provider_registry_sha256(resolved),
            "referenced_records_sha256": provider_records_sha256(providers),
            "providers": providers,
            "preflight": preflight,
        },
        "framing": {"question": question.strip(), "assumptions": [], "exclusions": []},
        "summary": {
            "status": "IN_PROGRESS",
            "decision": "",
            "load_bearing_claim_ids": [],
            "human_recommendation": "",
            "human_status": "",
        },
        "hypotheses": [],
        "planned_checks": [],
        "observations": [],
        "retrieval_occurrences": [],
        "claims": [],
        "evidence": [],
        "sources": [],
        "source_origins": [],
        "branch_manifests": [],
        "evidence_deltas": [],
        "action_metrics": [],
        "inference_joints": [],
        "engineering_handoff": {"constraints": [], "safe_actions": [], "acceptance_tests": []},
        "open_questions": [],
        "verification": [],
        "artifact_index": [],
    }
    state_errors = validate_state_document(state)
    if state_errors:
        raise ValueError("new state is invalid: " + "; ".join(state_errors))
    return state


def _ids_for(state: dict[str, Any], section: str, errors: list[str]) -> set[str]:
    value = state.get(section)
    if not isinstance(value, list):
        errors.append(f"state section {section} must be a list")
        return set()
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            errors.append(f"state section {section} entries must be objects")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"state section {section} entry id is required")
            continue
        if item_id in seen:
            singular = section[:-1] if section.endswith("s") else section
            errors.append(f"duplicate {singular} id {item_id}")
        seen.add(item_id)
    return seen


_PREFLIGHT_FIELDS = frozenset(
    {"provider_id", "adapter", "adapter_version", "execution_binding", "required_env", "ready"}
)


def _preflight_errors(
    preflight: list[Any], providers: list[dict[str, Any]], errors: list[str]
) -> None:
    """Check that the preflight snapshot exactly mirrors the capability providers."""

    provider_map = {
        provider.get("id"): provider
        for provider in providers
        if isinstance(provider, dict) and isinstance(provider.get("id"), str)
    }
    preflight_provider_ids: list[str] = []
    for record in preflight:
        if not isinstance(record, dict):
            errors.append("capability preflight record must be an object")
            continue
        if not set(record) <= _PREFLIGHT_FIELDS:
            errors.append("capability preflight record contains forbidden fields")
        if set(record) != _PREFLIGHT_FIELDS:
            errors.append("capability preflight record is incomplete")
        provider_id = record.get("provider_id")
        if isinstance(provider_id, str):
            preflight_provider_ids.append(provider_id)
        provider = provider_map.get(provider_id)
        if provider is None:
            errors.append(f"capability preflight references missing provider {provider_id}")
        else:
            for field in ("adapter", "adapter_version", "execution_binding"):
                if record.get(field) != provider.get(field):
                    errors.append(f"capability preflight {field} mismatch for {provider_id}")
        env_records = record.get("required_env")
        if not isinstance(env_records, list):
            errors.append("capability preflight required_env must be a list")
            continue
        for env_record in env_records:
            if not isinstance(env_record, dict) or set(env_record) != {"name", "present"}:
                errors.append("capability preflight environment record is invalid")
            elif not isinstance(env_record.get("name"), str) or not isinstance(
                env_record.get("present"), bool
            ):
                errors.append("capability preflight environment record is invalid")
        if provider is not None:
            env_names = sorted(
                env_record.get("name")
                for env_record in env_records
                if isinstance(env_record, dict) and isinstance(env_record.get("name"), str)
            )
            if env_names != sorted(provider.get("required_env", [])):
                errors.append(f"capability preflight required_env mismatch for {provider_id}")
        if not isinstance(record.get("ready"), bool):
            errors.append("capability preflight ready must be boolean")
    if len(preflight_provider_ids) != len(set(preflight_provider_ids)):
        errors.append("capability preflight contains duplicate providers")
    if set(preflight_provider_ids) != set(provider_map):
        errors.append("capability preflight provider set mismatch")


def validate_state_document(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state must be an object"]
    for section in REQUIRED_SECTIONS:
        if section not in state:
            errors.append(f"state section {section} is required")
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"state schema_version must be {SCHEMA_VERSION}")

    session = state.get("session")
    session_semantics = session.get("contract_semantics") if isinstance(session, dict) else None
    if not isinstance(session, dict):
        errors.append("state session must be an object")
    else:
        revision = session.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            errors.append("session revision must be a non-negative integer")
        for field in ("id", "created_at", "updated_at"):
            if not isinstance(session.get(field), str) or not session.get(field):
                errors.append(f"session {field} is required")
        if session_semantics not in {None, CONTRACT_SEMANTICS}:
            errors.append("session contract_semantics is invalid")

    capabilities = state.get("capabilities")
    providers: list[dict[str, Any]] = []
    if not isinstance(capabilities, dict):
        errors.append("state capabilities must be an object")
    else:
        providers_value = capabilities.get("providers")
        if isinstance(providers_value, list):
            providers = providers_value
            expected_records_hash = provider_records_sha256(providers)
            if capabilities.get("referenced_records_sha256") != expected_records_hash:
                errors.append("capability referenced-records hash mismatch")
        else:
            errors.append("capability providers must be a list")
        if not isinstance(capabilities.get("registry_sha256"), str):
            errors.append("capability registry_sha256 is required")
        if not isinstance(capabilities.get("preflight"), list):
            errors.append("capability preflight must be a list")
        else:
            _preflight_errors(capabilities["preflight"], providers, errors)

    contract = state.get("contract")
    if isinstance(contract, dict) and capabilities and providers:
        confirmation = contract.get("confirmation", {})
        if confirmation.get("registry_sha256") != capabilities.get("registry_sha256"):
            errors.append("capability registry hash does not match confirmation")
        if confirmation.get("referenced_records_sha256") != capabilities.get("referenced_records_sha256"):
            errors.append("capability records hash does not match confirmation")
        snapshot_registry = {"schema_version": "1.0", "providers": copy.deepcopy(providers)}
        registry_errors = validate_provider_registry(snapshot_registry)
        errors.extend(f"capability snapshot: {error}" for error in registry_errors)
        contract_errors = (
            validate_contract
            if session_semantics
            else _validate_persisted_contract
        )
        errors.extend(
            f"contract: {error}"
            for error in contract_errors(
                contract,
                snapshot_registry,
                resolved_registry_sha256=capabilities.get("registry_sha256"),
            )
        )
    elif not isinstance(contract, dict):
        errors.append("state contract must be an object")

    ids: dict[str, set[str]] = {}
    for section in ID_SECTIONS:
        if section in state:
            ids[section] = _ids_for(state, section, errors)

    evidence_ids = ids.get("evidence", set())
    claim_ids = ids.get("claims", set())
    summary = state.get("summary")
    if not isinstance(summary, dict):
        errors.append("state summary must be an object")
    else:
        load_bearing_ids = summary.get("load_bearing_claim_ids")
        if not isinstance(load_bearing_ids, list):
            errors.append("summary load_bearing_claim_ids must be a list")
        else:
            for claim_id in load_bearing_ids:
                if claim_id not in claim_ids:
                    errors.append(f"summary references missing claim {claim_id}")
    for claim in state.get("claims", []) if isinstance(state.get("claims"), list) else []:
        if not isinstance(claim, dict) or not isinstance(claim.get("id"), str):
            continue
        for evidence_id in claim.get("supporting_evidence_ids", []):
            if evidence_id not in evidence_ids:
                errors.append(f"claim {claim['id']} references missing evidence {evidence_id}")
        for evidence_id in claim.get("counter_evidence_ids", []):
            if evidence_id not in evidence_ids:
                errors.append(f"claim {claim['id']} references missing evidence {evidence_id}")

    source_ids = ids.get("sources", set())
    artifact_ids = ids.get("artifact_index", set())
    for evidence in state.get("evidence", []) if isinstance(state.get("evidence"), list) else []:
        if not isinstance(evidence, dict) or not isinstance(evidence.get("id"), str):
            continue
        source_id = evidence.get("source_id")
        artifact_id = evidence.get("artifact_id")
        if source_id is not None and source_id not in source_ids:
            errors.append(f"evidence {evidence['id']} references missing source {source_id}")
        if artifact_id is not None and artifact_id not in artifact_ids:
            errors.append(f"evidence {evidence['id']} references missing artifact {artifact_id}")

    origin_ids = ids.get("source_origins", set())
    for source in state.get("sources", []) if isinstance(state.get("sources"), list) else []:
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            continue
        origin_id = source.get("origin_id")
        if origin_id is not None and origin_id not in origin_ids:
            errors.append(f"source {source['id']} references missing origin {origin_id}")

    provider_ids = {provider.get("id") for provider in providers if isinstance(provider, dict)}
    for occurrence in (
        state.get("retrieval_occurrences", [])
        if isinstance(state.get("retrieval_occurrences"), list)
        else []
    ):
        if not isinstance(occurrence, dict) or not isinstance(occurrence.get("id"), str):
            continue
        provider_id = occurrence.get("provider_id")
        if provider_id is not None and provider_id not in provider_ids:
            errors.append(f"retrieval occurrence {occurrence['id']} references missing provider {provider_id}")
    return errors
