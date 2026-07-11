from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from research_harness.adapters import github
from research_harness.boundary import AdapterParseError, BoundaryError, execute_probe
from research_harness.providers import load_provider_registry
from research_harness.quota import QuotaExceeded, acquire_permits
from research_harness.state import new_state
from research_harness.storage import create_session, load_state, read_events
from research_harness.validation import validate_session
from tests.helpers import NOW, confirmed_demo_contract

FIXTURES = Path(__file__).with_name("fixtures")

# github is keyless: GITHUB_TOKEN is optional (attached only if present), so
# every session in this suite runs with an empty environ.
TEST_ENV: dict[str, str] = {}


def _github_enabled_registry() -> dict:
    """The base registry ships github with enabled:false (candidate route;
    the orchestrator flips it after reviewing adoption evidence). new_state()
    snapshots the registry it is given, so tests that want to exercise the
    v2 boundary must pass an override registry with github enabled, threaded
    through both confirmed_demo_contract(registry=...) and new_state(registry=...)
    so their registry hashes agree — see tests/helpers.py for the pattern.

    Flipping "enabled" alone is not sufficient: validate_provider_registry()
    additionally requires a v2_request_boundary route to carry a "baseline"
    or "validated" adoption_status plus non-empty adoption_evidence once it
    is enabled (see providers.py "enabled external route ... lacks adoption
    evidence"). This helper sets both on the in-memory test copy only; the
    committed registry record is untouched and stays enabled:false with
    adoption_status "not_tested" until the orchestrator reviews this suite
    plus the live e2e run and flips it for real.
    """

    registry = copy.deepcopy(load_provider_registry())
    for provider in registry["providers"]:
        if provider["id"] == "github":
            provider["enabled"] = True
            provider["adoption_status"] = "baseline"
            provider["adoption_evidence"] = ["fixture-replay-suite-tests-test_github"]
    return registry


def fixture_transport(name: str, status: int = 200):
    payload = (FIXTURES / name).read_bytes()

    def transport(spec):
        return status, payload

    return transport


