"""Provider capability registry loading, validation, overlays, and hashing."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from ._canon import RETENTION_RANK, is_positive_count as _is_positive_int, sha256_hex


REGISTRY_PATH = Path(__file__).with_name("provider_registry.json")
REGISTRY_SCHEMA_VERSION = "1.0"

REQUIRED_PROVIDER_FIELDS = (
    "id",
    "adapter",
    "adapter_version",
    "enabled",
    "roles",
    "action_categories",
    "stage_capabilities",
    "request_multiplicity",
    "execution_binding",
    "adoption_status",
    "adoption_evidence",
    "index_family",
    "index_provenance",
    "upstream_provider",
    "retrieval_shape",
    "evidence_capabilities",
    "controls",
    "metering",
    "transport",
    "privacy",
    "storage_rights",
    "lifecycle",
    "required_env",
    "docs_url",
    "docs_verified_at",
)

ALLOWED_INDEX_PROVENANCE = frozenset(
    {
        "independent",
        "scholarly-index",
        "registry",
        "hybrid-opaque",
        "wrapper",
        "grounding-wrapper",
        "fetch-only",
        "archive",
        "unknown",
        "not_applicable",
    }
)
LOCAL_BINDINGS = frozenset({"host_native_observed", "local", "no_network_demo"})


class ProviderRegistryError(ValueError):
    """Raised when registry data or an overlay would create an unsafe route."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderRegistryError(f"cannot load provider registry {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProviderRegistryError(f"provider registry {path} must contain a JSON object")
    return value


def _expanded_registry(raw: dict[str, Any]) -> dict[str, Any]:
    defaults = raw.get("provider_defaults", {})
    if not isinstance(defaults, dict):
        raise ProviderRegistryError("provider_defaults must be an object")
    providers = raw.get("providers")
    if not isinstance(providers, list):
        raise ProviderRegistryError("provider registry providers must be a list")
    expanded: list[dict[str, Any]] = []
    for item in providers:
        if not isinstance(item, dict):
            raise ProviderRegistryError("every provider record must be an object")
        record = copy.deepcopy(defaults)
        record.update(copy.deepcopy(item))
        expanded.append(record)
    return {
        "schema_version": raw.get("schema_version"),
        "providers": sorted(expanded, key=lambda provider: str(provider.get("id", ""))),
    }


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def validate_provider_registry(registry: dict[str, Any]) -> list[str]:
    """Return deterministic registry errors without reading keys or importing adapters."""

    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["provider registry must be an object"]
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        errors.append(f"provider registry schema_version must be {REGISTRY_SCHEMA_VERSION}")
    providers = registry.get("providers")
    if not isinstance(providers, list):
        errors.append("provider registry providers must be a list")
        return errors

    seen: set[str] = set()
    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            errors.append(f"provider record {index} must be an object")
            continue
        provider_id = provider.get("id")
        label = provider_id if isinstance(provider_id, str) and provider_id else f"record {index}"
        for field in REQUIRED_PROVIDER_FIELDS:
            if field not in provider:
                errors.append(f"provider {label} field {field} is required")
        if not isinstance(provider_id, str) or not provider_id:
            errors.append(f"provider record {index} id must be a non-empty string")
            continue
        if provider_id in seen:
            errors.append(f"duplicate provider id {provider_id}")
        seen.add(provider_id)

        if not isinstance(provider.get("enabled"), bool):
            errors.append(f"provider {provider_id} enabled must be boolean")
        for field in (
            "adapter",
            "adapter_version",
            "execution_binding",
            "adoption_status",
            "index_family",
            "upstream_provider",
            "docs_url",
            "docs_verified_at",
        ):
            if not isinstance(provider.get(field), str) or not provider.get(field):
                errors.append(f"provider {provider_id} {field} must be a non-empty string")
        for field in ("roles", "action_categories", "stage_capabilities", "retrieval_shape", "required_env"):
            if field in provider and not _is_string_list(provider[field]):
                errors.append(f"provider {provider_id} {field} must be a list of non-empty strings")
        required_env = provider.get("required_env")
        if isinstance(required_env, list) and any(
            not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
            for name in required_env
        ):
            errors.append(f"provider {provider_id} required_env contains an invalid name")
        for field in ("evidence_capabilities", "controls", "metering", "transport", "privacy"):
            if not isinstance(provider.get(field), dict):
                errors.append(f"provider {provider_id} {field} must be an object")
        if provider.get("index_provenance") not in ALLOWED_INDEX_PROVENANCE:
            errors.append(f"provider {provider_id} index_provenance is invalid")
        multiplicity = provider.get("request_multiplicity")
        if not isinstance(multiplicity, dict) or not multiplicity:
            errors.append(f"provider {provider_id} request_multiplicity must be a non-empty object")
        elif any(not isinstance(key, str) or not _is_positive_int(value) for key, value in multiplicity.items()):
            errors.append(f"provider {provider_id} request_multiplicity values must be positive integers")

        storage = provider.get("storage_rights")
        if not isinstance(storage, dict):
            errors.append(f"provider {provider_id} storage_rights must be an object")
            storage = {}
        for field in ("payload_retention", "html_allowed", "allowed_operational_fields", "verified_at", "source"):
            if field not in storage:
                errors.append(f"provider {provider_id} storage_rights.{field} is required")
        retention = storage.get("payload_retention")
        if retention not in {*RETENTION_RANK, "unknown"}:
            errors.append(f"provider {provider_id} storage payload_retention is invalid")
        if "html_allowed" in storage and not isinstance(storage.get("html_allowed"), bool):
            errors.append(f"provider {provider_id} storage html_allowed must be boolean")
        if "allowed_operational_fields" in storage and not _is_string_list(storage.get("allowed_operational_fields")):
            if storage.get("allowed_operational_fields") != []:
                errors.append(f"provider {provider_id} allowed_operational_fields must be a string list")

        lifecycle = provider.get("lifecycle")
        if not isinstance(lifecycle, dict) or "status" not in lifecycle or "sunset_at" not in lifecycle:
            errors.append(f"provider {provider_id} lifecycle status and sunset_at are required")
            lifecycle = {}

        if provider.get("enabled") is True:
            if provider.get("adapter") == "unbound" or provider.get("adapter_version") == "unbound":
                errors.append(f"enabled route {provider_id} has no adapter binding")
            for field in ("roles", "action_categories", "stage_capabilities"):
                if not provider.get(field):
                    errors.append(f"enabled route {provider_id} has no {field}")
            if lifecycle.get("status") != "active":
                errors.append(f"enabled route {provider_id} is {lifecycle.get('status', 'unknown')}")
            if retention == "unknown":
                errors.append(f"enabled route {provider_id} has unknown storage rights")
            binding = provider.get("execution_binding")
            if binding not in LOCAL_BINDINGS and binding != "v2_request_boundary":
                errors.append(f"enabled external route {provider_id} is not v2-bound")
            if binding == "v2_request_boundary":
                evidence = provider.get("adoption_evidence")
                if (
                    provider.get("adoption_status") not in {"baseline", "validated"}
                    or not evidence
                    or not _is_string_list(evidence)
                ):
                    errors.append(f"enabled external route {provider_id} lacks adoption evidence")
            if binding == "no_network_demo":
                capabilities = provider.get("evidence_capabilities")
                if not isinstance(capabilities, dict) or capabilities.get("can_support_claims") is not False:
                    errors.append(f"demo route {provider_id} must be barred from evidence")
    return errors


def _storage_is_no_broader(base: dict[str, Any], overlaid: dict[str, Any]) -> bool:
    base_retention = base.get("payload_retention")
    new_retention = overlaid.get("payload_retention")
    if base_retention == "unknown":
        retention_ok = new_retention in {"unknown", "forbidden", "ephemeral"}
    elif new_retention == "unknown":
        retention_ok = True
    else:
        retention_ok = (
            base_retention in RETENTION_RANK
            and new_retention in RETENTION_RANK
            and RETENTION_RANK[new_retention] <= RETENTION_RANK[base_retention]
        )
    html_ok = not overlaid.get("html_allowed", False) or base.get("html_allowed", False)
    fields_ok = set(overlaid.get("allowed_operational_fields", [])) <= set(
        base.get("allowed_operational_fields", [])
    )
    return retention_ok and html_ok and fields_ok


def _merge_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    if overlay.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ProviderRegistryError(f"provider overlay schema_version must be {REGISTRY_SCHEMA_VERSION}")
    overlay_providers = overlay.get("providers")
    if not isinstance(overlay_providers, list):
        raise ProviderRegistryError("provider overlay providers must be a list")

    merged = {provider["id"]: copy.deepcopy(provider) for provider in base["providers"]}
    overlay_ids = [
        candidate.get("id")
        for candidate in overlay_providers
        if isinstance(candidate, dict) and isinstance(candidate.get("id"), str)
    ]
    if len(overlay_ids) != len(set(overlay_ids)):
        raise ProviderRegistryError("provider overlay contains duplicate ids")
    immutable_fields = (
        "adapter",
        "adapter_version",
        "request_multiplicity",
        "execution_binding",
        "index_family",
        "index_provenance",
        "upstream_provider",
        "retrieval_shape",
        "evidence_capabilities",
    )
    fixed_policy_fields = ("controls", "metering", "transport", "privacy", "adoption_status", "adoption_evidence")
    for candidate in overlay_providers:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
            raise ProviderRegistryError("provider overlay records require string ids")
        provider_id = candidate["id"]
        if provider_id not in merged:
            if candidate.get("enabled") is not False:
                raise ProviderRegistryError(f"overlay cannot enable new provider {provider_id}")
            merged[provider_id] = copy.deepcopy(candidate)
            continue

        current = merged[provider_id]
        replacement = copy.deepcopy(candidate)
        if not current.get("enabled", False):
            if replacement.get("enabled") is not False:
                raise ProviderRegistryError(f"overlay cannot enable unbound provider {provider_id}")
            merged[provider_id] = replacement
            continue

        if replacement.get("enabled") not in {True, False}:
            raise ProviderRegistryError(f"overlay enabled for {provider_id} must be boolean")
        for field in immutable_fields:
            if replacement.get(field) != current.get(field):
                raise ProviderRegistryError(f"overlay cannot change {field} for enabled provider {provider_id}")
        for field in fixed_policy_fields:
            if replacement.get(field) != current.get(field):
                raise ProviderRegistryError(f"overlay cannot change {field} for enabled provider {provider_id}")
        for field in ("roles", "action_categories", "stage_capabilities"):
            if not set(replacement.get(field, [])) <= set(current.get(field, [])):
                raise ProviderRegistryError(f"overlay cannot broaden {field} for enabled provider {provider_id}")
        if not set(current.get("required_env", [])) <= set(replacement.get("required_env", [])):
            raise ProviderRegistryError(f"overlay cannot remove required_env for enabled provider {provider_id}")
        if replacement.get("enabled") is True and replacement.get("lifecycle") != current.get("lifecycle"):
            raise ProviderRegistryError(f"overlay cannot change lifecycle for enabled provider {provider_id}")
        if not _storage_is_no_broader(current.get("storage_rights", {}), replacement.get("storage_rights", {})):
            raise ProviderRegistryError(f"overlay cannot broaden storage rights for enabled provider {provider_id}")
        merged[provider_id] = replacement

    result = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "providers": sorted(merged.values(), key=lambda provider: provider["id"]),
    }
    errors = validate_provider_registry(result)
    if errors:
        raise ProviderRegistryError("; ".join(errors))
    return result


