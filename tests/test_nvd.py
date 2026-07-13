from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_harness.adapters import nvd
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract, enabled_registry_copy

FIXTURES = Path(__file__).with_name("fixtures")

# nvd is keyless: NVD_API_KEY is optional (attached only as the apiKey
# header if present, never required), so every session in this suite runs
# with an empty environ.
TEST_ENV: dict[str, str] = {}


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


def status_transport(status: int, payload: bytes = b'{"message": "synthetic nvd error"}'):
    """Inline HTTP-error transport with no backing fixture file.

    The task's fixture list is exactly success + two synthetic parse-failure
    bodies (empty vulnerabilities, non-dict) — no dedicated 4xx/429 error-body
    fixture. That is deliberate: the boundary fails on a non-200 status
    before ever calling adapter parse() (see boundary.execute_probe), so the
    error-permit-consumption path below needs only a status code, not a
    provider-accurate error body. A dedicated fixture file would duplicate
    github_not_found.json/pypi_not_found.json's role without adding
    coverage.
    """

    def transport(spec):
        return status, payload

    return transport


class NvdAdapterUnitTests(unittest.TestCase):
    """Pure build()/parse() tests: no network, no session machinery."""

    def test_build_is_a_true_get_with_no_credential_required(self) -> None:
        spec = nvd.build("CVE-2021-44228", {})
        self.assertEqual(spec.method, "GET")
        self.assertEqual(
            spec.url,
            "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2021-44228",
        )
        self.assertEqual(spec.body, b"")
        self.assertEqual(spec.timeout_s, 30.0)
        self.assertNotIn("apiKey", spec.headers)
        self.assertEqual(spec.headers["User-Agent"], "research-harness-v2")

    def test_build_attaches_api_key_header_when_present(self) -> None:
        spec = nvd.build("CVE-2021-44228", {"NVD_API_KEY": "s3cr3t"})
        self.assertEqual(spec.headers["apiKey"], "s3cr3t")
        # The credential must never leak into the URL or fingerprint surface.
        self.assertNotIn("s3cr3t", spec.url)

    def test_build_uppercases_lowercase_or_mixed_case_ids(self) -> None:
        spec = nvd.build("cve-2021-44228", {})
        self.assertEqual(
            spec.url,
            "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2021-44228",
        )
        spec = nvd.build("Cve-2021-44228", {})
        self.assertTrue(spec.url.endswith("CVE-2021-44228"))

    def test_build_accepts_longer_sequence_numbers(self) -> None:
        # Some CVE ids carry more than 4 sequence digits (post-2016 volume).
        spec = nvd.build("CVE-2021-123456", {})
        self.assertTrue(spec.url.endswith("CVE-2021-123456"))

    def test_build_rejects_malformed_cve_ids(self) -> None:
        for bad_query in (
            "",
            "CVE-2021",
            "CVE-21-44228",
            "CVE-2021-123",
            "CVE-2021-44228x",
            " CVE-2021-44228",
            "CVE-2021-44228 ",
            "2021-44228",
            "CVE_2021_44228",
            "CVE-2021-",
            "CVE--44228",
            "NOT-A-CVE-ID",
        ):
            with self.assertRaises(BoundaryError, msg=f"expected rejection for {bad_query!r}"):
                nvd.build(bad_query, {})

    def test_parse_raises_on_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            nvd.parse(b"not json at all")

    def test_parse_raises_when_payload_is_not_a_json_object(self) -> None:
        payload = (FIXTURES / "nvd_non_dict.json").read_bytes()
        with self.assertRaises(AdapterParseError):
            nvd.parse(payload)

    def test_parse_raises_when_vulnerabilities_is_empty(self) -> None:
        payload = (FIXTURES / "nvd_empty_vulnerabilities.json").read_bytes()
        with self.assertRaises(AdapterParseError):
            nvd.parse(payload)

    def test_parse_raises_when_vulnerabilities_key_missing(self) -> None:
        payload = json.dumps({"totalResults": 0}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            nvd.parse(payload)

    def test_parse_raises_when_cve_id_absent(self) -> None:
        payload = json.dumps(
            {"vulnerabilities": [{"cve": {"vulnStatus": "Analyzed"}}]}
        ).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            nvd.parse(payload)

    def test_parse_extracts_total_results_into_usage(self) -> None:
        fixture = json.loads((FIXTURES / "nvd_success.json").read_text())
        result = nvd.parse((FIXTURES / "nvd_success.json").read_bytes())
        self.assertEqual(result.usage, {"total_results": fixture["totalResults"]})


class NvdBoundaryTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_github.py and tests/test_pypi.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = enabled_registry_copy("nvd")
        contract = confirmed_demo_contract(
            route="nvd", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(contract, NOW, registry=self.registry, environ=TEST_ENV)
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "nvd", 1, "fp-test", NOW
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
        # response (live NVD call 2026-07-11 for CVE-2021-44228) and may be
        # re-recorded later.
        fixture = json.loads((FIXTURES / "nvd_success.json").read_text())
        cve = fixture["vulnerabilities"][0]["cve"]
        expected_id = cve["id"]
        expected_description = next(
            item["value"] for item in cve["descriptions"] if item["lang"] == "en"
        )[:300]
        expected_base_score = cve["metrics"]["cvssMetricV31"][0]["cvssData"]["baseScore"]
        expected_lines = [
            f"id: {expected_id}",
            f"vulnStatus: {cve.get('vulnStatus') or ''}",
            f"published: {cve.get('published') or ''}",
            f"lastModified: {cve.get('lastModified') or ''}",
            f"baseScore: {expected_base_score}",
            f"description: {expected_description}",
        ]
        expected_synthesis = "\n".join(expected_lines)

        result = execute_probe(
            self.session, "A1", "cve-2021-44228", NOW,
            transport=fixture_transport("nvd_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "nvd")
        self.assertEqual(occurrence["kind"], "record_fetch")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], 1)
        self.assertEqual(
            occurrence["citations"],
            [
                {
                    "url": f"https://nvd.nist.gov/vuln/detail/{expected_id}",
                    "title": expected_id,
                    "date": cve.get("lastModified"),
                }
            ],
        )
        self.assertEqual(occurrence["synthesis_excerpt"], expected_synthesis)
        self.assertFalse(occurrence["synthesis_truncated"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(
            json.loads(spool.read_text())["vulnerabilities"][0]["cve"]["id"], expected_id
        )

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_invalid_query_rejected_before_any_attempt(self) -> None:
        # build() validates the CVE-id shape before the boundary records any
        # attempt, so a malformed query never burns the permit's
        # attempt-status lifecycle (unlike a transport/HTTP failure).
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "not-a-cve-id", NOW,
                transport=fixture_transport("nvd_success.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), [])

    def test_http_error_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "CVE-2021-44228", NOW,
                transport=status_transport(403), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("synthetic nvd error", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "nvd", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "CVE-2021-44228", NOW,
                transport=fixture_transport("nvd_empty_vulnerabilities.json"),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool" / "A1.raw.json").exists())

    def test_second_execution_of_same_action_is_refused(self) -> None:
        execute_probe(
            self.session, "A1", "CVE-2021-44228", NOW,
            transport=fixture_transport("nvd_success.json"), environ=TEST_ENV,
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "CVE-2021-44228", NOW,
                transport=fixture_transport("nvd_success.json"), environ=TEST_ENV,
            )

    def test_succeeds_with_no_environment_at_all(self) -> None:
        # nvd is keyless: NVD_API_KEY is optional, so an empty environ must
        # not block the route.
        result = execute_probe(
            self.session, "A1", "CVE-2021-44228", NOW,
            transport=fixture_transport("nvd_success.json"), environ={},
        )
        self.assertEqual(result["occurrence"]["provider_id"], "nvd")


if __name__ == "__main__":
    unittest.main()