class GithubAdapterUnitTests(unittest.TestCase):
    """Pure build()/parse() tests: no network, no session machinery."""

    def test_build_is_a_true_get_with_no_credential_required(self) -> None:
        spec = github.build("jechiu16/agent-deep-research-trigger", {})
        self.assertEqual(spec.method, "GET")
        self.assertEqual(spec.url, "https://api.github.com/repos/jechiu16/agent-deep-research-trigger")
        self.assertEqual(spec.body, b"")
        self.assertNotIn("Authorization", spec.headers)
        self.assertEqual(spec.headers["Accept"], "application/vnd.github+json")
        self.assertEqual(spec.headers["X-GitHub-Api-Version"], "2022-11-28")
        self.assertEqual(spec.headers["User-Agent"], "research-harness-v2")

    def test_build_attaches_bearer_token_when_present(self) -> None:
        spec = github.build("jechiu16/agent-deep-research-trigger", {"GITHUB_TOKEN": "s3cr3t"})
        self.assertEqual(spec.headers["Authorization"], "Bearer s3cr3t")
        # The credential must never leak into the URL or fingerprint surface.
        self.assertNotIn("s3cr3t", spec.url)

    def test_build_rejects_malformed_owner_repo_queries(self) -> None:
        for bad_query in (
            "",
            "no-slash-here",
            "owner/",
            "/repo",
            "owner/repo/extra",
            "owner repo/x",
            "owner/repo with space",
            "a/b/c",
        ):
            with self.assertRaises(BoundaryError, msg=f"expected rejection for {bad_query!r}"):
                github.build(bad_query, {})

    def test_build_accepts_dotted_and_hyphenated_names(self) -> None:
        spec = github.build("some-org.io/repo_name.js", {})
        self.assertEqual(spec.url, "https://api.github.com/repos/some-org.io/repo_name.js")

    def test_parse_raises_on_non_json_payload(self) -> None:
        with self.assertRaises(AdapterParseError):
            github.parse(b"not json at all")

    def test_parse_raises_when_full_name_missing(self) -> None:
        payload = json.dumps({"html_url": "https://github.com/a/b"}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            github.parse(payload)

    def test_parse_raises_when_html_url_missing(self) -> None:
        payload = json.dumps({"full_name": "a/b"}).encode("utf-8")
        with self.assertRaises(AdapterParseError):
            github.parse(payload)


class GithubBoundaryTests(unittest.TestCase):
    """execute_probe()-level tests through the real v2 boundary, matching the
    golden pattern in tests/test_boundary.py."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.session = Path(self._tempdir.name) / "session"
        self.registry = _github_enabled_registry()
        contract = confirmed_demo_contract(
            route="github", request_count=1, probe_ceiling=2, registry=self.registry
        )
        state = new_state(
            "github adapter boundary test", contract, NOW,
            registry=self.registry, environ=TEST_ENV,
        )
        create_session(self.session, state)
        acquire_permits(
            self.session, "A1", "primary_scout", "probe", "github", 1, "fp-test", NOW
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
        # GitHub response and may be re-recorded after repository metadata
        # changes.
        fixture = json.loads((FIXTURES / "github_success.json").read_text())
        expected_full_name = fixture["full_name"]
        expected_html_url = fixture["html_url"]
        expected_lines = [
            f"full_name: {fixture.get('full_name') or ''}",
            f"description: {fixture.get('description') or ''}",
            f"default_branch: {fixture.get('default_branch') or ''}",
            f"license.spdx_id: {(fixture.get('license') or {}).get('spdx_id') or ''}",
            f"stargazers_count: {fixture.get('stargazers_count')}",
            f"open_issues_count: {fixture.get('open_issues_count')}",
            f"archived: {fixture.get('archived')}",
            f"pushed_at: {fixture.get('pushed_at') or ''}",
        ]
        expected_synthesis = "\n".join(expected_lines)

        result = execute_probe(
            self.session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
            transport=fixture_transport("github_success.json"), environ=TEST_ENV,
        )
        occurrence = result["occurrence"]
        self.assertEqual(occurrence["provider_id"], "github")
        self.assertEqual(occurrence["kind"], "record_fetch")
        self.assertIsNone(occurrence["cost_usd"])
        self.assertEqual(occurrence["citation_count"], 1)
        self.assertEqual(
            occurrence["citations"],
            [{"url": expected_html_url, "title": expected_full_name, "date": fixture.get("pushed_at")}],
        )
        self.assertEqual(occurrence["synthesis_excerpt"], expected_synthesis)
        self.assertFalse(occurrence["synthesis_truncated"])
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "completed"])

        state = load_state(self.session)
        self.assertEqual(len(state["retrieval_occurrences"]), 1)
        spool = Path(result["spool_path"])
        self.assertTrue(spool.exists())
        self.assertEqual(json.loads(spool.read_text())["full_name"], expected_full_name)

        report = validate_session(self.session, check_report=False)
        self.assertEqual(report.errors, ())

    def test_http_404_consumes_permit_and_preserves_payload(self) -> None:
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "jechiu16/does-not-exist-zzz", NOW,
                transport=fixture_transport("github_not_found.json", status=404),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        spool = self.session / "provider_spool" / "A1.raw.json"
        self.assertIn("Not Found", spool.read_text())
        # The permit stays consumed: the single primary_scout invocation is gone.
        with self.assertRaises(QuotaExceeded):
            acquire_permits(
                self.session, "A2", "primary_scout", "probe", "github", 1, "fp2", NOW
            )

    def test_parse_failure_spools_raw_and_fails_attempt(self) -> None:
        with self.assertRaises(AdapterParseError):
            execute_probe(
                self.session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
                transport=fixture_transport("github_malformed_missing_full_name.json"),
                environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), ["attempted", "accepted", "failed"])
        self.assertTrue((self.session / "provider_spool" / "A1.raw.json").exists())

    def test_invalid_query_rejected_before_any_attempt(self) -> None:
        # build() validates "owner/repo" shape before the boundary records
        # any attempt, so a malformed query never burns the permit's
        # attempt-status lifecycle (unlike a transport/HTTP failure).
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "this-is-not-owner-slash-repo", NOW,
                transport=fixture_transport("github_success.json"), environ=TEST_ENV,
            )
        self.assertEqual(self.attempt_statuses(), [])

    def test_second_execution_of_same_action_is_refused(self) -> None:
        execute_probe(
            self.session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
            transport=fixture_transport("github_success.json"), environ=TEST_ENV,
        )
        with self.assertRaises(BoundaryError):
            execute_probe(
                self.session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
                transport=fixture_transport("github_success.json"), environ=TEST_ENV,
            )

    def test_succeeds_with_no_environment_at_all(self) -> None:
        # github is keyless: unlike sonar (PERPLEXITY_API_KEY required), an
        # empty environ must not block the route.
        result = execute_probe(
            self.session, "A1", "jechiu16/agent-deep-research-trigger", NOW,
            transport=fixture_transport("github_success.json"), environ={},
        )
        self.assertEqual(result["occurrence"]["provider_id"], "github")


if __name__ == "__main__":
    unittest.main()
