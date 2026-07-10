from __future__ import annotations

import copy
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


def confirmed_demo_contract(
    route: str = "demo-probe",
    request_count: int = 1,
    probe_ceiling: int = 2,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = copy.deepcopy(load_provider_registry() if registry is None else registry)
    contract = draft_medium_contract()
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
