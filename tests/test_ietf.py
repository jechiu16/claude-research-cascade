from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_harness.adapters import ietf
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")

# ietf is fully keyless (no optional token, same posture as pypi), so every
# session in this suite runs with an empty environ.
TEST_ENV: dict[str, str] = {}


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


class IetfAdapterUnitTests(unittest.TestCase):
    """Pure build()/parse() tests: no network, no session machinery."""

    def test_build_is_a_true_get_with_expected_headers(self) -> None:
        spec = ietf.build("9110", {})
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.url, "https://www.rfc-editor.org/rfc/rfc9110.json")
        self.assertEqual(spec.body, b"")
        self.assertEqual(spec.timeout_s, 30.0)
        self.assertEqual(spec.headers, {"Accept": "application/json", "User-Agent": "research-harness-v2"})

    def test_build_accepts_rfc_prefix_case_insensitively(self) -> None:
        for query in ("9110", "rfc9110", "RFC9110", "Rfc9110", "rFC9110"):
            with self.subTest(query=query):
                spec = ietf.build(query, {})
                self.assertEqual(spec.url, "https://www.rfc-editor.org/rfc/rfc9110.json")

    def test_build_normalizes_numeric_query_to_int(self) -> None:
        # "normalize to number": a shorter zero-padded digit run still maps
        # to the same canonical rfc<n>.json URL.
        spec = ietf.build("rfc09110", {})
        self.assertEqual(spec.url, "https://www.rfc-editor.org/rfc/rfc9110.json")

    def test_build_rejects_malformed_queries(self) -> None:
        for bad_query in (
            "",
            "rfc",
            "abc",
            "123456",  # 6 digits, over the 5-digit cap
            "91 10",
            "-9110",
            "9110.5",
            "rfc-9110",
            "rfc 9110",
            "rfc9110x",
            "9110/",
        ):
            with self.assertRaises(BoundaryError, msg=f"expected rejection for {bad_query!r}"):
                ietf.build(bad_query, {})

    def test_parse_raises_on_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            ietf.parse(b"not json at all")

    def test_parse_raises_when_doc_id_missing(self) -> None:
        payload = json.dumps({"title": "HTTP Semantics"}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            ietf.parse(payload)

    def test_parse_raises_when_title_missing(self) -> None:
        payload = json.dumps({"doc_id": "RFC9110"}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            ietf.parse(payload)

    def test_parse_tolerates_non_list_authors_obsoletes_fields(self) -> None:
        # doc_id/title are the only load-bearing fields; a payload where
        # authors/obsoletes/obsoleted_by are present but malformed as a
        # non-list must degrade to empty rather than crash (iterating a bare
        # string char-by-char) or raise an uncaught TypeError.
        payload = json.dumps(
            {
                "doc_id": "RFC9110",
                "title": "HTTP Semantics",
                "authors": "not-a-list",
                "obsoletes": {"unexpected": "shape"},
                "obsoleted_by": None,
            }
        ).encode("utf-8")
        result = ietf.parse(payload)
        lines = dict(line.split(": ", 1) for line in result.synthesis_text.splitlines())
        self.assertEqual(lines["authors"], "")
        self.assertEqual(lines["obsoletes"], "")
        self.assertEqual(lines["obsoleted_by"], "")


class IetfBoundaryTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_pypi.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = enabled_registry_copy("ietf")
        contract = confirmed_demo_contract(
            route="ietf", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(contract, NOW, registry=self.registry, environ=TEST_ENV)
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "ietf", 1, "fp-test", NOW
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
        # response (live rfc-editor.org call 2026-07-11 against RFC 9110)
        # and may be re-recorded later.
        fixture = json.loads((FIXTURES / "ietf_success.json").read_text())
        doc_id = fixture["doc_id"]
        title = fixture["title"]
        expected_lines = [
            f"doc_id: {doc_id}",
            f"title: {title}",
            f"status: {fixture.get('status') or ''}",
            f"pub_date: {fixture.get('pub_date') or ''}",
            f"authors: {', '.join(fixture.get('authors') or [])}",
            f"obsoletes: {', '.join(fixture.get('obsoletes') or [])}",
            f"obsoleted_by: {', '.join(fixture.get('obsoleted_by') or [])}",
        ]
        if fixture.get("abstract"):
            expected_lines.append(f"abstract: {fixture['abstract']}")
        expected_synthesis = "\n".join(expected_lines)
        expected_url = f"https://www.rfc-editor.org/rfc/{doc_id.lower()}"

        result = execute_probe(
            self.session, "A1", "9110", NOW,
            transport=fixture_transport("ietf_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "ietf")
        self.assertEqual(occurrence["kind"], "record_fetch")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], 1)
        self.assertEqual(
            occurrence["citations"],
            [{"url": expected_url, "title": f"{doc_id}: {title}", "date": fixture.get("pub_date")}],
        )
        self.assertEqual(occurrence["synthesis_excerpt"], expected_synthesis)
        self.assertFalse(occurrence["synthesis_truncated"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(json.loads(spool.read_text())["doc_id"], doc_id)

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_404_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "99999", NOW,
                transport=fixture_transport("ietf_not_found.json", status=404),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("Not found", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "ietf", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "9110", NOW,
                transport=fixture_transport("ietf_malformed_missing_doc_id.json"),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool" / "A1.raw.json").exists())

    def test_invalid_query_rejected_before_any_attempt(self) -> None:
        # build() validates the RFC-number shape before the boundary records
        # any attempt, so a malformed query never burns the permit's
        # attempt-status lifecycle (unlike a transport/HTTP failure).
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "not-an-rfc-number", NOW,
                transport=fixture_transport("ietf_success.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), [])

    def test_second_execution_of_same_action_is_refused(self) -> None:
        execute_probe(
            self.session, "A1", "9110", NOW,
            transport=fixture_transport("ietf_success.json"), environ=TEST_ENV,
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "9110", NOW,
                transport=fixture_transport("ietf_success.json"), environ=TEST_ENV,
            )


if __name__ == "__main__":
    unittest.main()
