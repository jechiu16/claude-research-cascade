"""User-confirmed research contract normalization and validation."""

from __future__ import annotations

import copy
from typing import Any, Optional

from ._canon import is_count as _is_count, is_positive_count as _is_positive_count, sha256_hex
from .providers import (
    ProviderRegistryError,
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
    validate_provider_registry,
)


POSTURES = frozenset({"lookup", "synthesis", "scientific", "decision"})
TIERS = frozenset({"low", "medium", "high", "custom"})
EXECUTIONS = frozenset({"host_native", "external_managed"})
DURABILITIES = frozenset({"chat_only", "canonical_package"})
ACTION_CATEGORIES = (
    "probe",
    "deep",
    "processor",
    "network_experiment",
    "transport",
    "host_retrieval",
    "local",
    "organizer_pass",
)
METERED_CATEGORIES = (
    "probe",
    "deep",
    "processor",
    "network_experiment",
    "transport",
)


def normalize_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Copy a contract and fill only explicit zero-valued quota categories."""

    contract = copy.deepcopy(data)
    if not isinstance(contract, dict):
        return contract
    resource = contract.get("resource_envelope")
    if resource is None:
        resource = {}
        contract["resource_envelope"] = resource
    if not isinstance(resource, dict):
        contract.setdefault("stage_permit_map", [])
        contract.setdefault("confirmation", {})
        return contract
    physical = resource.setdefault("physical_ceiling", {})
    for category in ACTION_CATEGORIES:
        physical.setdefault(category, 0)
    external = resource.setdefault("external", {})
    metered = external.setdefault("metered_ceiling", {})
    for category in METERED_CATEGORIES:
        metered.setdefault(category, 0)
    contract.setdefault("stage_permit_map", [])
    contract.setdefault("confirmation", {})
    return contract


def contract_card_sha256(contract: dict[str, Any]) -> str:
    normalized = normalize_contract(contract)
    normalized.pop("confirmation", None)
    return sha256_hex(normalized)


def _confirmation_errors(
    contract: dict[str, Any],
    registry: dict[str, Any],
    resolved_registry_sha256: str,
    errors: list[str],
) -> None:
    confirmation = contract.get("confirmation")
    if not isinstance(confirmation, dict) or confirmation.get("confirmed_by") != "user" or not confirmation.get(
        "confirmed_at"
    ):
        errors.append("contract is not user-confirmed")
        return
    if confirmation.get("card_sha256") != contract_card_sha256(contract):
        errors.append("confirmed card hash does not match contract")
    if confirmation.get("registry_sha256") != resolved_registry_sha256:
        errors.append("confirmed registry hash does not match resolved registry")
    try:
        records = referenced_provider_records(contract, registry)
    except ProviderRegistryError:
        records = []
    if confirmation.get("referenced_records_sha256") != provider_records_sha256(records):
        errors.append("confirmed referenced-records hash does not match routes")


def _envelope_errors(resource: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Validate the physical/external/host/local envelopes; return the physical ceiling map."""

    physical = resource.get("physical_ceiling")
    if not isinstance(physical, dict):
        errors.append("physical ceiling is required")
        physical = {}
    for category in ACTION_CATEGORIES:
        if not _is_count(physical.get(category)):
            errors.append(f"physical ceiling {category} must be a non-negative integer")

    external = resource.get("external")
    if not isinstance(external, dict):
        errors.append("external resource envelope is required")
        external = {}
    metered = external.get("metered_ceiling")
    if not isinstance(metered, dict):
        errors.append("external metered ceiling is required")
        metered = {}
    for category in METERED_CATEGORIES:
        value = metered.get(category)
        if not _is_count(value):
            errors.append(f"metered ceiling {category} must be a non-negative integer")
        elif _is_count(physical.get(category)) and value > physical[category]:
            errors.append(f"metered ceiling {category} exceeds physical ceiling")
    if not _is_positive_count(external.get("max_wall_time_seconds")):
        errors.append("external max wall time must be a positive integer")
    if not isinstance(external.get("allowed_endpoint_classes"), list):
        errors.append("allowed endpoint classes must be a list")
    if not isinstance(external.get("local_file_egress"), bool):
        errors.append("local file egress policy must be boolean")
    endpoints = external.get("network_experiment_endpoints")
    if not isinstance(endpoints, list):
        errors.append("network experiment endpoints must be a list")
        endpoints = []
    if _is_count(physical.get("network_experiment")) and physical.get("network_experiment", 0) > 0 and not endpoints:
        errors.append("network experiment endpoint policy is required")
    if not _is_count(external.get("raw_storage_bytes")):
        errors.append("raw storage bytes must be a non-negative integer")

    host = resource.get("host")
    if not isinstance(host, dict):
        errors.append("host resource envelope is required")
    else:
        if host.get("context_class") not in {"lean", "standard", "extended"}:
            errors.append("host context class is invalid")
        for field in ("admitted_characters", "estimated_tokens"):
            if not _is_count(host.get(field)):
                errors.append(f"host {field} must be a non-negative integer")
    local = resource.get("local")
    if not isinstance(local, dict):
        errors.append("local resource envelope is required")
    else:
        if not _is_count(local.get("admitted_output_characters")):
            errors.append("local admitted output characters must be a non-negative integer")
        if not _is_positive_count(local.get("max_wall_time_seconds")):
            errors.append("local max wall time must be a positive integer")
        if local.get("network_egress") is not False:
            errors.append("local network egress must be false")
    return physical