def load_provider_registry(
    path: Optional[Path] = None,
    overlay: Optional[Path] = None,
) -> dict[str, Any]:
    """Load and validate the resolved registry, applying a restrictive overlay."""

    base = _expanded_registry(_load_json(Path(path) if path else REGISTRY_PATH))
    errors = validate_provider_registry(base)
    if errors:
        raise ProviderRegistryError("; ".join(errors))
    if overlay is not None:
        base = _merge_overlay(base, _expanded_registry(_load_json(Path(overlay))))
    return copy.deepcopy(base)


def provider_registry_sha256(registry: dict[str, Any]) -> str:
    def sort_key(provider: Any) -> str:
        return str(provider.get("id", "")) if isinstance(provider, dict) else repr(provider)

    normalized = {
        "schema_version": registry.get("schema_version"),
        "providers": sorted(copy.deepcopy(registry.get("providers", [])), key=sort_key),
    }
    return sha256_hex(normalized)


def provider_records_sha256(records: list[dict[str, Any]]) -> str:
    normalized = sorted(
        copy.deepcopy(records),
        key=lambda provider: str(provider.get("id", "")) if isinstance(provider, dict) else repr(provider),
    )
    return sha256_hex(normalized)


def referenced_provider_records(contract: dict[str, Any], registry: dict[str, Any]) -> list[dict[str, Any]]:
    providers = {provider["id"]: provider for provider in registry.get("providers", [])}
    route_ids = sorted(
        {
            mapping.get("route")
            for mapping in contract.get("stage_permit_map", [])
            if isinstance(mapping, dict) and isinstance(mapping.get("route"), str)
        }
    )
    missing = [route_id for route_id in route_ids if route_id not in providers]
    if missing:
        raise ProviderRegistryError(f"unknown provider routes: {', '.join(missing)}")
    return [copy.deepcopy(providers[route_id]) for route_id in route_ids]


