from __future__ import annotations

import json
import http.server
import socket
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from research_harness.boundary import (
    AdapterParseError,
    BoundaryError,
    RequestSpec,
    _urllib_transport,
    execute_probe,
)
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract

FIXTURES = Path(__file__).with_name("fixtures")
TEST_ENV = {"PERPLEXITY_API_KEY": "test-key"}


class RedirectHandler(http.server.BaseHTTPRequestHandler):
    request_count = 0

    def do_GET(self) -> None:
        type(self).request_count += 1
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/final")
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"followed")

    def log_message(self, format: str, *args: object) -> None:
        pass


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def failing_transport(exc: Exception):
    def transport(spec):
        raise exc

    return transport


class BoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        contract = confirmed_demo_contract(route="sonar", request_count=1, probe_ceiling=2)
        state = new_state("boundary test question", contract, NOW, environ=TEST_ENV)
        create_session(self.session, state)
        patcher = mock.patch.dict("os.environ", TEST_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "sonar", 1, "fp-test", NOW
        )

    def attempt_statuses(self, action_id: str = "A1") -> list[str]:
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        return [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    def test_success_records_occurrence_and_completes_attempt(self) -> None:
        # Expectations come from the fixture itself: it is a recorded real
        # response (live sonar call 2026-07-11) and may be re-recorded later.
        fixture = json.loads((FIXTURES / "sonar_success.json").read_text())
        expected_cost = round(fixture["usage"]["cost"]["total_cost"], 4)
        expected_citations = len(
            [item for item in fixture.get("search_results", []) if isinstance(item.get("url"), str)]
        )
        result = execute_probe(
            self.session, "A1", "current fed funds target range", NOW,
            transport=fixture_transport("sonar_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "sonar")
        self.assertEqual(occurrence["citation_count"], expected_citations)
        self.assertAlmostEqual(occurrence["cost_usd"], expected_cost)
        self.assertTrue(occurrence["synthesis_excerpt"].strip())
        self.assertEqual(
            self.attempt_statuses(), ["attempted", "accepted", "completed"]
        )
        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(json.loads(spool.read_text())["model"], "sonar-pro")
        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_error_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("sonar_rate_limited.json", status=429),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("rate_limit_exceeded", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "sonar", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("sonar_missing_content.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool" / "A1.raw.json").exists())

    def test_transport_failure_fails_attempt(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=failing_transport(urllib.error.URLError("connection refused")),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "failed"])

    def test_timeout_marks_attempt_uncertain(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=failing_transport(socket.timeout("timed out")), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "uncertain"])

    def test_second_execution_of_same_action_is_refused(self) -> None:
        execute_probe(
            self.session, "A1", "q", NOW,
            transport=fixture_transport("sonar_success.json"), environ=TEST_ENV,
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("sonar_success.json"), environ=TEST_ENV,
            )

    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "missing", "q", NOW,
                transport=fixture_transport("sonar_success.json"), environ=TEST_ENV,
            )

    def test_missing_key_refuses_before_any_attempt(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("sonar_success.json"), environ={},
            )
        self.assertEqual(self.attempt_statuses(), [])

    def test_transport_refuses_redirect_without_second_physical_request(self) -> None:
        RedirectHandler.request_count = 0
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        spec = RequestSpec(
            "GET",
            f"http://127.0.0.1:{server.server_port}/start",
            {},
            b"",
            2.0,
        )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            _urllib_transport(spec)

        self.assertEqual(raised.exception.code, 302)
        self.assertEqual(RedirectHandler.request_count, 1)


if __name__ == "__main__":
    unittest.main()
