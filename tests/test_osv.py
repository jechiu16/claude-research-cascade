from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_harness.adapters import osv
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import permit_usage
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")

# api.osv.dev is fully keyless (no optional token at all, unlike github's
# optional GITHUB_TOKEN), so every session in this suite runs with an empty
# environ.
TEST_ENV: dict[str, str] = {}


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def _expected_citation(vuln: dict) -> dict:
    summary = vuln.get("summary")
    return {
        "url": f"https://osv.dev/vulnerability/{vuln['id']}",
        "title": f"{vuln['id']}: {summary}" if summary else vuln["id"],
        "date": vuln.get("modified"),
    }


def _expected_line(vuln: dict) -> str:
    summary = vuln.get("summary")
    excerpt = summary[:120] if summary else ""
    parts = [vuln["id"]]
    if excerpt:
        parts.append(excerpt)
    parts.append(f"modified {vuln.get('modified')}")
    return " — ".join(parts)


class OsvAdapterUnitTests(unittest.TestCase):
    """Pure build()/parse() tests: no network, no session machinery."""

    def test_build_is_a_post_with_expected_headers_and_body(self) -> None:
        spec = osv.build("PyPI/requests", {})
        self.assertEqual(spec.method, "POST")
        self.assertEqual(spec.url, "https://api.osv.dev/v1/query")
        self.assertEqual(
            spec.headers,
            {"Content-Type": "application/json", "User-Agent": "research-harness-v2"},
        )
        self.assertEqual(
            json.loads(spec.body), {"package": {"ecosystem": "PyPI", "name": "requests"}}
        )
        self.assertEqual(spec.timeout_s, 30.0)

    def test_build_ignores_env_because_the_route_is_keyless(self) -> None:
        # osv is keyless: unlike github's optional GITHUB_TOKEN, no header is
        # ever added for any env content, and an unrelated/empty env must
        # not raise.
        spec = osv.build("PyPI/requests", {"SOME_OTHER_KEY": "x"})
        self.assertNotIn("Authorization", spec.headers)
        self.assertEqual(len(spec.headers), 2)

    def test_build_splits_on_first_slash_only(self) -> None:
        # A scoped npm package name legitimately contains its own slash;
        # only the FIRST slash divides ecosystem from package name, so the
        # rest of the string (including embedded slashes) is the name.
        spec = osv.build("npm/@angular/core", {})
        self.assertEqual(
            json.loads(spec.body), {"package": {"ecosystem": "npm", "name": "@angular/core"}}
        )

    def test_build_rejects_malformed_queries(self) -> None:
        for bad_query in ("", "noslash", "PyPI/", "/requests", "/"):
            with self.assertRaises(BoundaryError, msg=f"expected rejection for {bad_query!r}"):
                osv.build(bad_query, {})

    def test_parse_raises_on_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            osv.parse(b"not json at all")

    def test_parse_raises_on_non_dict_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            osv.parse(b"[1, 2, 3]")

    def test_parse_raises_when_vulns_is_not_a_list(self) -> None:
        with self.assertRaises(AdapterParseError):
            osv.parse((FIXTURES / "osv_malformed_vulns_not_list.json").read_bytes())

    def test_parse_treats_empty_object_as_valid_no_vulns_result(self) -> None:
        # {} is OSV's own shape for "no known vulnerabilities" for a
        # package — a complete, valid result, not a parse error.
        parsed = osv.parse((FIXTURES / "osv_empty.json").read_bytes())
        self.assertEqual(parsed.kind, "record_fetch")
        self.assertEqual(parsed.citations, [])
        self.assertEqual(parsed.usage, {"vuln_count": 0})
        self.assertEqual(parsed.synthesis_text, "no known vulnerabilities recorded")


class OsvBoundaryTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_pypi.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = enabled_registry_copy("osv")
        contract = confirmed_demo_contract(
            route="osv", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(contract, NOW, registry=self.registry, environ=TEST_ENV)
        create_session(self.session, state)

    def attempt_statuses(self, action_id: str = "A1") -> list[str]:
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        return [
            event.get("initial_status")
            for event in events
            if event.get("event") == "permit_acquired"
            and event.get("action_id") == action_id
            and event.get("initial_status")
        ] + [
            event["status"]
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == action_id
        ]

    def test_success_records_occurrence_with_expectations_from_fixture(self) -> None:
        # Expectations come from the fixture itself: it is a recorded real
        # response (live osv.dev call 2026-07-11 against "PyPI/requests")
        # and may be re-recorded later. The 15 real vulns straddle both
        # branches of the summary-optional field (8 carry a summary, 7 of
        # the PYSEC-sourced entries do not), so this fixture alone exercises
        # both citation-title shapes honestly.
        fixture = json.loads((FIXTURES / "osv_success.json").read_text())
        vulns = fixture["vulns"]
        expected_citations = [_expected_citation(v) for v in vulns]
        expected_synthesis = "\n".join(_expected_line(v) for v in vulns)

        result = execute_probe(
            self.session, "A1", 'primary_scout', 'osv', "PyPI/requests", NOW,
            transport=fixture_transport("osv_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "osv")
        self.assertEqual(occurrence["kind"], "record_fetch")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], len(vulns))
        self.assertEqual(occurrence["citations"], expected_citations)
        self.assertEqual(occurrence["synthesis_excerpt"], expected_synthesis)
        self.assertFalse(occurrence["synthesis_truncated"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(len(json.loads(spool.read_text())["vulns"]), len(vulns))

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_empty_result_records_completed_occurrence_with_zero_citations(self) -> None:
        # Expectations come from the fixture itself: it is a recorded real
        # response (live osv.dev call 2026-07-11 against "PyPI/cowsay", a
        # real published package with no known vulnerabilities). OSV's own
        # {} shape for "nothing found" is a VALID complete result, not an
        # error — the attempt must still reach "completed", not "failed".
        result = execute_probe(
            self.session, "A1", 'primary_scout', 'osv', "PyPI/cowsay", NOW,
            transport=fixture_transport("osv_empty.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "osv")
        self.assertEqual(occurrence["kind"], "record_fetch")
        self.assertEqual(occurrence["citation_count"], 0)
        self.assertEqual(occurrence["citations"], [])
        self.assertEqual(occurrence["synthesis_excerpt"], "no known vulnerabilities recorded")
        self.assertFalse(occurrence["synthesis_truncated"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_error_consumes_permit_and_preserves_payload(self) -> None:
        # Real recorded 400 body (live osv.dev call 2026-07-11, an
        # intentionally invalid ecosystem name) — a well-formed provider
        # error, not a malformed/parse-failure payload.
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", 'primary_scout', 'osv', "PyPI/requests", NOW,
                transport=fixture_transport("osv_invalid_ecosystem.json", status=400),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("Invalid ecosystem", spool.read_text())
        # The boundary request count stays consumed after the failed call.
        self.assertEqual(permit_usage(self.session)["probe"], 1)

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", 'primary_scout', 'osv', "PyPI/requests", NOW,
                transport=fixture_transport("osv_malformed_vulns_not_list.json"),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool" / "A1.raw.json").exists())

    def test_invalid_query_rejected_before_any_attempt(self) -> None:
        # build() validates the "<ecosystem>/<package>" shape before the
        # boundary records any attempt, so a malformed query never burns
        # the permit's attempt-status lifecycle (unlike a transport/HTTP
        # failure).
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", 'primary_scout', 'osv', "this-has-no-slash", NOW,
                transport=fixture_transport("osv_success.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), [])

    def test_second_execution_of_same_action_is_refused(self) -> None:
        execute_probe(
            self.session, "A1", 'primary_scout', 'osv', "PyPI/requests", NOW,
            transport=fixture_transport("osv_success.json"), environ=TEST_ENV,
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", 'primary_scout', 'osv', "PyPI/requests", NOW,
                transport=fixture_transport("osv_success.json"), environ=TEST_ENV,
            )


if __name__ == "__main__":
    unittest.main()


class OsvIdlessVulnTests(unittest.TestCase):
    def test_vuln_without_id_yields_no_fabricated_citation(self) -> None:
        import json as _json

        from research_harness.adapters import osv as osv_adapter

        payload = _json.dumps(
            {"vulns": [{"summary": "record with no id", "modified": "2026-01-01"}]}
        ).encode("utf-8")
        result = osv_adapter.parse(payload)
        self.assertEqual(result.citations, [])
        self.assertNotIn("None", " ".join(c.get("url", "") for c in result.citations))
