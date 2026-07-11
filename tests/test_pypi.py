from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_harness.adapters import pypi
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")

# pypi is fully keyless (no optional token, unlike github's GITHUB_TOKEN), so
# every session in this suite runs with an empty environ.
TEST_ENV: dict[str, str] = {}


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


class PypiAdapterUnitTests(unittest.TestCase):
    """Pure build()/parse() tests: no network, no session machinery."""

    def test_build_is_a_true_get_with_expected_headers(self) -> None:
        spec = pypi.build("requests", {})
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.url, "https://pypi.org/pypi/requests/json")
        self.assertEqual(spec.body, b"")
        self.assertEqual(spec.timeout_s, 30.0)
        self.assertEqual(spec.headers, {"Accept": "application/json", "User-Agent": "research-harness-v2"})

    def test_build_rejects_invalid_package_names(self) -> None:
        for bad_query in (
            "",
            ".",
            "-",
            "-leading-hyphen",
            "trailing-hyphen-",
            ".leading-dot",
            "trailing-dot.",
            "has space",
            "has/slash",
            "semi;colon",
        ):
            with self.assertRaises(BoundaryError, msg=f"expected rejection for {bad_query!r}"):
                pypi.build(bad_query, {})

    def test_build_accepts_dotted_hyphenated_underscored_and_single_character_names(self) -> None:
        for good_query in ("a", "A", "0", "zope.interface", "typing-extensions", "some_package_name"):
            spec = pypi.build(good_query, {})
            self.assertEqual(spec.url, f"https://pypi.org/pypi/{good_query}/json")

    def test_parse_raises_on_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            pypi.parse(b"not json at all")

    def test_parse_raises_when_info_object_missing(self) -> None:
        payload = json.dumps({"releases": {}}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            pypi.parse(payload)

    def test_parse_raises_when_name_missing(self) -> None:
        payload = json.dumps({"info": {"version": "1.0.0"}, "releases": {}}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            pypi.parse(payload)

    def test_parse_raises_when_version_missing(self) -> None:
        payload = json.dumps({"info": {"name": "some-package"}, "releases": {}}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            pypi.parse(payload)


class PypiBoundaryTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_github.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = enabled_registry_copy("pypi")
        contract = confirmed_demo_contract(
            route="pypi", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(
            "pypi adapter boundary test", contract, NOW,
            registry=self.registry, environ=TEST_ENV,
        )
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "pypi", 1, "fp-test", NOW
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
        # response (live pypi.org call 2026-07-11 against the "requests"
        # package) and may be re-recorded later.
        fixture = json.loads((FIXTURES / "pypi_success.json").read_text())
        info = fixture["info"]
        expected_name = info["name"]
        expected_version = info["version"]
        expected_release_count = len(fixture.get("releases") or {})
        expected_lines = [
            f"name: {expected_name}",
            f"version: {expected_version}",
            f"summary: {info.get('summary') or ''}",
            f"license: {info.get('license') or ''}",
            f"requires_python: {info.get('requires_python') or ''}",
            f"release_count: {expected_release_count}",
        ]
        expected_synthesis = "\n".join(expected_lines)
        expected_url = info.get("package_url") or f"https://pypi.org/project/{expected_name}/"

        result = execute_probe(
            self.session, "A1", "requests", NOW,
            transport=fixture_transport("pypi_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "pypi")
        self.assertEqual(occurrence["kind"], "record_fetch")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], 1)
        self.assertEqual(
            occurrence["citations"],
            [{"url": expected_url, "title": f"{expected_name} {expected_version}", "date": None}],
        )
        self.assertEqual(occurrence["synthesis_excerpt"], expected_synthesis)
        self.assertFalse(occurrence["synthesis_truncated"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(json.loads(spool.read_text())["info"]["name"], expected_name)

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_404_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "this-package-does-not-exist-zzz", NOW,
                transport=fixture_transport("pypi_not_found.json", status=404),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("Not Found", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "pypi", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "requests", NOW,
                transport=fixture_transport("pypi_malformed_missing_name.json"),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool" / "A1.raw.json").exists())

    def test_invalid_query_rejected_before_any_attempt(self) -> None:
        # build() validates the package-name shape before the boundary
        # records any attempt, so a malformed query never burns the permit's
        # attempt-status lifecycle (unlike a transport/HTTP failure).
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "-not a valid name-", NOW,
                transport=fixture_transport("pypi_success.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), [])

    def test_second_execution_of_same_action_is_refused(self) -> None:
        execute_probe(
            self.session, "A1", "requests", NOW,
            transport=fixture_transport("pypi_success.json"), environ=TEST_ENV,
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "requests", NOW,
                transport=fixture_transport("pypi_success.json"), environ=TEST_ENV,
            )


if __name__ == "__main__":
    unittest.main()
