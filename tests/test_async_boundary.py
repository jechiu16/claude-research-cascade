"""Fixture-replay tests for the async deep-engine boundary extension.

Covers docs/superpowers/specs/2026-07-11-async-deep-engine-boundary.md:
submit-accept, poll-running, poll-terminal-success, poll-terminal-failure,
malformed-terminal (spooled + still harvestable), and
wall-timeout -> uncertain -> journaled resume -> poll -> completed.

Contract stage naming deviates from the literal spec draft: it uses the
single stage "investigation" for both the `deep` and `transport` category
mappings (not "deep_investigation"/"deep_transport"), matching
docs/superpowers/specs/2026-07-10-adaptive-scientific-research-harness-design.md
section 7.1 ("investigation ... each accepted submission=`deep`", with
`transport` explicitly a same-route harvest of an already-authorized
`investigation` job) and the pre-existing openai/gemini candidate registry
records, which already encode stage_capabilities=["investigation",
"anti_lock_in"] with request_multiplicity {"deep": 1, "transport": 1}.
"""

from __future__ import annotations

import copy
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
    execute_deep_timeout,
    execute_probe,
)
from research_harness.contracts import contract_card_sha256, normalize_contract
from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
)
from research_harness.quota import acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")
TEST_ENV = {"PERPLEXITY_API_KEY": "test-key"}


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
    deep_route: str = "perplexity",
) -> dict:
    """A minimal confirmed contract exercising exactly the investigation/deep
    and investigation/transport mappings this boundary extension needs.
    Built inline (not in tests/helpers.py) per instructions to avoid merge
    conflicts with a shared fixture file."""

    contract = {
        "posture": "lookup",
        "tier": "custom",
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


class AsyncBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.registry = enabled_registry_copy("perplexity")
        self.contract = _deep_contract(self.registry)
        self.session = Path(self._tempdir.name) / "session"
        state = new_state("async deep boundary test", self.contract, NOW, self.registry, TEST_ENV)
        create_session(self.session, state)
        patcher = mock.patch.dict("os.environ", TEST_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- helpers --------------------------------------------------------

    def attempt_statuses(self, action_id: str, session: Path | None = None) -> list[str]:
        events, errors = read_events(session or self.session)
        self.assertEqual(errors, [])
        return [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    def _new_session(self, name: str, contract: dict, registry: dict) -> Path:
        session = Path(self._tempdir.name) / name
        state = new_state("async boundary guard test", contract, NOW, registry, TEST_ENV)
        create_session(session, state)
        return session

    def _acquire_deep(self, action_id: str = "D1", session: Path | None = None, now: str = NOW) -> None:
        acquire_permits(
            session or self.session, action_id, "investigation", "deep", "perplexity", 1,
            f"fp-{action_id}", now,
        )

    def _acquire_transport(self, action_id: str, session: Path | None = None, now: str = NOW) -> None:
        acquire_permits(
            session or self.session, action_id, "investigation", "transport", "perplexity", 1,
            f"fp-{action_id}", now,
        )

    def _submit(
        self, action_id: str = "D1", query: str = "what changed in async retrieval boundaries",
        now: str = NOW, session: Path | None = None,
    ) -> dict:
        self._acquire_deep(action_id, session=session, now=now)
        return execute_deep_submit(
            session or self.session, action_id, query, now,
            transport=fixture_transport("perplexity_deep_submit_accept.json"), environ=TEST_ENV,
        )

    # -- submit -----------------------------------------------------------

    def test_submit_records_job_token_and_accepts(self) -> None:
        fixture = json.loads((FIXTURES / "perplexity_deep_submit_accept.json").read_text())
        result = self._submit()
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["job"], f"perplexity:{fixture['id']}")
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted"])
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(json.loads(spool.read_text())["id"], fixture["id"])

    def test_submit_is_never_retried_after_accept(self) -> None:
        self._submit()
        with self.assertRaises(BoundaryError):
            execute_deep_submit(
                self.session, "D1", "q", NOW,
                transport=fixture_transport("perplexity_deep_submit_accept.json"), environ=TEST_ENV,
            )

    def test_submit_requires_deep_category_permit(self) -> None:
        acquire_permits(self.session, "P1", "primary_scout", "probe", "demo-probe", 1, "fp-p1", NOW)
        with self.assertRaises(BoundaryError):
            execute_deep_submit(
                self.session, "P1", "q", NOW,
                transport=fixture_transport("perplexity_deep_submit_accept.json"), environ=TEST_ENV,
            )
        # the wrongly-typed action never even reaches "attempted"
        self.assertEqual(self.attempt_statuses("P1"), [])

    def test_submit_http_error_fails_without_job_token(self) -> None:
        acquire_permits(self.session, "D1", "investigation", "deep", "perplexity", 1, "fp-d1", NOW)
        with self.assertRaises(BoundaryError):
            execute_deep_submit(
                self.session, "D1", "q", NOW,
                transport=fixture_transport("sonar_rate_limited.json", status=429), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "D1.raw.json"
        self.assertIn("rate_limit_exceeded", spool.read_text())

    def test_submit_malformed_accept_body_fails_after_spooling(self) -> None:
        acquire_permits(self.session, "D1", "investigation", "deep", "perplexity", 1, "fp-d1", NOW)
        with self.assertRaises(AdapterParseError):
            execute_deep_submit(
                self.session, "D1", "q", NOW,
                transport=fixture_transport("perplexity_deep_submit_malformed.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "D1.raw.json"
        self.assertTrue(spool.exists())
        self.assertIn("CREATED", spool.read_text())

    # -- poll: still running ----------------------------------------------

    def test_poll_still_running_leaves_deep_action_unchanged(self) -> None:
        self._submit()
        self._acquire_transport("T1")
        result = execute_deep_poll(
            self.session, "D1", "T1", NOW,
            transport=fixture_transport("perplexity_deep_poll_running.json"), environ=TEST_ENV,
        )
        self.assertEqual(result["status"], "running")
        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "completed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted"])

    # -- poll: terminal success --------------------------------------------

    def test_poll_terminal_success_records_occurrence(self) -> None:
        # Expectations come from the fixture itself: perplexity_deep_submit_accept
        # .json, perplexity_deep_poll_running.json, and
        # perplexity_deep_poll_terminal_success.json are ONE real recorded job
        # (live sonar-deep-research call 2026-07-11, reasoning_effort "low",
        # cost_usd 0.6261, 19 citations, 8 polls / 180s wall time) and may be
        # re-recorded later. terminal_failure and malformed_terminal are
        # synthetic (a real failure was not deliberately induced).
        self._submit()
        self._acquire_transport("T1")
        fixture = json.loads((FIXTURES / "perplexity_deep_poll_terminal_success.json").read_text())
        expected_cost = round(fixture["response"]["usage"]["cost"]["total_cost"], 4)
        expected_citations = len(fixture["response"].get("search_results", []))

        result = execute_deep_poll(
            self.session, "D1", "T1", NOW,
            transport=fixture_transport("perplexity_deep_poll_terminal_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(occurrence["provider_id"], "perplexity")
        self.assertEqual(occurrence["action_id"], "D1")
        self.assertEqual(occurrence["model"], "sonar-deep-research")
        self.assertEqual(occurrence["kind"], "search_synthesis")
        self.assertAlmostEqual(occurrence["cost_usd"], expected_cost)
        self.assertEqual(occurrence["citation_count"], expected_citations)
        self.assertTrue(occurrence["synthesis_excerpt"].strip())

        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "completed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    # -- poll: terminal failure ---------------------------------------------

    def test_poll_terminal_failure_fails_deep_action(self) -> None:
        self._submit()
        self._acquire_transport("T1")
        with self.assertRaises(BoundaryError):
            execute_deep_poll(
                self.session, "D1", "T1", NOW,
                transport=fixture_transport("perplexity_deep_poll_terminal_failure.json"), environ=TEST_ENV,
            )
        # the poll itself succeeded (it correctly learned FAILED) -> completed;
        # only the deep action fails.
        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "completed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "failed"])
        # permit stays consumed: no occurrence, no way to resubmit under D1
        state = load_state(self.session)
        self.assertEqual(state["retrieval_occurrences"], [])

    # -- poll: malformed terminal --------------------------------------------

    def test_poll_malformed_terminal_stays_harvestable(self) -> None:
        self._submit()
        self._acquire_transport("T1")
        with self.assertRaises(AdapterParseError):
            execute_deep_poll(
                self.session, "D1", "T1", NOW,
                transport=fixture_transport("perplexity_deep_poll_malformed_terminal.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses("T1"), ["attempted", "accepted", "failed"])
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted"])  # untouched
        spool = self.session / "provider_spool" / "T1.raw.json"
        self.assertTrue(spool.exists())  # spooled before extract() ever ran

        # still harvestable at zero marginal cost beyond a fresh transport permit:
        self._acquire_transport("T2")
        result = execute_deep_poll(
            self.session, "D1", "T2", NOW,
            transport=fixture_transport("perplexity_deep_poll_terminal_success.json"), environ=TEST_ENV,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.attempt_statuses("D1"), ["attempted", "accepted", "completed"])

    # -- poll: permit-shape guards --------------------------------------------

    def test_poll_requires_transport_category_permit(self) -> None:
        self._submit()
        acquire_permits(self.session, "PX", "primary_scout", "probe", "demo-probe", 1, "fp-px", NOW)
        with self.assertRaises(BoundaryError):
            execute_deep_poll(
                self.session, "D1", "PX", NOW,
                transport=fixture_transport("perplexity_deep_poll_running.json"), environ=TEST_ENV,
            )

    def test_poll_unknown_deep_action_is_refused(self) -> None:
        self._acquire_transport("T1")
        with self.assertRaises(BoundaryError):
            execute_deep_poll(
                self.session, "missing-deep", "T1", NOW,
                transport=fixture_transport("perplexity_deep_poll_running.json"), environ=TEST_ENV,
            )

    # -- wall-timeout -> uncertain -> resume -> poll -> completed -------------

    def test_wall_timeout_then_resume_then_poll_completes(self) -> None:
        contract = _deep_contract(self.registry, wall_time=60)
        session = self._new_session("session-timeout", contract, self.registry)
        self._submit(session=session)

        # not yet elapsed: no-op, deep action stays accepted
        not_yet = execute_deep_timeout(session, "D1", "2026-07-10T12:00:30Z")
        self.assertFalse(not_yet["transitioned"])
        self.assertEqual(self.attempt_statuses("D1", session), ["attempted", "accepted"])

        # elapsed past the 60s wall cap
        timed_out = execute_deep_timeout(session, "D1", "2026-07-10T12:01:05Z")
        self.assertTrue(timed_out["transitioned"])
        self.assertEqual(self.attempt_statuses("D1", session), ["attempted", "accepted", "uncertain"])

        # a later poll journals the resume, then completes in one call
        self._acquire_transport("T1", session=session, now="2026-07-10T12:01:10Z")
        result = execute_deep_poll(
            session, "D1", "T1", "2026-07-10T12:01:12Z",
            transport=fixture_transport("perplexity_deep_poll_terminal_success.json"), environ=TEST_ENV,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            self.attempt_statuses("D1", session),
            ["attempted", "accepted", "uncertain", "accepted", "completed"],
        )
        events, _ = read_events(session)
        resume_events = [
            event for event in events
            if event.get("event") == "attempt_status"
            and event.get("action_id") == "D1"
            and event.get("details", {}).get("resume") is True
        ]
        self.assertEqual(len(resume_events), 1)
        report = validate_session(session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_timeout_is_a_free_noop_before_submission_status_changes(self) -> None:
        # calling deep-timeout on an action that never reached "accepted"
        # (e.g. still "attempted", or already terminal) must not raise.
        self._submit()
        self._acquire_transport("T1")
        execute_deep_poll(
            self.session, "D1", "T1", NOW,
            transport=fixture_transport("perplexity_deep_poll_terminal_success.json"), environ=TEST_ENV,
        )
        result = execute_deep_timeout(self.session, "D1", NOW)
        self.assertFalse(result["transitioned"])
        self.assertEqual(result["reason"], "status is completed")

    # -- _bound_route mode guard: sync boundary refuses async routes and vice versa --

    def test_execute_probe_refuses_async_route(self) -> None:
        registry = enabled_registry_copy("perplexity")
        for provider in registry["providers"]:
            if provider["id"] == "perplexity":
                provider["action_categories"] = list(provider["action_categories"]) + ["probe"]
                provider["stage_capabilities"] = list(provider["stage_capabilities"]) + ["primary_scout"]
                provider["request_multiplicity"] = {**provider["request_multiplicity"], "probe": 1}
        contract = _deep_contract(registry, primary_scout_route="perplexity")
        session = self._new_session("session-cross-sync", contract, registry)
        acquire_permits(session, "PX", "primary_scout", "probe", "perplexity", 1, "fp-px", NOW)
        with self.assertRaises(BoundaryError) as ctx:
            execute_probe(
                session, "PX", "q", NOW,
                transport=fixture_transport("perplexity_deep_submit_accept.json"), environ=TEST_ENV,
            )
        self.assertIn("transport mode", str(ctx.exception))

    def test_execute_deep_submit_refuses_sync_route(self) -> None:
        registry = copy.deepcopy(load_provider_registry())
        for provider in registry["providers"]:
            if provider["id"] == "sonar":
                provider["action_categories"] = list(provider["action_categories"]) + ["deep", "transport"]
                provider["stage_capabilities"] = list(provider["stage_capabilities"]) + ["investigation"]
                provider["request_multiplicity"] = {
                    **provider["request_multiplicity"], "deep": 1, "transport": 1,
                }
        contract = _deep_contract(registry, deep_route="sonar")
        session = self._new_session("session-cross-async", contract, registry)
        acquire_permits(session, "D1", "investigation", "deep", "sonar", 1, "fp-d1", NOW)
        with self.assertRaises(BoundaryError) as ctx:
            execute_deep_submit(
                session, "D1", "q", NOW,
                transport=fixture_transport("sonar_success.json"), environ=TEST_ENV,
            )
        self.assertIn("transport mode", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
