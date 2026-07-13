"""User-confirmed research contract normalization and validation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Optional

from ._canon import (
    canonical_question,
    is_count as _is_count,
    is_positive_count as _is_positive_count,
    sha256_hex,
)
from .budgets import resolve_budget_profile
from .providers import (
    ProviderRegistryError,
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
    validate_provider_registry,
)


POSTURES = frozenset({"lookup", "synthesis", "scientific", "decision"})
TIERS = frozenset({"low", "medium", "high", "ultra", "custom"})
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
HOST_LED_WORKFLOW = "host_led_v1"


def draft_host_led_contract(
    question: str,
    posture: str,
    profile_name: str,
    registry: dict[str, Any],
    environ: Mapping[str, str],
    *,
    profile_path: Optional[Path] = None,
    deep_routes: Optional[list[str]] = None,
    search_routes: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build one unconfirmed host-led contract from classes, not a fixed pipeline."""

    profile = resolve_budget_profile(profile_name, profile_path)
    providers = {
        provider["id"]: provider
        for provider in registry.get("providers", [])
        if isinstance(provider, dict) and isinstance(provider.get("id"), str)
    }

    def ready(provider: dict[str, Any]) -> bool:
        return provider.get("enabled") is True and all(
            bool(environ.get(name)) for name in provider.get("required_env", [])
        )

    def eligible(provider_id: str, cost_class: str, category: str, stage: str) -> bool:
        provider = providers.get(provider_id)
        return bool(
            provider
            and ready(provider)
            and provider.get("cost_class") == cost_class
            and category in provider.get("action_categories", [])
            and stage in provider.get("stage_capabilities", [])
        )

    deep_count = profile["deep"]
    chosen_deep = list(deep_routes or [])
    if deep_count == 0 and chosen_deep:
        raise ValueError("light profile cannot name a deep route")
    if deep_count > 0:
        if not chosen_deep:
            candidates = sorted(
                (
                    provider
                    for provider in providers.values()
                    if eligible(provider["id"], "deep", "deep", "investigation")
                ),
                key=lambda provider: (provider["cost_rank"], provider["id"]),
            )
            if not candidates:
                raise ValueError("selected profile requires a ready deep provider")
            chosen_deep = [candidates[0]["id"]]
        if len(chosen_deep) not in {1, deep_count}:
            raise ValueError("deep routes must contain one reusable route or one route per deep call")
        if len(chosen_deep) == 1:
            chosen_deep *= deep_count
        for index, route in enumerate(chosen_deep):
            stage = "investigation" if index == 0 else "anti_lock_in"
            if not eligible(route, "deep", "deep", stage):
                raise ValueError(f"deep route {route} is not ready for {stage}")

    if search_routes is None:
        chosen_search = sorted(
            provider["id"]
            for provider in providers.values()
            if eligible(provider["id"], "search", "probe", "verification")
        )
    else:
        chosen_search = list(dict.fromkeys(search_routes))
    for route in chosen_search:
        if not eligible(route, "search", "probe", "verification"):
            raise ValueError(f"search route {route} is not ready for verification")

    search_capacity = profile["search"] * len(chosen_search)
    physical = {
        "probe": search_capacity,
        "deep": deep_count,
        "processor": 0,
        "network_experiment": 0,
        "transport": 20 * deep_count,
        "host_retrieval": 3,
        "local": 1,
        "organizer_pass": 1,
    }
    mappings: list[dict[str, Any]] = [
        {
            "stage": "primary_scout", "category": "host_retrieval", "route": "host-web",
            "invocations": 1, "count": 1, "reserved": False,
        },
        {
            "stage": "local_applicability", "category": "local", "route": "local",
            "invocations": 1, "count": 1, "reserved": False,
        },
        {
            "stage": "anti_lock_in", "category": "host_retrieval", "route": "host-web",
            "invocations": 1, "count": 1, "reserved": True,
        },
        {
            "stage": "verification", "category": "host_retrieval", "route": "host-web",
            "invocations": 1, "count": 1, "reserved": True,
        },
        {
            "stage": "final_inference_review", "category": "organizer_pass", "route": "host",
            "invocations": 1, "count": 1, "reserved": True,
        },
    ]
    mappings.extend(
        {
            "stage": "verification", "category": "probe", "route": route,
            "invocations": profile["search"], "count": profile["search"], "reserved": True,
        }
        for route in chosen_search
        if profile["search"] > 0
    )
    for index, route in enumerate(chosen_deep):
        stage = "investigation" if index == 0 else "anti_lock_in"
        mappings.extend(
            [
                {
                    "stage": stage, "category": "deep", "route": route,
                    "invocations": 1, "count": 1, "reserved": index > 0,
                    "marginal_purpose": (
                        "expand the primary research frame"
                        if index == 0
                        else "challenge or materially extend the current frame"
                    ),
                },
                {
                    "stage": stage, "category": "transport", "route": route,
                    "invocations": 20, "count": 20, "reserved": True,
                },
            ]
        )

    return normalize_contract(
        {
            "question": question,
            "posture": posture,
            "tier": "custom",
            "execution": "external_managed",
            "durability": "canonical_package",
            "research_workflow": HOST_LED_WORKFLOW,
            "conclusion_author": "host",
            "provider_reports_role": "discovery_only",
            "scout_route": "host-web",
            "resource_envelope": {
                "cost_budget": profile,
                "physical_ceiling": physical,
                "external": {
                    "metered_ceiling": {
                        "probe": search_capacity,
                        "deep": deep_count,
                        "processor": 0,
                        "network_experiment": 0,
                        "transport": 0,
                    },
                    "max_wall_time_seconds": 7200,
                    "allowed_endpoint_classes": [],
                    "local_file_egress": False,
                    "network_experiment_endpoints": [],
                    "estimated_spend_usd": {"minimum": 0.0, "maximum": 0.0, "hard_cap": False},
                    "raw_storage_bytes": 20 * 1024 * 1024,
                },
                "host": {
                    "context_class": "standard",
                    "admitted_characters": 32000,
                    "estimated_tokens": 8000,
                },
                "local": {
                    "admitted_output_characters": 16000,
                    "max_wall_time_seconds": 1200,
                    "network_egress": False,
                },
            },
            "stage_permit_map": mappings,
            "evidence_floor": {"minimum_load_bearing_claims": 1, "require_raw_artifacts": True},
            "artifact_policy": {"default_retention": "session", "allow_provider_payloads": False},
            "confirmation": {},
        }
    )


