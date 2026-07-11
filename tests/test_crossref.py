from __future__ import annotations

import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path

from research_harness.adapters import crossref
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")

# crossref is keyless: the mailto param is an email address for the polite
# pool, not a credential, so every session in this suite runs with an empty
# environ (matching scholar's and github's keyless test pattern).
TEST_ENV: dict[str, str] = {}


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def failing_transport(exc: Exception):
    def transport(spec):
        raise exc

    return transport


class CrossrefAdapterBoundaryTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_boundary.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = enabled_registry_copy("crossref")
        contract = confirmed_demo_contract(
            route="crossref", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(
            "boundary test question", contract, NOW, registry=self.registry, environ=TEST_ENV,
        )
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "crossref", 1, "fp-test", NOW
        )

    def attempt_statuses(self, action_id: str = "A1") -> list[str]:
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        return [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    def test_success_records_occurrence_with_expectations_from_fixture(self) -> None:
        # Expectations come from the fixture itself: it is a recorded real
        # response (live crossref call 2026-07-11, query "dynamic factor
        # model nowcasting") and may be re-recorded later.
        fixture = json.loads((FIXTURES / "crossref_success.json").read_text())
        message = fixture["message"]
        items = message["items"]
        expected_returned = len(items)
        expected_total = message["total-results"]
        first_item = items[0]
        first_doi = first_item["DOI"]
        first_title = first_item["title"][0]
        # This record's issued.date-parts is [[None]] in the real payload --
        # a genuine Crossref edge case (a dissertation record with no issued
        # date; only "approved" carries a year) -- so the first citation's
        # date must come through as None rather than crash or fall back to
        # today's date.
        self.assertEqual(first_item["issued"]["date-parts"], [[None]])

        result = execute_probe(
            self.session, "A1", "dynamic factor model nowcasting", NOW,
            transport=fixture_transport("crossref_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "crossref")
        self.assertEqual(occurrence["kind"], "paper_listing")
        self.assertEqual(occurrence["model"], "crossref/works-search")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], expected_returned)
        self.assertEqual(
            occurrence["citations"][0],
            {"url": f"https://doi.org/{first_doi}", "title": first_title, "date": None},
        )
        self.assertTrue(occurrence["synthesis_excerpt"].strip())
        self.assertIn(str(expected_total), occurrence["synthesis_excerpt"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        spooled = json.loads(spool.read_text())
        self.assertEqual(spooled["message"]["total-results"], expected_total)
        self.assertEqual(len(spooled["message"]["items"]), expected_returned)

        # Every citation is url/title/date-shaped, one per item in the fixture.
        self.assertEqual(len(occurrence["citations"]), min(expected_returned, 40))
        for citation in occurrence["citations"]:
            self.assertEqual(set(citation), {"url", "title", "date"})
            self.assertTrue(citation["url"].startswith("https://doi.org/"))

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_error_consumes_permit_and_preserves_payload(self) -> None:
        # Real recorded 400 (live crossref call 2026-07-11 with a
        # deliberately invalid rows param): Crossref's own validation-failure
        # body has "message" as a LIST, not an object.
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("crossref_bad_request.json", status=400),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("validation-failure", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "crossref", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("crossref_missing_items.json"), environ=TEST_ENV,
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
            self.session, "A1", "dynamic factor model nowcasting", NOW,
            transport=fixture_transport("crossref_success.json"), environ=TEST_ENV,
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "dynamic factor model nowcasting", NOW,
                transport=fixture_transport("crossref_success.json"), environ=TEST_ENV,
            )

    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "missing", "q", NOW,
                transport=fixture_transport("crossref_bad_request.json", status=400),
                environ=TEST_ENV,
            )

    def test_succeeds_with_no_environment_at_all(self) -> None:
        # crossref is keyless: unlike sonar (PERPLEXITY_API_KEY required), an
        # empty environ must not block the route.
        result = execute_probe(
            self.session, "A1", "dynamic factor model nowcasting", NOW,
            transport=fixture_transport("crossref_success.json"), environ={},
        )
        self.assertEqual(result["occurrence"]["provider_id"], "crossref")


class CrossrefBuildTests(unittest.TestCase):
    """build() is pure: no network, no side effects -- check it directly."""

    def test_build_is_a_get_with_no_body_and_url_encoded_params(self) -> None:
        spec = crossref.build("dynamic factor model nowcasting", {})
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.body, b"")
        self.assertEqual(spec.timeout_s, 30.0)
        self.assertTrue(spec.url.startswith("https://api.crossref.org/works?"))
        self.assertIn("query=dynamic+factor+model+nowcasting", spec.url)
        self.assertIn("rows=20", spec.url)
        self.assertIn("mailto=samuel7014%40gmail.com", spec.url)
        self.assertEqual(
            spec.headers["User-Agent"], "research-harness-v2 (mailto:samuel7014@gmail.com)"
        )

    def test_build_never_requires_a_key(self) -> None:
        # Must not raise: crossref is a fully keyless route (no optional
        # credential upgrade either, unlike scholar's S2_API_KEY).
        spec = crossref.build("q", {})
        self.assertNotIn("Authorization", spec.headers)

    def test_build_ignores_environment_contents(self) -> None:
        # No env var is ever read by this adapter, so unrelated environment
        # contents must not change the request.
        spec_empty = crossref.build("q", {})
        spec_with_env = crossref.build("q", {"SOME_OTHER_KEY": "value"})
        self.assertEqual(spec_empty.url, spec_with_env.url)
        self.assertEqual(spec_empty.headers, spec_with_env.headers)


class CrossrefParseTests(unittest.TestCase):
    """parse() is pure: check it directly against edge-case payload shapes
    that a fixture-only test suite would not otherwise exercise."""

    def test_parse_rejects_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            crossref.parse(b"not json at all")

    def test_parse_rejects_non_object_top_level_json(self) -> None:
        for bad in (b"[1, 2, 3]", b'"just a string"', b"42", b"null", b"true"):
            with self.subTest(payload=bad):
                with self.assertRaises(AdapterParseError):
                    crossref.parse(bad)

    def test_parse_rejects_message_that_is_not_an_object(self) -> None:
        # The real Crossref 400 validation-failure body has "message" as a
        # LIST, not an object -- the live edge case behind the explicit
        # isinstance(message, dict) guard.
        payload = json.dumps(
            {"status": "failed", "message": [{"type": "integer-not-valid"}]}
        ).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            crossref.parse(payload)

    def test_parse_rejects_missing_items_list(self) -> None:
        payload = json.dumps({"message": {"total-results": 0}}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            crossref.parse(payload)

    def test_parse_handles_items_with_missing_optional_fields(self) -> None:
        payload = json.dumps(
            {
                "message": {
                    "total-results": 1,
                    "items": [
                        {
                            "title": None,
                            "DOI": None,
                            "issued": None,
                            "is-referenced-by-count": None,
                        }
                    ],
                }
            }
        ).encode("utf-8")
        result = crossref.parse(payload)
        self.assertEqual(result.kind, "paper_listing")
        self.assertEqual(result.citations, [{"url": None, "title": None, "date": None}])
        self.assertIn("(untitled)", result.synthesis_text)

    def test_parse_falls_back_to_doi_when_title_is_missing(self) -> None:
        payload = json.dumps(
            {
                "message": {
                    "total-results": 1,
                    "items": [
                        {"title": [], "DOI": "10.1/example", "issued": {"date-parts": [[2020]]}}
                    ],
                }
            }
        ).encode("utf-8")
        result = crossref.parse(payload)
        self.assertEqual(
            result.citations,
            [{"url": "https://doi.org/10.1/example", "title": "10.1/example", "date": "2020"}],
        )

    def test_parse_handles_null_first_date_part(self) -> None:
        # Live-observed shape: issued.date-parts == [[None]] on records with
        # no issued date (e.g. a dissertation where only "approved" carries
        # a year).
        payload = json.dumps(
            {
                "message": {
                    "total-results": 1,
                    "items": [
                        {"title": ["T"], "DOI": "10.1/x", "issued": {"date-parts": [[None]]}}
                    ],
                }
            }
        ).encode("utf-8")
        result = crossref.parse(payload)
        self.assertIsNone(result.citations[0]["date"])
        self.assertIn("(?)", result.synthesis_text)

    def test_parse_skips_non_dict_items_defensively(self) -> None:
        payload = json.dumps(
            {"message": {"total-results": 2, "items": [None, {"title": ["T"], "DOI": "10.1/x"}]}}
        ).encode("utf-8")
        result = crossref.parse(payload)
        self.assertEqual(len(result.citations), 1)

    def test_usage_reports_total_and_returned_counts(self) -> None:
        fixture = json.loads((FIXTURES / "crossref_success.json").read_text())
        payload = (FIXTURES / "crossref_success.json").read_bytes()
        result = crossref.parse(payload)
        self.assertEqual(
            result.usage,
            {
                "total_results": fixture["message"]["total-results"],
                "returned": len(fixture["message"]["items"]),
            },
        )


if __name__ == "__main__":
    unittest.main()
