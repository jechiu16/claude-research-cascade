from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_harness.budgets import (
    BudgetProfileError,
    load_budget_profiles,
    resolve_budget_profile,
)


class BudgetProfileTests(unittest.TestCase):
    def test_default_profiles_are_count_vectors(self) -> None:
        profiles = load_budget_profiles()["profiles"]
        self.assertEqual(profiles["light"], {"deep": 0, "search": 5, "free": "unlimited"})
        self.assertEqual(profiles["standard"], {"deep": 1, "search": 15, "free": "unlimited"})
        self.assertEqual(profiles["heavy"], {"deep": 2, "search": 30, "free": "unlimited"})

    def test_resolved_profile_is_an_immutable_contract_snapshot(self) -> None:
        profile = resolve_budget_profile("standard")
        self.assertEqual(
            profile,
            {"profile": "standard", "deep": 1, "search": 15, "free": "unlimited"},
        )

    def test_custom_file_controls_numbers_without_naming_tools(self) -> None:
        payload = load_budget_profiles()
        payload["profiles"]["standard"]["search"] = 7
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "profiles.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(resolve_budget_profile("standard", path)["search"], 7)

    def test_invalid_profile_cannot_make_free_calls_finite(self) -> None:
        payload = load_budget_profiles()
        payload["profiles"]["heavy"]["free"] = 99
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "profiles.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(BudgetProfileError, "heavy free must be unlimited"):
                load_budget_profiles(path)


if __name__ == "__main__":
    unittest.main()
