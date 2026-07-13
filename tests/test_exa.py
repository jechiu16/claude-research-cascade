from __future__ import annotations

import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from research_harness.adapters import exa
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy


TEST_ENV = {"EXA_API_KEY": "test-exa-key"}
FIXTURES = Path(__file__).with_name("fixtures")
SUCCESS_FIXTURE = FIXTURES / "exa_success.json"


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def failing_transport(exc: Exception):
    def transport(spec):
        raise exc

    return transport


class ExaBuildTests(unittest.TestCase):
    def test_build_is_one_bounded_auto_search_with_highlights(self) -> None:
        spec = exa.build("reliable agent evaluation", TEST_ENV)
        body = json.loads(spec.body)

        self.assertEqual(spec.method, "POST")
        self.assertEqual(spec.url, "https://api.exa.ai/search")
        self.assertEqual(spec.headers["x-api-key"], "test-exa-key")
        self.assertEqual(spec.headers["Content-Type"], "application/json")
        self.assertEqual(spec.timeout_s, 60.0)
        self.assertEqual(
            body,
            {
                "query": "reliable agent evaluation",
                "type": "auto",
                "numResults": 10,
                "contents": {"highlights": True},
            },
        )
        self.assertNotIn("outputSchema", body)
        self.assertNotIn("stream", body)
        self.assertNotIn("additionalQueries", body)

    def test_build_requires_api_key(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "EXA_API_KEY"):
            exa.build("q", {})

    def test_build_rejects_empty_api_key(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "EXA_API_KEY"):
            exa.build("q", {"EXA_API_KEY": ""})


class ExaParseTests(unittest.TestCase):
    def test_parse_rejects_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            exa.parse(b"not json")

    def test_parse_rejects_non_object_top_level(self) -> None:
        for payload in (b"[]", b'"text"', b"42", b"null", b"true"):
            with self.subTest(payload=payload):
                with self.assertRaises(AdapterParseError):
                    exa.parse(payload)

    def test_parse_requires_results_list(self) -> None:
        for value in (None, {}, "results", 1):
            with self.subTest(value=value):
                payload = json.dumps({"results": value}).encode("utf-8")
                with self.assertRaises(AdapterParseError):
                    exa.parse(payload)

    def test_parse_returns_context_efficient_result_listing(self) -> None:
        payload = json.dumps(
            {
                "requestId": "req-1",
                "results": [
                    {
                        "title": "Evaluation paper",
                        "url": "https://example.test/paper",
                        "publishedDate": "2026-01-02T00:00:00.000Z",
                        "author": "A. Researcher",
                        "highlights": ["A" * 600, "second highlight"],
                    }
                ],
                "costDollars": {"total": 0.007, "search": {"neural": 0.005}},
            }
        ).encode("utf-8")

        result = exa.parse(payload)

        self.assertEqual(result.kind, "result_listing")
        self.assertEqual(result.model, "exa/search-auto")
        self.assertEqual(result.cost_usd, 0.007)
        self.assertEqual(
            result.citations,
            [
                {
                    "url": "https://example.test/paper",
                    "title": "Evaluation paper",
                    "date": "2026-01-02T00:00:00.000Z",
                }
            ],
        )
        self.assertIn("Evaluation paper", result.synthesis_text)
        self.assertIn("A. Researcher", result.synthesis_text)
        self.assertIn("A" * 500, result.synthesis_text)
        self.assertNotIn("A" * 501, result.synthesis_text)
        self.assertNotIn("second highlight", result.synthesis_text)
        self.assertEqual(result.usage["request_id"], "req-1")
        self.assertEqual(result.usage["returned"], 1)

    def test_parse_lists_unresolvable_result_without_counting_citation(self) -> None:
        payload = json.dumps(
            {
                "results": [
                    {
                        "title": "Missing URL",
                        "url": None,
                        "publishedDate": None,
                        "author": None,
                        "highlights": [],
                    }
                ]
            }
        ).encode("utf-8")
        result = exa.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertIn("Missing URL", result.synthesis_text)

    def test_parse_rejects_non_web_citation_urls(self) -> None:
        payload = json.dumps(
            {"results": [{"title": "Unsafe URL", "url": "javascript:alert(1)"}]}
        ).encode("utf-8")
        self.assertEqual(exa.parse(payload).citations, [])

    def test_parse_handles_empty_results(self) -> None:
        result = exa.parse(json.dumps({"results": []}).encode("utf-8"))
        self.assertEqual(result.citations, [])
        self.assertEqual(result.synthesis_text, "")
        self.assertEqual(result.usage["returned"], 0)

    def test_parse_ignores_non_numeric_cost(self) -> None:
        payload = json.dumps(
            {"results": [], "costDollars": {"total": "0.007"}}
        ).encode("utf-8")
        self.assertIsNone(exa.parse(payload).cost_usd)


class ExaBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.session = Path(self.tempdir.name) / "session"
        self.registry = enabled_registry_copy("exa")
        patcher = mock.patch.dict("os.environ", TEST_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        contract = confirmed_demo_contract(
            route="exa", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(contract, NOW, registry=self.registry, environ=TEST_ENV)
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "exa", 1, "fp-test", NOW
        )

    def attempt_statuses(self, action_id: str = "A1") -> list[str]:
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        return [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    @unittest.skipUnless(SUCCESS_FIXTURE.exists(), "recorded Exa success fixture not created yet")
    def test_success_records_result_listing_and_cost(self) -> None:
        fixture = json.loads(SUCCESS_FIXTURE.read_text())
        expected_results = [
            item
            for item in fixture["results"]
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"]
        ]
        result = execute_probe(
            self.session,
            "A1",
            "reliable agent evaluation",
            NOW,
            transport=fixture_transport("exa_success.json"),
            environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "exa")
        self.assertEqual(occurrence["kind"], "result_listing")
        self.assertEqual(occurrence["model"], "exa/search-auto")
        self.assertEqual(occurrence["citation_count"], len(expected_results))
        self.assertEqual(occurrence["cost_usd"], fixture["costDollars"]["total"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])
        self.assertEqual(len(load_state(self.session)["retrieval_occurrences"]), 1)
        self.assertEqual(Path(result["spool_path"]).read_bytes(), SUCCESS_FIXTURE.read_bytes())
        self.assertEqual(validate_session(self.session, check_report=False).errors, ())

    def test_http_error_consumes_permit_and_spools_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("exa_error_body.json", status=429),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertIn("rate_limit_exceeded", (self.session / "provider_spool/A1.raw.json").read_text())
        self._assert_permit_consumed()

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("exa_missing_results.json"),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool/A1.raw.json").exists())

    def test_transport_failure_consumes_permit(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=failing_transport(urllib.error.URLError("connection refused")),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "failed"])
        self._assert_permit_consumed()

    def test_timeout_is_uncertain_and_consumes_permit(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=failing_transport(socket.timeout("timed out")),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "uncertain"])
        self._assert_permit_consumed()

    def test_second_execution_is_refused(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("exa_error_body.json", status=429),
                environ=TEST_ENV,
            )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("exa_error_body.json", status=429),
                environ=TEST_ENV,
            )

    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "missing",
                "q",
                NOW,
                transport=fixture_transport("exa_error_body.json", status=429),
                environ=TEST_ENV,
            )

    def test_missing_key_refuses_before_attempt(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "EXA_API_KEY"):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("exa_error_body.json"),
                environ={},
            )
        self.assertEqual(self.attempt_statuses(), [])

    def _assert_permit_consumed(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "exa", 1, "fp2", NOW
            )


if __name__ == "__main__":
    unittest.main()
