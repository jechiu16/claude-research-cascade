from __future__ import annotations

import copy
import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any

from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.providers import load_provider_registry
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract

FIXTURES = Path(__file__).with_name("fixtures")
_SUCCESS_FIXTURE = FIXTURES / "scholar_success.json"
_SUCCESS_FIXTURE_MISSING_REASON = (
    "tests/fixtures/scholar_success.json not recorded: Semantic Scholar's "
    "keyless shared pool returned HTTP 429 on all 27 sequential, "
    "never-parallel live requests attempted during adapter development "
    "(2026-07-11) -- spaced from 0s to 900s apart across 8 retry rounds, "
    "including a minimal limit=1 request, direct header inspection (no "
    "Retry-After; AWS API Gateway TooManyRequestsException), and one "
    "attempt through the real harness pipeline (execute_probe raised "
    "BoundaryError as designed). Consistent with the shared anonymous-tier "
    "quota being exhausted rather than a client-pacing problem. Per the "
    "adapters/README.md rule, a synthetic success fixture is not an "
    "acceptable substitute. Re-run the recording script once the pool "
    "recovers (or with S2_API_KEY set) to record the real fixture; these "
    "tests will activate automatically the moment the file exists."
)


def _scholar_enabled_registry() -> dict[str, Any]:
    """The shipped registry ships scholar with enabled: false — the orchestrator
    flips it once adoption evidence is in. Tests exercise the adapter under the
    exact record that will ship, with only that one bit flipped, so the
    contract/state validation pipeline runs for real instead of being bypassed.
    """
    registry = copy.deepcopy(load_provider_registry())
    for provider in registry["providers"]:
        if provider["id"] == "scholar":
            provider["enabled"] = True
    return registry


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def failing_transport(exc: Exception):
    def transport(spec):
        raise exc

    return transport


class ScholarAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = _scholar_enabled_registry()
        contract = confirmed_demo_contract(
            route="scholar", request_count=1, probe_ceiling=2, registry=self.registry
        )
        # scholar requires no credential, so environ stays empty (no os.environ
        # patching needed the way sonar's tests patch in PERPLEXITY_API_KEY).
        state = new_state("boundary test question", contract, NOW, registry=self.registry, environ={})
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "scholar", 1, "fp-test", NOW
        )

    def attempt_statuses(self, action_id: str = "A1") -> list[str]:
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        return [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    @unittest.skipUnless(_SUCCESS_FIXTURE.exists(), _SUCCESS_FIXTURE_MISSING_REASON)
    def test_success_records_occurrence_and_completes_attempt(self) -> None:
        # Expectations come from the fixture itself: it is a recorded real
        # response (live scholar call 2026-07-11) and may be re-recorded later.
        fixture = json.loads((FIXTURES / "scholar_success.json").read_text())
        papers = fixture.get("data", [])
        expected_returned = len(papers)
        expected_total = fixture.get("total")

        result = execute_probe(
            self.session, "A1", "retrieval augmented generation hallucination", NOW,
            transport=fixture_transport("scholar_success.json"), environ={},
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "scholar")
        self.assertEqual(occurrence["kind"], "paper_listing")
        self.assertEqual(occurrence["model"], "s2-graph/paper-search")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], expected_returned)
        self.assertTrue(occurrence["synthesis_excerpt"].strip())
        self.assertEqual(
            self.attempt_statuses(), ["attempted", "accepted", "completed"]
        )

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        spooled = json.loads(spool.read_text())
        self.assertEqual(spooled.get("total"), expected_total)
        self.assertEqual(len(spooled.get("data", [])), expected_returned)

        # Every citation is url/title/date-shaped, one per paper in the fixture.
        self.assertEqual(len(occurrence["citations"]), min(expected_returned, 40))
        for citation in occurrence["citations"]:
            self.assertEqual(set(citation), {"url", "title", "date"})

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_error_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("scholar_rate_limited.json", status=429),
                environ={},
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("Too Many Requests", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "scholar", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("scholar_missing_data.json"), environ={},
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool" / "A1.raw.json").exists())

    def test_transport_failure_fails_attempt(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=failing_transport(urllib.error.URLError("connection refused")),
                environ={},
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "failed"])

    def test_timeout_marks_attempt_uncertain(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=failing_transport(socket.timeout("timed out")), environ={},
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "uncertain"])

    def test_second_execution_of_same_action_is_refused(self) -> None:
        # Any recorded attempt_status blocks a second execute_probe on the
        # same action_id (success or failure alike) -- this only needs *a*
        # payload, so it does not depend on the (currently unrecorded, see
        # test_success_records_occurrence_and_completes_attempt) success
        # fixture.
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("scholar_rate_limited.json", status=429),
                environ={},
            )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("scholar_rate_limited.json", status=429),
                environ={},
            )

    def test_unknown_action_is_refused(self) -> None:
        # _permit_for rejects an action with no acquired permit before the
        # transport is ever called, so any fixture works here.
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "missing", "q", NOW,
                transport=fixture_transport("scholar_rate_limited.json", status=429),
                environ={},
            )


