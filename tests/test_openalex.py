from __future__ import annotations

import json
import socket
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from research_harness.adapters import openalex
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")

TEST_ENV = {"OPENALEX_API_KEY": "test-openalex-key"}


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def failing_transport(exc: Exception):
    def transport(spec):
        raise exc

    return transport


class OpenAlexBuildTests(unittest.TestCase):
    """build() is pure: no network, no side effects -- check it directly."""

    def test_build_is_a_get_with_no_body_and_url_encoded_params(self) -> None:
        spec = openalex.build("retrieval augmented generation", TEST_ENV)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(spec.url).query)
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.body, b"")
        self.assertTrue(spec.url.startswith("https://api.openalex.org/works?"))
        self.assertEqual(query["search"], ["retrieval augmented generation"])
        self.assertEqual(query["per_page"], ["20"])
        self.assertEqual(query["api_key"], ["test-openalex-key"])
        self.assertEqual(
            query["select"],
            ["id,doi,display_name,publication_year,publication_date,cited_by_count,is_retracted,primary_location"],
        )
        self.assertNotIn("mailto", query)
        self.assertEqual(spec.headers["User-Agent"], "research-harness-v2")
        self.assertEqual(spec.timeout_s, 30.0)

    def test_build_requires_api_key(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "OPENALEX_API_KEY"):
            openalex.build("q", {})

    def test_build_sends_api_key_param_only_when_present(self) -> None:
        spec = openalex.build("q", {"OPENALEX_API_KEY": "secret-value"})
        self.assertIn("api_key=secret-value", spec.url)

    def test_build_rejects_empty_api_key(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "OPENALEX_API_KEY"):
            openalex.build("q", {"OPENALEX_API_KEY": ""})

    def test_build_headers_are_limited_to_user_agent(self) -> None:
        # OpenAlex has no header-based key mechanism -- the credential (when
        # present) travels only in the documented api_key query param, never
        # as a header alongside it.
        spec = openalex.build("q", {"OPENALEX_API_KEY": "secret-value"})
        self.assertEqual(set(spec.headers), {"User-Agent"})

    def test_fingerprint_excludes_api_key_but_preserves_query(self) -> None:
        from research_harness.boundary import _request_fingerprint

        first = _request_fingerprint(openalex.build("same query", {"OPENALEX_API_KEY": "key-one"}))
        rotated = _request_fingerprint(
            openalex.build("same query", {"OPENALEX_API_KEY": "key-two"})
        )
        changed_query = _request_fingerprint(
            openalex.build("different query", {"OPENALEX_API_KEY": "key-two"})
        )
        self.assertEqual(first, rotated)
        self.assertNotEqual(first, changed_query)


class OpenAlexParseTests(unittest.TestCase):
    """parse() is pure: check it directly against edge-case payload shapes
    that a fixture-only test suite would not otherwise exercise."""

    def test_parse_raises_on_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            openalex.parse(b"not json at all")

    def test_parse_rejects_non_object_top_level_json(self) -> None:
        # A bare JSON array/string/number/null is valid JSON but not a
        # provider-contract match; data.get("results") on a non-dict would
        # otherwise raise AttributeError instead of AdapterParseError.
        for bad in (b"[1, 2, 3]", b'"just a string"', b"42", b"null", b"true"):
            with self.subTest(payload=bad):
                with self.assertRaises(AdapterParseError):
                    openalex.parse(bad)

    def test_parse_raises_when_results_missing(self) -> None:
        payload = json.dumps({"meta": {"count": 1}}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            openalex.parse(payload)

    def test_parse_raises_when_results_is_not_a_list(self) -> None:
        payload = json.dumps({"meta": {"count": 1}, "results": {}}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            openalex.parse(payload)

    def test_parse_handles_empty_results_list(self) -> None:
        payload = json.dumps({"meta": {"count": 0}, "results": []}).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertEqual(result.synthesis_text, "")
        self.assertEqual(result.usage, {"total_results": 0, "returned": 0})

    def test_citation_url_prefers_doi_over_landing_page_and_id(self) -> None:
        payload = json.dumps(
            {
                "meta": {"count": 1},
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "doi": "https://doi.org/10.1/x",
                        "display_name": "T",
                        "publication_year": 2020,
                        "cited_by_count": 5,
                        "primary_location": {"landing_page_url": "https://example.test/landing"},
                    }
                ],
            }
        ).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.citations[0]["url"], "https://doi.org/10.1/x")

    def test_citation_url_falls_back_to_landing_page_when_doi_missing(self) -> None:
        payload = json.dumps(
            {
                "meta": {"count": 1},
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "doi": None,
                        "display_name": "T",
                        "publication_year": 2020,
                        "cited_by_count": 5,
                        "primary_location": {"landing_page_url": "https://example.test/landing"},
                    }
                ],
            }
        ).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.citations[0]["url"], "https://example.test/landing")

    def test_citation_url_falls_back_to_id_when_doi_and_landing_page_missing(self) -> None:
        payload = json.dumps(
            {
                "meta": {"count": 1},
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "doi": None,
                        "display_name": "T",
                        "publication_year": 2020,
                        "cited_by_count": 5,
                        "primary_location": None,
                    }
                ],
            }
        ).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.citations[0]["url"], "https://openalex.org/W1")

    def test_unresolvable_work_is_listed_but_not_counted_as_citation(self) -> None:
        payload = json.dumps(
            {
                "meta": {"count": 1},
                "results": [{"id": None, "doi": None, "primary_location": None}],
            }
        ).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertIn("(untitled)", result.synthesis_text)

    def test_parse_handles_works_with_missing_optional_fields(self) -> None:
        payload = json.dumps(
            {
                "meta": {"count": 1},
                "results": [
                    {
                        "id": None,
                        "doi": None,
                        "display_name": None,
                        "publication_year": None,
                        "cited_by_count": None,
                        "primary_location": None,
                    }
                ],
            }
        ).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.kind, "paper_listing")
        self.assertEqual(result.citations, [])
        self.assertIn("(untitled)", result.synthesis_text)
        self.assertIn("?", result.synthesis_text)

    def test_parse_skips_non_dict_entries_in_results(self) -> None:
        payload = json.dumps({"meta": {"count": 1}, "results": [None, "x", 1]}).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertEqual(result.synthesis_text, "")

    def test_parse_handles_missing_meta(self) -> None:
        payload = json.dumps({"results": []}).encode("utf-8")
        result = openalex.parse(payload)
        self.assertEqual(result.usage, {"total_results": None, "returned": 0})

    def test_parse_preserves_provider_reported_cost(self) -> None:
        payload = json.dumps(
            {"meta": {"count": 0, "cost_usd": 0.001}, "results": []}
        ).encode("utf-8")
        self.assertEqual(openalex.parse(payload).cost_usd, 0.001)

    def test_parse_marks_retracted_works(self) -> None:
        payload = json.dumps(
            {
                "meta": {"count": 1, "cost_usd": 0.001},
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "Retracted result",
                        "publication_year": 2020,
                        "cited_by_count": 5,
                        "is_retracted": True,
                    }
                ],
            }
        ).encode("utf-8")
        self.assertIn("[RETRACTED]", openalex.parse(payload).synthesis_text)

    def test_every_citation_is_url_title_date_shaped_against_fixture(self) -> None:
        fixture = json.loads((FIXTURES / "openalex_success.json").read_text())
        result = openalex.parse((FIXTURES / "openalex_success.json").read_bytes())
        self.assertEqual(len(result.citations), len(fixture["results"]))
        for citation in result.citations:
            self.assertEqual(set(citation), {"url", "title", "date"})


class OpenAlexAdapterTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_boundary.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = enabled_registry_copy("openalex")
        patcher = mock.patch.dict("os.environ", TEST_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        contract = confirmed_demo_contract(
            route="openalex", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(
            "boundary test question", contract, NOW, registry=self.registry, environ=TEST_ENV
        )
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "openalex", 1, "fp-test", NOW
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
        # response (live openalex call 2026-07-11, query "retrieval
        # augmented generation") and may be re-recorded later.
        fixture = json.loads((FIXTURES / "openalex_success.json").read_text())
        works = fixture["results"]
        expected_total = fixture["meta"]["count"]

        result = execute_probe(
            self.session, "A1", "retrieval augmented generation", NOW,
            transport=fixture_transport("openalex_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "openalex")
        self.assertEqual(occurrence["kind"], "paper_listing")
        self.assertEqual(occurrence["model"], "openalex/works-search")
        self.assertEqual(occurrence["cost_usd"], fixture["meta"]["cost_usd"])
        self.assertEqual(occurrence["citation_count"], len(works))
        self.assertTrue(occurrence["synthesis_excerpt"].strip())
        self.assertIn(works[0]["display_name"], occurrence["synthesis_excerpt"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        spooled = json.loads(spool.read_text())
        self.assertEqual(spooled["meta"]["count"], expected_total)
        self.assertEqual(len(spooled["results"]), len(works))

        # Every citation is url/title/date-shaped, one per work in the fixture.
        self.assertEqual(len(occurrence["citations"]), len(works))
        for citation in occurrence["citations"]:
            self.assertEqual(set(citation), {"url", "title", "date"})

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_error_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("openalex_error_body.json", status=429),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("RateLimitError", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "openalex", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("openalex_missing_results.json"), environ=TEST_ENV,
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
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "openalex", 1, "fp2", NOW
            )

    def test_timeout_marks_attempt_uncertain(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=failing_transport(socket.timeout("timed out")), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "uncertain"])
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "openalex", 1, "fp2", NOW
            )

    def test_second_execution_of_same_action_is_refused(self) -> None:
        # Any recorded attempt_status blocks a second execute_probe on the
        # same action_id (success or failure alike) -- this only needs *a*
        # payload, independent of which fixture is used.
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("openalex_error_body.json", status=429),
                environ=TEST_ENV,
            )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("openalex_error_body.json", status=429),
                environ=TEST_ENV,
            )

    def test_unknown_action_is_refused(self) -> None:
        # _permit_for rejects an action with no acquired permit before the
        # transport is ever called, so any fixture works here.
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "missing", "q", NOW,
                transport=fixture_transport("openalex_error_body.json", status=429),
                environ=TEST_ENV,
            )

    def test_missing_key_refuses_before_any_attempt(self) -> None:
        with self.assertRaisesRegex(BoundaryError, "OPENALEX_API_KEY"):
            execute_probe(
                self.session, "A1", "retrieval augmented generation", NOW,
                transport=fixture_transport("openalex_success.json"), environ={},
            )
        self.assertEqual(self.attempt_statuses(), [])


if __name__ == "__main__":
    unittest.main()