def normalize_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Copy a contract and fill only explicit zero-valued quota categories."""

    contract = copy.deepcopy(data)
    if not isinstance(contract, dict):
        return contract
    if "question" in contract:
        try:
            contract["question"] = canonical_question(contract["question"])
        except ValueError:
            # Keep malformed input available for validation instead of leaking
            # a normalization exception from a public validation path.
            pass
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


def _host_led_budget_errors(
    contract: dict[str, Any], registry: dict[str, Any], mappings: list[Any], errors: list[str]
) -> None:
    if contract.get("research_workflow") != HOST_LED_WORKFLOW:
        return
    if contract.get("tier") != "custom":
        errors.append("host-led workflow uses custom tier compatibility semantics")
    if contract.get("durability") != "canonical_package":
        errors.append("host-led workflow requires canonical_package durability")
    if contract.get("conclusion_author") != "host":
        errors.append("host-led workflow requires conclusion_author=host")
    if contract.get("provider_reports_role") != "discovery_only":
        errors.append("host-led workflow requires provider_reports_role=discovery_only")

    budget = contract.get("resource_envelope", {}).get("cost_budget")
    if not isinstance(budget, dict):
        errors.append("host-led workflow requires a cost budget")
        return
    if set(budget) != {"profile", "deep", "search", "free"}:
        errors.append("cost budget must contain exactly profile, deep, search, and free")
        return
    if not isinstance(budget.get("profile"), str) or not budget["profile"]:
        errors.append("cost budget profile must be a non-empty string")
    for cost_class in ("deep", "search"):
        if not _is_count(budget.get(cost_class)):
            errors.append(f"cost budget {cost_class} must be a non-negative integer")
    if budget.get("free") != "unlimited":
        errors.append("cost budget free must be unlimited")

    providers = {
        provider.get("id"): provider
        for provider in registry.get("providers", [])
        if isinstance(provider, dict)
    }
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        provider = providers.get(mapping.get("route"))
        count = mapping.get("count")
        if provider is None or not _is_positive_count(count):
            continue
        if mapping.get("category") == "deep" and provider.get(
            "evidence_capabilities", {}
        ).get("can_support_claims") is not False:
            errors.append(f"deep route {mapping.get('route')} must be discovery-only")

    final_passes = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict)
        and mapping.get("stage") == "final_inference_review"
        and mapping.get("category") == "organizer_pass"
        and mapping.get("route") == "host"
    ]
    if len(final_passes) != 1:
        errors.append("host-led workflow requires one host final_inference_review mapping")
    reverification = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict)
        and mapping.get("stage") == "verification"
        and mapping.get("reserved") is True
    ]
    if not reverification:
        errors.append("host-led workflow requires reserved targeted re-verification")


def _reinforcement_errors(tier: Any, mappings: list[Any], errors: list[str]) -> None:
    reserved_reinforcement = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict)
        and mapping.get("reserved") is True
        and mapping.get("stage") in {"anti_lock_in", "verification", "coverage_audit"}
    ]
    if tier in {"medium", "high", "ultra"} and not reserved_reinforcement:
        errors.append("Medium, High, and Ultra tiers require reserved post-result reinforcement")
    context_verifiers = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict)
        and mapping.get("stage") == "context_separated_verification"
        and mapping.get("reserved") is True
        and mapping.get("category") == "organizer_pass"
    ]
    if tier in {"high", "ultra"} and len(context_verifiers) != 1:
        errors.append("High and Ultra tiers require reserved context-separated verifier capacity")


def _ultra_submission_errors(
    mappings: list[Any], physical: dict[str, Any], resource: dict[str, Any], errors: list[str]
) -> None:
    """Require the bounded one-or-two-shot deep plan for Ultra."""

    deep_mappings = [
        mapping
        for mapping in mappings
        if isinstance(mapping, dict) and mapping.get("category") == "deep"
    ]
    deep_count = len(deep_mappings)
    if deep_count not in {1, 2}:
        errors.append("Ultra tier requires one or two deep submission mappings")
        return
    if physical.get("deep") != deep_count:
        errors.append("Ultra physical deep ceiling must equal the deep mapping count")
    metered_deep = resource.get("external", {}).get("metered_ceiling", {}).get("deep")
    if metered_deep != deep_count:
        errors.append("Ultra external deep ceiling must equal the deep mapping count")

    for index, mapping in enumerate(deep_mappings, start=1):
        if mapping.get("invocations") != 1 or mapping.get("count") != 1:
            errors.append(f"Ultra deep submission {index} requires invocations=1 and count=1")
        matching_transport = [
            candidate
            for candidate in mappings
            if isinstance(candidate, dict)
            and candidate.get("category") == "transport"
            and candidate.get("stage") == mapping.get("stage")
            and candidate.get("route") == mapping.get("route")
        ]
        if len(matching_transport) != 1:
            errors.append(
                f"Ultra deep submission {index} requires exactly one matching transport mapping"
            )
    if deep_mappings[0].get("stage") != "investigation":
        errors.append("Ultra first deep submission must use investigation stage")
    if len(deep_mappings) == 2:
        second = deep_mappings[1]
        if second.get("stage") != "anti_lock_in":
            errors.append("Ultra second deep submission must use anti_lock_in stage")
        if second.get("reserved") is not True:
            errors.append("Ultra second deep submission must be reserved")


def _validate_contract_core(
    contract: dict[str, Any],
    registry: dict[str, Any],
    resolved_registry_sha256: str,
    *,
    allow_legacy_axes: bool = False,
    allow_legacy_question: bool = False,
) -> list[str]:
    errors: list[str] = []
    question = contract.get("question")
    if question is None:
        if not allow_legacy_question:
            errors.append("contract question is required")
    else:
        try:
            canonical_question(question)
        except ValueError as exc:
            errors.append(f"contract question is invalid: {exc}")
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
        elif contract.get("tier") in {"medium", "high", "ultra"} and contract.get("durability") != "canonical_package":
            errors.append("Medium, High, and Ultra tiers require canonical_package durability")
    _confirmation_errors(contract, registry, resolved_registry_sha256, errors)

    resource = contract.get("resource_envelope")
    if not isinstance(resource, dict):
        errors.append("resource envelope is required")
        return errors
    physical = _envelope_errors(resource, errors)
    mappings = _mapping_errors(contract, registry, physical, errors)
    _reinforcement_errors(contract.get("tier"), mappings, errors)
    _host_led_budget_errors(contract, registry, mappings, errors)
    if contract.get("tier") == "ultra":
        _ultra_submission_errors(mappings, physical, resource, errors)

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
        allow_legacy_question=True,
    )


def _validate_persisted_contract_v1(
    contract: dict[str, Any],
    registry: dict[str, Any],
    *,
    resolved_registry_sha256: Optional[str] = None,
) -> list[str]:
    """Validate a persisted v1 contract: axes required, question optional."""

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
        allow_legacy_question=True,
    )