class ScholarBuildTests(unittest.TestCase):
    """build() is pure: no network, no side effects — check it directly."""

    def test_build_is_a_get_with_no_body_and_url_encoded_params(self) -> None:
        from research_harness.adapters import scholar

        spec = scholar.build("dynamic factor model nowcasting", {})
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.body, b"")
        self.assertTrue(spec.url.startswith("https://api.semanticscholar.org/graph/v1/paper/search?"))
        self.assertIn("query=dynamic+factor+model+nowcasting", spec.url)
        self.assertIn("limit=20", spec.url)
        self.assertIn("fields=title%2Cyear%2Cabstract%2CcitationCount%2Cauthors%2Curl%2CopenAccessPdf%2Ctldr", spec.url)
        self.assertNotIn("x-api-key", spec.headers)

    def test_build_sends_key_header_only_when_present(self) -> None:
        from research_harness.adapters import scholar

        spec = scholar.build("q", {"S2_API_KEY": "secret-value"})
        self.assertEqual(spec.headers.get("x-api-key"), "secret-value")
        # Credentials never leak into the URL.
        self.assertNotIn("secret-value", spec.url)

    def test_build_never_requires_a_key(self) -> None:
        from research_harness.adapters import scholar

        # Must not raise BoundaryError: scholar is a keyless shared-pool route.
        spec = scholar.build("q", {})
        self.assertEqual(spec.headers, {})


class ScholarParseTests(unittest.TestCase):
    """parse() is pure: check it directly against edge-case payload shapes
    that a fixture-only test suite would not otherwise exercise."""

    def test_parse_rejects_non_object_top_level_json(self) -> None:
        # A bare JSON array/string/number/null is valid JSON but not a
        # provider-contract match; data.get("data") on a non-dict would
        # otherwise raise AttributeError instead of AdapterParseError.
        from research_harness.adapters import scholar

        for bad in (b"[1, 2, 3]", b'"just a string"', b"42", b"null", b"true"):
            with self.subTest(payload=bad):
                with self.assertRaises(AdapterParseError):
                    scholar.parse(bad)

    def test_parse_handles_papers_with_missing_optional_fields(self) -> None:
        from research_harness.adapters import scholar

        payload = json.dumps(
            {
                "total": 1,
                "data": [
                    {
                        "title": None,
                        "year": None,
                        "citationCount": None,
                        "abstract": None,
                        "tldr": None,
                        "url": None,
                    }
                ],
            }
        ).encode("utf-8")
        result = scholar.parse(payload)
        self.assertEqual(result.kind, "paper_listing")
        self.assertEqual(result.citations, [{"url": None, "title": "(untitled)", "date": None}])
        self.assertIn("(untitled)", result.synthesis_text)

    def test_parse_truncates_excerpt_to_200_chars(self) -> None:
        from research_harness.adapters import scholar

        payload = json.dumps(
            {"total": 1, "data": [{"title": "T", "year": 2020, "abstract": "x" * 500}]}
        ).encode("utf-8")
        result = scholar.parse(payload)
        self.assertIn("x" * 200, result.synthesis_text)
        self.assertNotIn("x" * 201, result.synthesis_text)


if __name__ == "__main__":
    unittest.main()