def _mapping_errors(
    contract: dict[str, Any],
    registry: dict[str, Any],
    physical: dict[str, Any],
    errors: list[str],
) -> list[Any]:
    """Validate the stage permit map against routes and ceilings; return the mappings."""

    providers = {provider["id"]: provider for provider in registry.get("providers", []) if isinstance(provider, dict)}
    mappings = contract.get("stage_permit_map")
    if not isinstance(mappings, list):
        errors.append("stage permit map must be a list")
        mappings = []
    primary = [mapping for mapping in mappings if isinstance(mapping, dict) and mapping.get("stage") == "primary_scout"]
    if len(primary) != 1 or primary[0].get("invocations") != 1:
        errors.append("exactly one primary_scout mapping with one invocation is required")
    elif contract.get("scout_route") != primary[0].get("route"):
        errors.append("scout_route must match the primary_scout route")

    category_totals = {category: 0 for category in ACTION_CATEGORIES}
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            errors.append(f"stage mapping {index} must be an object")
            continue
        stage = mapping.get("stage")
        category = mapping.get("category")
        route = mapping.get("route")
        invocations = mapping.get("invocations")
        count = mapping.get("count")
        if not isinstance(stage, str) or not stage:
            errors.append(f"stage mapping {index} stage is required")
        if category not in ACTION_CATEGORIES:
            errors.append(f"stage mapping {index} category is invalid")
            continue
        if not _is_positive_count(invocations):
            errors.append(f"stage mapping {index} invocations must be a positive integer")
        if not _is_positive_count(count):
            errors.append(f"stage mapping {index} count must be a positive integer")
            continue
        category_totals[category] += count
        provider = providers.get(route)
        if provider is None or not provider.get("enabled", False):
            errors.append(f"route {route} is not enabled in capability registry")
            continue
        if category not in provider.get("action_categories", []) or stage not in provider.get(
            "stage_capabilities", []
        ):
            errors.append(f"route {route} does not support {stage}/{category}")
            continue
        multiplicity = provider.get("request_multiplicity", {}).get(category)
        if _is_positive_count(invocations) and _is_positive_count(multiplicity):
            expected = invocations * multiplicity
            if count != expected:
                errors.append(
                    f"route {route} invocation/count must be {invocations}/{expected} for {category}"
                )
    for category, total in category_totals.items():
        ceiling = physical.get(category)
        if _is_count(ceiling) and total > ceiling:
            errors.append(f"stage mappings exceed physical ceiling {category}")
    return mappings


