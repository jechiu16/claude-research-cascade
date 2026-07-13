from __future__ import annotations

import json
import socket
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

from research_harness.adapters import europe_pmc
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def failing_transport(exc: Exception):
    def transport(spec):
        raise exc

    return transport


class EuropePmcBuildTests(unittest.TestCase):
    """build() is pure: no network, no side effects -- check it directly."""

    def test_build_is_a_get_with_no_body_and_url_encoded_params(self) -> None:
        spec = europe_pmc.build("CRISPR gene editing efficacy", {})
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(spec.url).query)
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.body, b"")
        self.assertTrue(
            spec.url.startswith("https://www.ebi.ac.uk/europepmc/webservices/rest/search?")
        )
        self.assertEqual(query["query"], ["CRISPR gene editing efficacy"])
        self.assertEqual(query["format"], ["json"])
        self.assertEqual(query["pageSize"], ["20"])
        self.assertEqual(spec.headers, {"User-Agent": "research-harness-v2"})
        self.assertEqual(spec.timeout_s, 30.0)

    def test_build_never_requires_a_key(self) -> None:
        # Must not raise BoundaryError: europe-pmc is a fully keyless route.
        spec = europe_pmc.build("q", {})
        self.assertEqual(spec.headers, {"User-Agent": "research-harness-v2"})

    def test_build_ignores_env_entirely(self) -> None:
        # No credential mechanism exists for this route -- a populated env
        # must never leak into the URL or headers.
        spec = europe_pmc.build("q", {"SOME_OTHER_KEY": "secret-value"})
        self.assertNotIn("secret-value", spec.url)
        self.assertNotIn("secret-value", str(spec.headers))


