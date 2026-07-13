from __future__ import annotations

import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from research_harness.adapters import brave
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy


TEST_ENV = {"BRAVE_SEARCH_API_KEY": "test-brave-key"}
FIXTURES = Path(__file__).with_name("fixtures")
SUCCESS_FIXTURE = FIXTURES / "brave_success.json"


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def failing_transport(exc: Exception):
    def transport(spec):
        raise exc

    return transport


class BraveBuildTests(unittest.TestCase):
    def test_build_is_one_bounded_web_search_get(self) -> None:
        spec = brave.build("reliable agent evaluation harness", TEST_ENV)

        self.assertEqual(spec.method, "GET")
        self.assertTrue(spec.url.startswith("https://api.search.brave.com/res/v1/web/search?"))
        self.assertIn("q=reliable+agent+evaluation+harness", spec.url)
        self.assertIn("count=20", spec.url)
        self.assertEqual(spec.headers["Accept"], "application/json")
        self.assertEqual(spec.headers["X-Subscription-Token"], "test-brave-key")
        self.assertEqual(spec.body, b"")
        self.assertEqual(spec.timeout_s, 30.0)

    def test_build_requires_api_key(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "BRAVE_SEARCH_API_KEY"):
            brave.build("q", {})

    def test_build_rejects_empty_api_key(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "BRAVE_SEARCH_API_KEY"):
            brave.build("q", {"BRAVE_SEARCH_API_KEY": ""})


class BraveParseTests(unittest.TestCase):
    def test_parse_rejects_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            brave.parse(b"not json")

    def test_parse_rejects_non_object_top_level(self) -> None:
        for payload in (b"[]", b'"text"', b"42", b"null", b"true"):
            with self.subTest(payload=payload):
                with self.assertRaises(AdapterParseError):
                    brave.parse(payload)

    def test_parse_requires_web_object(self) -> None:
        for value in (None, [], "web", 1):
            with self.subTest(value=value):
                payload = json.dumps({"web": value}).encode("utf-8")
                with self.assertRaises(AdapterParseError):
                    brave.parse(payload)

    def test_parse_requires_results_list(self) -> None:
        for value in (None, {}, "results", 1):
            with self.subTest(value=value):
                payload = json.dumps({"web": {"results": value}}).encode("utf-8")
                with self.assertRaises(AdapterParseError):
                    brave.parse(payload)

    def test_parse_returns_numbered_result_listing(self) -> None:
        payload = json.dumps(
            {
                "web": {
                    "results": [
                        {
                            "title": "First result",
                            "url": "https://example.test/one",
                            "description": "First description",
                            "page_age": "2026-01-02T00:00:00",
                        },
                        {
                            "title": "Second result",
                            "url": "https://example.test/two",
                            "description": "Second description",
                            "age": "2 days ago",
                        },
                    ]
                }
            }
        ).encode("utf-8")

        result = brave.parse(payload)

        self.assertEqual(result.kind, "result_listing")
        self.assertEqual(result.model, "brave-web-search/v1")
        self.assertIsNone(result.cost_usd)
        self.assertEqual(result.usage, {"result_count": 2})
        self.assertEqual(
            result.citations,
            [
                {"url": "https://example.test/one", "title": "First result", "date": "2026-01-02T00:00:00"},
                {"url": "https://example.test/two", "title": "Second result", "date": "2 days ago"},
            ],
        )
        self.assertIn("1. First result — https://example.test/one", result.synthesis_text)
        self.assertIn("First description", result.synthesis_text)
        self.assertIn("2. Second result — https://example.test/two", result.synthesis_text)

    def test_parse_prefers_page_age_over_age(self) -> None:
        payload = json.dumps(
            {
                "web": {
                    "results": [
                        {
                            "title": "Both dates",
                            "url": "https://example.test/both",
                            "page_age": "2026-01-01T00:00:00",
                            "age": "1 year ago",
                        }
                    ]
                }
            }
        ).encode("utf-8")
        result = brave.parse(payload)
        self.assertEqual(result.citations[0]["date"], "2026-01-01T00:00:00")

    def test_parse_date_is_none_when_neither_present(self) -> None:
        payload = json.dumps(
            {"web": {"results": [{"title": "No date", "url": "https://example.test/nodate"}]}}
        ).encode("utf-8")
        result = brave.parse(payload)
        self.assertIsNone(result.citations[0]["date"])

    def test_parse_strips_highlight_tags_before_truncating_excerpt(self) -> None:
        description = "A" * 150 + "<strong>" + "B" * 20 + "</strong>" + "C" * 50
        payload = json.dumps(
            {"web": {"results": [{"title": "T", "url": "https://example.test/x", "description": description}]}}
        ).encode("utf-8")
        result = brave.parse(payload)
        self.assertNotIn("<strong>", result.synthesis_text)
        self.assertNotIn("</strong>", result.synthesis_text)
        self.assertIn("A" * 150 + "B" * 10, result.synthesis_text)
        self.assertNotIn("B" * 11, result.synthesis_text)

    def test_parse_lists_unresolvable_result_without_counting_citation(self) -> None:
        payload = json.dumps(
            {"web": {"results": [{"title": "Missing URL", "url": None, "description": "d"}]}}
        ).encode("utf-8")
        result = brave.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertIn("Missing URL", result.synthesis_text)
        self.assertEqual(result.usage, {"result_count": 1})

    def test_parse_rejects_non_web_citation_urls(self) -> None:
        payload = json.dumps(
            {"web": {"results": [{"title": "Unsafe URL", "url": "javascript:alert(1)"}]}}
        ).encode("utf-8")
        self.assertEqual(brave.parse(payload).citations, [])

    def test_parse_handles_empty_results(self) -> None:
        result = brave.parse(json.dumps({"web": {"results": []}}).encode("utf-8"))
        self.assertEqual(result.citations, [])
        self.assertEqual(result.synthesis_text, "")
        self.assertEqual(result.usage, {"result_count": 0})

    def test_parse_result_count_includes_unrenderable_items(self) -> None:
        payload = json.dumps(
            {"web": {"results": [{"title": "Real", "url": "https://example.test/real"}, "not-a-dict"]}}
        ).encode("utf-8")
        result = brave.parse(payload)
        self.assertEqual(result.usage, {"result_count": 2})
        self.assertEqual(len(result.citations), 1)

    @unittest.skipUnless(SUCCESS_FIXTURE.exists(), "recorded Brave success fixture not created yet")
    def test_parse_handles_recorded_live_fixture(self) -> None:
        payload = SUCCESS_FIXTURE.read_bytes()
        result = brave.parse(payload)
        fixture = json.loads(payload)
        web_results = fixture["web"]["results"]
        self.assertEqual(result.kind, "result_listing")
        self.assertEqual(result.usage["result_count"], len(web_results))
        self.assertTrue(result.synthesis_text.startswith("1. "))


class BraveBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.session = Path(self.tempdir.name) / "session"
        self.registry = enabled_registry_copy("brave")
        patcher = mock.patch.dict("os.environ", TEST_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        contract = confirmed_demo_contract(
            route="brave", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(contract, NOW, registry=self.registry, environ=TEST_ENV)
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "brave", 1, "fp-test", NOW
        )

    def attempt_statuses(self, action_id: str = "A1") -> list[str]:
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        return [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    @unittest.skipUnless(SUCCESS_FIXTURE.exists(), "recorded Brave success fixture not created yet")
    def test_success_records_result_listing_and_citation_count(self) -> None:
        # Expectations come from the fixture itself: it is a recorded real
        # response (live brave call 2026-07-11) and may be re-recorded later.
        fixture = json.loads(SUCCESS_FIXTURE.read_text())
        web_results = fixture["web"]["results"]
        expected_citations = [
            item
            for item in web_results
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"]
        ]
        result = execute_probe(
            self.session,
            "A1",
            "reliable agent evaluation harness",
            NOW,
            transport=fixture_transport("brave_success.json"),
            environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "brave")
        self.assertEqual(occurrence["kind"], "result_listing")
        self.assertEqual(occurrence["model"], "brave-web-search/v1")
        self.assertEqual(occurrence["citation_count"], len(expected_citations))
        self.assertIsNone(occurrence["cost_usd"])
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
                transport=fixture_transport("brave_invalid_token.json", status=401),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertIn("UNAUTHORIZED", (self.session / "provider_spool/A1.raw.json").read_text())
        self._assert_permit_consumed()

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("brave_missing_results.json"),
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
                transport=fixture_transport("brave_invalid_token.json", status=401),
                environ=TEST_ENV,
            )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("brave_invalid_token.json", status=401),
                environ=TEST_ENV,
            )

    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session,
                "missing",
                "q",
                NOW,
                transport=fixture_transport("brave_invalid_token.json", status=401),
                environ=TEST_ENV,
            )

    def test_missing_key_refuses_before_any_attempt(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "BRAVE_SEARCH_API_KEY"):
            execute_probe(
                self.session,
                "A1",
                "q",
                NOW,
                transport=fixture_transport("brave_invalid_token.json"),
                environ={},
            )
        self.assertEqual(self.attempt_statuses(), [])

    def _assert_permit_consumed(self) -> None:
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "brave", 1, "fp2", NOW
            )


if __name__ == "__main__":
    unittest.main()