def _reinforcement_errors(tier: Any, mappings: list[Any], errors: list[str]) -> None:
    reserved_reinforcement = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict)
        and mapping.get("reserved") is True
        and mapping.get("stage") in {"anti_lock_in", "verification", "coverage_audit"}
    ]
    if tier in {"medium", "high"} and not reserved_reinforcement:
        errors.append("medium and high tiers require reserved post-result reinforcement")
    context_verifiers = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict)
        and mapping.get("stage") == "context_separated_verification"
        and mapping.get("reserved") is True
        and mapping.get("category") == "organizer_pass"
    ]
    if tier == "high" and len(context_verifiers) != 1:
        errors.append("high tier requires reserved context-separated verifier capacity")


def _validate_contract_core(
    contract: dict[str, Any],
    registry: dict[str, Any],
    resolved_registry_sha256: str,
    *,
    allow_legacy_axes: bool = False,
) -> list[str]:
    errors: list[str] = []
    if contract.get("posture") not in POSTURES:
        errors.append("contract posture is invalid")
    if contract.get("tier") not in TIERS:
        errors.append("contract tier is invalid")
    has_execution = "execution" in contract
    has_durability = "durability" in contract
    if has_execution != has_durability:
        errors.append("contract execution and durability axes must be paired")
    elif not has_execution and not allow_legacy_axes:
        errors.append("contract execution and durability axes are required")
    elif has_execution:
        if contract.get("execution") not in EXECUTIONS:
            errors.append("contract execution axis is invalid")
        if contract.get("durability") not in DURABILITIES:
            errors.append("contract durability axis is invalid")
        elif contract.get("tier") == "low" and contract.get("durability") != "chat_only":
            errors.append("low tier requires chat_only durability")
        elif contract.get("tier") in {"medium", "high"} and contract.get("durability") != "canonical_package":
            errors.append("medium and high tiers require canonical_package durability")
    _confirmation_errors(contract, registry, resolved_registry_sha256, errors)

    resource = contract.get("resource_envelope")
    if not isinstance(resource, dict):
        errors.append("resource envelope is required")
        return errors
    physical = _envelope_errors(resource, errors)
    mappings = _mapping_errors(contract, registry, physical, errors)
    _reinforcement_errors(contract.get("tier"), mappings, errors)

    evidence_floor = contract.get("evidence_floor")
    if not isinstance(evidence_floor, dict) or not _is_positive_count(
        evidence_floor.get("minimum_load_bearing_claims") if isinstance(evidence_floor, dict) else None
    ):
        errors.append("evidence floor must require at least one load-bearing claim")
    return errors


def validate_contract(
    contract: dict[str, Any],
    registry: Optional[dict[str, Any]] = None,
    *,
    resolved_registry_sha256: Optional[str] = None,
) -> list[str]:
    if not isinstance(contract, dict):
        return ["contract must be an object"]
    normalized = normalize_contract(contract)
    resolved = copy.deepcopy(load_provider_registry() if registry is None else registry)
    registry_errors = validate_provider_registry(resolved)
    if registry_errors:
        return registry_errors
    registry_hash = resolved_registry_sha256 or provider_registry_sha256(resolved)
    return _validate_contract_core(normalized, resolved, registry_hash)


def _validate_persisted_contract(
    contract: dict[str, Any],
    registry: dict[str, Any],
    *,
    resolved_registry_sha256: Optional[str] = None,
) -> list[str]:
    """Validate an already-persisted contract while accepting legacy axes."""

    if not isinstance(contract, dict):
        return ["contract must be an object"]
    normalized = normalize_contract(contract)
    resolved = copy.deepcopy(registry)
    registry_errors = validate_provider_registry(resolved)
    if registry_errors:
        return registry_errors
    registry_hash = resolved_registry_sha256 or provider_registry_sha256(resolved)
    return _validate_contract_core(
        normalized,
        resolved,
        registry_hash,
        allow_legacy_axes=True,
    )