class EuropePmcParseTests(unittest.TestCase):
    """parse() is pure: check it directly against edge-case payload shapes
    that a fixture-only test suite would not otherwise exercise."""

    def test_parse_raises_on_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            europe_pmc.parse(b"not json at all")

    def test_parse_rejects_non_object_top_level_json(self) -> None:
        # A bare JSON array/string/number/null is valid JSON but not a
        # provider-contract match; data.get("resultList") on a non-dict would
        # otherwise raise AttributeError instead of AdapterParseError.
        for bad in (b"[1, 2, 3]", b'"just a string"', b"42", b"null", b"true"):
            with self.subTest(payload=bad):
                with self.assertRaises(AdapterParseError):
                    europe_pmc.parse(bad)

    def test_parse_raises_when_resultlist_missing(self) -> None:
        payload = json.dumps({"hitCount": 0}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            europe_pmc.parse(payload)

    def test_parse_raises_when_resultlist_is_not_an_object(self) -> None:
        payload = json.dumps({"hitCount": 0, "resultList": []}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            europe_pmc.parse(payload)

    def test_parse_raises_when_result_is_not_a_list(self) -> None:
        payload = json.dumps({"hitCount": 0, "resultList": {"result": {}}}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            europe_pmc.parse(payload)

    def test_parse_handles_empty_result_list(self) -> None:
        payload = json.dumps({"hitCount": 0, "resultList": {"result": []}}).encode("utf-8")
        result = europe_pmc.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertEqual(result.usage, {"total_results": 0, "returned": 0})

    def test_citation_url_prefers_doi_over_source_id_fallback(self) -> None:
        payload = json.dumps(
            {
                "hitCount": 1,
                "resultList": {
                    "result": [
                        {
                            "id": "123",
                            "source": "MED",
                            "doi": "10.1/x",
                            "title": "T",
                            "authorString": "A B.",
                            "pubYear": "2020",
                        }
                    ]
                },
            }
        ).encode("utf-8")
        result = europe_pmc.parse(payload)
        self.assertEqual(result.citations[0]["url"], "https://doi.org/10.1/x")

    def test_citation_url_falls_back_to_source_and_id_when_doi_missing(self) -> None:
        # doi is absent (not just null) on a real minority of records --
        # matches the shape of two entries in europe_pmc_success.json.
        payload = json.dumps(
            {
                "hitCount": 1,
                "resultList": {
                    "result": [{"id": "PMC999", "source": "PMC", "title": "T", "pubYear": "2020"}]
                },
            }
        ).encode("utf-8")
        result = europe_pmc.parse(payload)
        self.assertEqual(result.citations[0]["url"], "https://europepmc.org/abstract/PMC/PMC999")

    def test_result_with_no_doi_and_no_source_or_id_is_listed_but_not_a_citation(self) -> None:
        payload = json.dumps(
            {"hitCount": 1, "resultList": {"result": [{"title": "Orphan record"}]}}
        ).encode("utf-8")
        result = europe_pmc.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertIn("Orphan record", result.synthesis_text)

    def test_parse_handles_results_with_missing_optional_fields(self) -> None:
        payload = json.dumps(
            {
                "hitCount": 1,
                "resultList": {
                    "result": [
                        {
                            "id": "1",
                            "source": "MED",
                            "title": None,
                            "authorString": None,
                            "pubYear": None,
                        }
                    ]
                },
            }
        ).encode("utf-8")
        result = europe_pmc.parse(payload)
        self.assertEqual(result.kind, "paper_listing")
        self.assertIn("(untitled)", result.synthesis_text)
        self.assertIsNone(result.citations[0]["date"])

    def test_parse_skips_non_dict_entries_in_result(self) -> None:
        payload = json.dumps({"hitCount": 1, "resultList": {"result": [None, "x", 1]}}).encode(
            "utf-8"
        )
        result = europe_pmc.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertEqual(result.usage["returned"], 3)

    def test_parse_handles_missing_hit_count(self) -> None:
        payload = json.dumps({"resultList": {"result": []}}).encode("utf-8")
        result = europe_pmc.parse(payload)
        self.assertEqual(result.usage, {"total_results": None, "returned": 0})

    def test_every_citation_is_url_title_date_shaped_against_fixture(self) -> None:
        fixture = json.loads((FIXTURES / "europe_pmc_success.json").read_text())
        result = europe_pmc.parse((FIXTURES / "europe_pmc_success.json").read_bytes())
        self.assertEqual(len(result.citations), len(fixture["resultList"]["result"]))
        for citation in result.citations:
            self.assertEqual(set(citation), {"url", "title", "date"})


class EuropePmcAdapterTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_boundary.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = enabled_registry_copy("europe-pmc")
        contract = confirmed_demo_contract(
            route="europe-pmc", request_count=1, probe_ceiling=2, registry=self.registry
        )
        # europe-pmc requires no credential, so environ stays empty -- no
        # os.environ patching needed the way sonar's/openalex's tests patch
        # in a key.
        state = new_state(contract, NOW, registry=self.registry, environ={})
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "europe-pmc", 1, "fp-test", NOW
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
        # response (live europe-pmc call 2026-07-11, query "CRISPR gene
        # editing efficacy") and may be re-recorded later.
        fixture = json.loads((FIXTURES / "europe_pmc_success.json").read_text())
        results = fixture["resultList"]["result"]
        expected_total = fixture["hitCount"]

        result = execute_probe(
            self.session, "A1", "CRISPR gene editing efficacy", NOW,
            transport=fixture_transport("europe_pmc_success.json"), environ={},
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "europe-pmc")
        self.assertEqual(occurrence["kind"], "paper_listing")
        self.assertEqual(occurrence["model"], "europepmc/rest-search")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], len(results))
        self.assertTrue(occurrence["synthesis_excerpt"].strip())
        self.assertIn(results[0]["title"], occurrence["synthesis_excerpt"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        spooled = json.loads(spool.read_text())
        self.assertEqual(spooled["hitCount"], expected_total)
        self.assertEqual(len(spooled["resultList"]["result"]), len(results))

        # Every citation is url/title/date-shaped, one per resolvable result.
        self.assertEqual(len(occurrence["citations"]), len(results))
        for citation in occurrence["citations"]:
            self.assertEqual(set(citation), {"url", "title", "date"})

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_error_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("europe_pmc_error_body.json", status=429),
                environ={},
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("Too Many Requests", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "europe-pmc", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("europe_pmc_missing_resultlist.json"), environ={},
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
        execute_probe(
            self.session, "A1", "q", NOW,
            transport=fixture_transport("europe_pmc_success.json"), environ={},
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "q", NOW,
                transport=fixture_transport("europe_pmc_success.json"), environ={},
            )

    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "missing", "q", NOW,
                transport=fixture_transport("europe_pmc_success.json"), environ={},
            )


if __name__ == "__main__":
    unittest.main()
