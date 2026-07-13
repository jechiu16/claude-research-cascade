"""Fixture-replay tests for the openai-deep adapter (wave-2 async deep vendor).

Covers docs/superpowers/specs/2026-07-11-async-deep-engine-boundary.md the
same way tests/test_async_boundary.py covers the perplexity route: submit
accept, poll still-running, terminal success (occurrence + citations +
raw spool), terminal failure, and malformed-terminal (fail-closed, still
harvestable). The generic boundary guarantees (permit-category guards,
never-retried-after-accept, cross sync/async route refusal, wall-timeout ->
resume) are provider-agnostic and are already exhaustively exercised against
the perplexity route in tests/test_async_boundary.py; re-proving them here
against a second adapter would just duplicate the same boundary.py assertions
without adding adapter-specific information, so this file focuses on the
surface that is genuinely different for openai-deep: the adapter's own
job_token/extract parsing of OpenAI Responses API shapes, and the registry
record that binds it.

`_deep_contract` is duplicated (not imported) from test_async_boundary.py's
own copy, per that file's docstring note: it is kept inline "to avoid merge
conflicts with a shared fixture file" -- exactly the situation a second,
parallel async-adapter test file creates.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_harness.boundary import (
    AdapterParseError,
    BoundaryError,
    execute_deep_poll,
    execute_deep_submit,
)
from research_harness.contracts import contract_card_sha256, normalize_contract
from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
    validate_provider_registry,
)
from research_harness.quota import acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")
TEST_ENV = {"OPENAI_API_KEY": "test-key"}


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def _deep_contract(
    registry: dict,
    *,
    wall_time: int = 1200,
    transport_ceiling: int = 20,
    primary_scout_route: str = "demo-probe",
    deep_route: str = "openai-deep",
) -> dict:
    """A minimal confirmed contract exercising exactly the investigation/deep
    and investigation/transport mappings the async boundary extension needs.
    See tests/test_async_boundary.py::_deep_contract for the original."""

    contract = {
        "posture": "lookup",
        "tier": "custom",
        "execution": "external_managed",
        "durability": "canonical_package",
        "scout_route": primary_scout_route,
        "resource_envelope": {
            "physical_ceiling": {
                "probe": 1, "deep": 1, "processor": 0, "network_experiment": 0,
                "transport": transport_ceiling, "host_retrieval": 0, "local": 0,
                "organizer_pass": 0,
            },
            "external": {
                "metered_ceiling": {
                    "probe": 0, "deep": 1, "processor": 0,
                    "network_experiment": 0, "transport": 0,
                },
                "max_wall_time_seconds": wall_time,
                "allowed_endpoint_classes": [],
                "local_file_egress": False,
                "network_experiment_endpoints": [],
                "estimated_spend_usd": {"minimum": 0.0, "maximum": 1.0, "hard_cap": False},
                "raw_storage_bytes": 10 * 1024 * 1024,
            },
            "host": {"context_class": "lean", "admitted_characters": 8000, "estimated_tokens": 2000},
            "local": {"admitted_output_characters": 0, "max_wall_time_seconds": 60, "network_egress": False},
        },
        "stage_permit_map": [
            {"stage": "primary_scout", "category": "probe", "route": primary_scout_route,
             "invocations": 1, "count": 1, "reserved": False},
            {"stage": "investigation", "category": "deep", "route": deep_route,
             "invocations": 1, "count": 1, "reserved": False},
            {"stage": "investigation", "category": "transport", "route": deep_route,
             "invocations": transport_ceiling, "count": transport_ceiling, "reserved": False},
        ],
        "evidence_floor": {"minimum_load_bearing_claims": 1, "require_raw_artifacts": True},
        "artifact_policy": {"default_retention": "session", "allow_provider_payloads": False},
    }
    contract = normalize_contract(contract)
    records = referenced_provider_records(contract, registry)
    contract["confirmation"] = {
        "confirmed_by": "user",
        "confirmed_at": NOW,
        "card_sha256": contract_card_sha256(contract),
        "registry_sha256": provider_registry_sha256(registry),
        "referenced_records_sha256": provider_records_sha256(records),
    }
    return contract


class OpenAIDeepAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.registry = enabled_registry_copy("openai-deep")
        self.contract = _deep_contract(self.registry)
        self.session = Path(self._tempdir.name) / "session"
        state = new_state("openai-deep adapter test", self.contract, NOW, self.registry, TEST_ENV)
        create_session(self.session, state)
        patcher = mock.patch.dict("os.environ", TEST_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- helpers --------------------------------------------------------

    def attempt_statuses(self, action_id: str) -> list[str]:
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        return [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    def _acquire_deep(self, action_id: str = "D1") -> None:
        acquire_permits(
            self.session, action_id, "investigation", "deep", "openai-deep", 1, f"fp-{action_id}", NOW,
        )

    def _acquire_transport(self, action_id: str) -> None:
        acquire_permits(
            self.session, action_id, "investigation", "transport", "openai-deep", 1, f"fp-{action_id}", NOW,
        )

    def _submit(
        self, action_id: str = "D1", query: str = "what changed in SMR construction status", now: str = NOW,
    ) -> dict:
        self._acquire_deep(action_id)
        return execute_deep_submit(
            self.session, action_id, query, now,
            transport=fixture_transport("openai_deep_submit_accept.json"), environ=TEST_ENV,
        )

    # -- submit accept ------------------------------------------------------

    def test_submit_records_job_token_and_accepts(self) -> None:
        fixture = json.loads((FIXTURES / "openai_deep_submit_accept.json").read_text())
        result = self._submit()
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["job"], f"openai-deep:{fixture['id']}")
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted"])
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(json.loads(spool.read_text())["id"], fixture["id"])

    # -- poll: still running --------------------------------------------

    def test_poll_still_running_leaves_deep_action_unchanged(self) -> None:
        self._submit()
        self._acquire_transport("T1")
        result = execute_deep_poll(
            self.session, "D1", "T1", NOW,
            transport=fixture_transport("openai_deep_poll_running.json"), environ=TEST_ENV,
        )
        self.assertEqual(result["status"], "running")
        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "completed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted"])

    # -- poll: terminal success ------------------------------------------

    def test_poll_terminal_success_records_occurrence(self) -> None:
        self._submit()
        self._acquire_transport("T1")
        fixture = json.loads((FIXTURES / "openai_deep_poll_terminal_success.json").read_text())
        expected_citations = sum(
            1
            for item in fixture["output"]
            if item.get("type") == "message"
            for content in item.get("content", [])
            for annotation in content.get("annotations", [])
            if annotation.get("type") == "url_citation"
        )
        self.assertEqual(expected_citations, 3)  # brief calls for 2-3 url_citation annotations

        result = execute_deep_poll(
            self.session, "D1", "T1", NOW,
            transport=fixture_transport("openai_deep_poll_terminal_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(occurrence["provider_id"], "openai-deep")
        self.assertEqual(occurrence["action_id"], "D1")
        self.assertEqual(occurrence["model"], "o4-mini-deep-research")
        self.assertEqual(occurrence["kind"], "search_synthesis")
        self.assertIsNone(occurrence["cost_usd"])  # Responses API never reports a dollar cost
        self.assertEqual(occurrence["citation_count"], expected_citations)
        self.assertTrue(occurrence["synthesis_excerpt"].strip())
        self.assertEqual(
            {citation["url"] for citation in occurrence["citations"]},
            {
                annotation["url"]
                for item in fixture["output"]
                if item.get("type") == "message"
                for content in item.get("content", [])
                for annotation in content.get("annotations", [])
            },
        )

        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "completed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    # -- poll: terminal failure -------------------------------------------

    def test_poll_terminal_failure_fails_deep_action(self) -> None:
        self._submit()
        self._acquire_transport("T1")
        with self.assertRaises(BoundaryError):
            execute_deep_poll(
                self.session, "D1", "T1", NOW,
                transport=fixture_transport("openai_deep_poll_terminal_failure.json"), environ=TEST_ENV,
            )
        # the poll itself succeeded (it correctly learned "failed") -> completed;
        # only the deep action fails, and the permit stays consumed.
        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "completed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "failed"])
        state = load_state(self.session)
        self.assertEqual(state["retrieval_occurrences"], [])

    # -- poll: malformed terminal -------------------------------------------

    def test_poll_malformed_terminal_stays_harvestable(self) -> None:
        self._submit()
        self._acquire_transport("T1")
        with self.assertRaises(AdapterParseError):
            execute_deep_poll(
                self.session, "D1", "T1", NOW,
                transport=fixture_transport("openai_deep_poll_malformed_terminal.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "failed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted"])  # untouched
        spool = self.session / "provider_spool" / "T1.raw.json"
        self.assertTrue(spool.exists())  # spooled before extract() ever ran

        # still harvestable at zero marginal cost beyond a fresh transport permit:
        self._acquire_transport("T2")
        result = execute_deep_poll(
            self.session, "D1", "T2", NOW,
            transport=fixture_transport("openai_deep_poll_terminal_success.json"), environ=TEST_ENV,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "completed"])

    # -- registry schema ------------------------------------------------------

    def test_openai_deep_registry_record_validates(self) -> None:
        registry = load_provider_registry()
        self.assertEqual(validate_provider_registry(registry), [])
        provider = next(p for p in registry["providers"] if p["id"] == "openai-deep")
        self.assertEqual(provider["adapter"], "openai-deep-responses")
        self.assertEqual(provider["adapter_version"], "v1")
        self.assertEqual(provider["execution_binding"], "v2_request_boundary")
        self.assertEqual(provider["action_categories"], ["deep", "transport"])
        self.assertEqual(provider["stage_capabilities"], ["investigation", "anti_lock_in"])
        self.assertEqual(provider["request_multiplicity"], {"deep": 1, "transport": 1})
        self.assertEqual(provider["transport"], {"mode": "async", "polling": "required"})
        self.assertEqual(provider["required_env"], ["OPENAI_API_KEY"])
        self.assertEqual(provider["evidence_capabilities"], {"can_support_claims": False})
        # adoption gate invariant (not a frozen snapshot): an enabled external
        # route must carry a recognized adoption status and non-empty evidence;
        # openai-deep crossed the gate with a live occurrence on 2026-07-12,
        # the same gate perplexity crossed in test_async_boundary's live-run note.
        self.assertTrue(provider["enabled"])
        self.assertIn(provider["adoption_status"], {"baseline", "validated"})
        self.assertTrue(provider["adoption_evidence"])
        self.assertTrue(any("live-occurrence" in item for item in provider["adoption_evidence"]))


if __name__ == "__main__":
    unittest.main()
