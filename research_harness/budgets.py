"""Configurable count budgets for the public research profiles."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional


PROFILE_PATH = Path(__file__).with_name("budget_profiles.json")
PROFILE_SCHEMA_VERSION = "1.0"
PROFILE_NAMES = ("light", "standard", "heavy")
COST_CLASSES = frozenset({"deep", "search", "free"})


class BudgetProfileError(ValueError):
    """Raised when a profile file cannot form a safe count envelope."""


def validate_budget_profiles(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["budget profiles must be an object"]
    if data.get("schema_version") != PROFILE_SCHEMA_VERSION:
        errors.append(f"budget profile schema_version must be {PROFILE_SCHEMA_VERSION}")
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return errors + ["budget profiles map is required"]
    if set(profiles) != set(PROFILE_NAMES):
        errors.append("budget profiles must contain exactly light, standard, and heavy")
    for name in PROFILE_NAMES:
        profile = profiles.get(name)
        if not isinstance(profile, dict):
            errors.append(f"budget profile {name} must be an object")
            continue
        if set(profile) != COST_CLASSES:
            errors.append(f"budget profile {name} must contain exactly deep, search, and free")
            continue
        for cost_class in ("deep", "search"):
            value = profile.get(cost_class)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"budget profile {name} {cost_class} must be a non-negative integer")
        if profile.get("free") != "unlimited":
            errors.append(f"budget profile {name} free must be unlimited")
    return errors


def load_budget_profiles(path: Optional[Path] = None) -> dict[str, Any]:
    source = Path(path) if path else PROFILE_PATH
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BudgetProfileError(f"cannot load budget profiles {source}: {exc}") from exc
    errors = validate_budget_profiles(data)
    if errors:
        raise BudgetProfileError("; ".join(errors))
    return copy.deepcopy(data)


def resolve_budget_profile(name: str, path: Optional[Path] = None) -> dict[str, Any]:
    profiles = load_budget_profiles(path)
    if name not in PROFILE_NAMES:
        raise BudgetProfileError(f"unknown budget profile {name}")
    return {"profile": name, **copy.deepcopy(profiles["profiles"][name])}