def preflight_contract_routes(
    contract: dict[str, Any],
    registry: dict[str, Any],
    environ: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Check route readiness while retaining key names and booleans only."""

    errors: list[str] = []
    try:
        providers = referenced_provider_records(contract, registry)
    except ProviderRegistryError as exc:
        return [], [str(exc)]
    records: list[dict[str, Any]] = []
    for provider in providers:
        provider_id = provider["id"]
        env_records = [
            {"name": name, "present": bool(environ.get(name))}
            for name in sorted(provider.get("required_env", []))
        ]
        missing = [record["name"] for record in env_records if not record["present"]]
        if not provider.get("enabled", False):
            errors.append(f"route {provider_id} is not enabled")
        if provider.get("lifecycle", {}).get("status") != "active":
            errors.append(f"route {provider_id} lifecycle is not active")
        if missing:
            errors.append(f"route {provider_id} missing required environment: {', '.join(missing)}")
        records.append(
            {
                "provider_id": provider_id,
                "adapter": provider.get("adapter"),
                "adapter_version": provider.get("adapter_version"),
                "execution_binding": provider.get("execution_binding"),
                "required_env": env_records,
                "ready": (
                    provider.get("enabled", False)
                    and provider.get("lifecycle", {}).get("status") == "active"
                    and not missing
                ),
            }
        )
    return records, errors
