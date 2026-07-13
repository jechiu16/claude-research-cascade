from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from research_harness.artifacts import purge_raw_artifact
from research_harness.contracts import contract_card_sha256
from research_harness.operations import purge_artifact, recover_operation
from research_harness.providers import (
    load_provider_registry,
    provider_records_sha256,
    provider_registry_sha256,
    referenced_provider_records,
)
from research_harness.rendering import render_session_result
from research_harness.state import new_state, state_sha256
from research_harness.storage import apply_state_patch, create_session, load_state, read_events
from scripts import research_state
from tests.helpers import (
    NOW,
    confirmed_demo_contract,
    confirmed_medium_contract,
    draft_medium_contract,
    make_complete_pass_session,
    write_overlay,
)


LATER = "2026-07-10T12:01:00Z"


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.cli = self.repo / "scripts" / "research_state.py"
        self.session = self.root / "session"
        self.source = self.root / "source.txt"
        self.source.write_text("local bounded output\n", encoding="utf-8")
        self.contract = self._write_json(confirmed_medium_contract(), "contract.json")
        self.draft = self._write_json(draft_medium_contract(), "draft.json")

    def _write_json(self, value: object, name: str | None = None) -> Path:
        path = self.root / (name or f"data-{uuid.uuid4().hex}.json")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def run_cli(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(self.cli), *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
            env=os.environ.copy(),
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(f"CLI failed ({result.returncode}): {result.stderr}\n{result.stdout}")
        return result

    def _init_session(self) -> None:
        self.run_cli(
            "init",
            str(self.session),
            "--contract",
            str(self.contract),
            "--json",
        )

    def _acquire_local(self) -> None:
        self.run_cli(
            "permit",
            str(self.session),
            "--action-id",
            "L1",
            "--stage",
            "local_applicability",
            "--category",
            "local",
            "--route",
            "local",
            "--count",
            "1",
            "--fingerprint",
            "sha256:local",
            "--now",
            NOW,
            "--json",
        )

    def test_init_permit_validate_render_flow(self) -> None:
        self._init_session()
        self.run_cli(
            "permit",
            str(self.session),
            "--action-id",
            "A1",
            "--stage",
            "primary_scout",
            "--category",
            "host_retrieval",
            "--route",
            "host-web",
            "--count",
            "1",
            "--fingerprint",
            "sha256:test",
            "--now",
            NOW,
            "--json",
        )
        validated = self.run_cli("validate", str(self.session), "--json")
        rendered = self.run_cli("render", str(self.session), "--json")
        self.assertTrue(json.loads(validated.stdout)["ok"])
        self.assertTrue(Path(json.loads(rendered.stdout)["report_path"]).exists())

    def test_v2_example_init_smoke_creates_session_and_validates(self) -> None:
        session = self.root / "v2-example-session"
        example = self.repo / "examples" / "v2" / "medium-contract.json"
        initialized = self.run_cli(
            "init", str(session), "--contract", str(example), "--json", check=False
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.assertTrue((session / "state.json").exists())
        validated = self.run_cli("validate", str(session), "--json", check=False)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertTrue(json.loads(validated.stdout)["ok"])

    def _assert_deprecated_question_migration(self, question_args: list[str]) -> None:
        session = self.root / f"deprecated-question-{uuid.uuid4().hex}"
        result = self.run_cli(
            "init",
            str(session),
            "--question",
            *question_args,
            "--contract",
            str(self.contract),
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "init --question is deprecated; place the question in the prepare/confirmed contract",
            result.stderr,
        )
        self.assertFalse(session.exists())

    def test_init_deprecated_question_valued_same_rejects_without_session(self) -> None:
        self._assert_deprecated_question_migration(["Choose a cache"])

    def test_init_deprecated_question_valued_different_rejects_without_session(self) -> None:
        self._assert_deprecated_question_migration(["Question B"])

    def test_init_deprecated_question_empty_rejects_without_session(self) -> None:
        self._assert_deprecated_question_migration([""])

    def test_init_deprecated_question_bare_rejects_without_session(self) -> None:
        self._assert_deprecated_question_migration([])

    def test_prepare_rejects_missing_contract_axes(self) -> None:
        contract = draft_medium_contract()
        contract.pop("execution")
        contract.pop("durability")
        path = self._write_json(contract, "missing-axes.json")
        result = self.run_cli("prepare", "--contract", str(path), "--json", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("execution and durability axes are required", result.stderr + result.stdout)

    def test_validate_exit_matrix_and_render_for_tier_insufficient(self) -> None:
        deliverable = make_complete_pass_session(self.root)
        self.assertEqual(self.run_cli("validate", str(deliverable), "--json").returncode, 0)

        host_contract = confirmed_medium_contract()
        host_contract["execution"] = "host_native"
        host_contract["durability"] = "canonical_package"
        host_contract["confirmation"]["card_sha256"] = contract_card_sha256(host_contract)
        insufficient = self.root / "insufficient"
        create_session(insufficient, new_state(host_contract, NOW, None, {}))
        result = self.run_cli("validate", str(insufficient), "--json", check=False)
        self.assertEqual(result.returncode, 2)
        rendered = self.run_cli("render", str(insufficient), "--json")
        self.assertTrue(Path(json.loads(rendered.stdout)["report_path"]).exists())

        invalid = make_complete_pass_session(self.root)
        state = load_state(invalid)
        apply_state_patch(
            invalid,
            [{"op": "replace", "path": "/claims/0/status", "value": "unverified"}],
            state["session"]["revision"],
            NOW,
        )
        self.assertEqual(self.run_cli("validate", str(invalid), "--json", check=False).returncode, 1)

    def test_attempt_records_status_transitions_for_organizer_action(self) -> None:
        self._init_session()
        self.run_cli(
            "permit",
            str(self.session),
            "--action-id",
            "O1",
            "--stage",
            "final_inference_review",
            "--category",
            "organizer_pass",
            "--route",
            "host",
            "--count",
            "1",
            "--fingerprint",
            "sha256:verifier",
            "--now",
            NOW,
            "--json",
        )
        for status in ("attempted", "accepted", "completed"):
            result = self.run_cli(
                "attempt",
                str(self.session),
                "--action-id",
                "O1",
                "--status",
                status,
                "--now",
                NOW,
                "--json",
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["action_id"], "O1")
            self.assertEqual(payload["status"], status)
            self.assertTrue(payload["event_hash"])
        events, errors = read_events(self.session)
        self.assertEqual(errors, [])
        transitions = [
            (event["from_status"], event["status"])
            for event in events
            if event.get("event") == "attempt_status" and event.get("action_id") == "O1"
        ]
        self.assertEqual(
            transitions,
            [("acquired", "attempted"), ("attempted", "accepted"), ("accepted", "completed")],
        )

    def test_attempt_rejects_invalid_transition(self) -> None:
        self._init_session()
        self._acquire_local()
        result = self.run_cli(
            "attempt",
            str(self.session),
            "--action-id",
            "L1",
            "--status",
            "completed",
            "--now",
            NOW,
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot transition action L1 from acquired to completed", result.stderr)

    def test_attempt_refuses_boundary_managed_categories(self) -> None:
        # Journaling "attempted" on a probe permit would permanently void it:
        # the boundary's _permit_for refuses any already-attempted action.
        # The medium contract has no probe mapping, so this uses a demo
        # contract in its own session.
        probe_session = self.root / "probe-session"
        probe_contract = self._write_json(confirmed_demo_contract(), "probe-contract.json")
        self.run_cli(
            "init",
            str(probe_session),
            "--contract",
            str(probe_contract),
            "--json",
        )
        self.run_cli(
            "permit",
            str(probe_session),
            "--action-id",
            "P1",
            "--stage",
            "primary_scout",
            "--category",
            "probe",
            "--route",
            "demo-probe",
            "--count",
            "1",
            "--fingerprint",
            "sha256:probe",
            "--now",
            NOW,
            "--json",
        )
        result = self.run_cli(
            "attempt",
            str(probe_session),
            "--action-id",
            "P1",
            "--status",
            "attempted",
            "--now",
            NOW,
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("boundary-managed", result.stderr)
        events, errors = read_events(probe_session)
        self.assertEqual(errors, [])
        self.assertEqual(
            [
                event
                for event in events
                if event.get("event") == "attempt_status" and event.get("action_id") == "P1"
            ],
            [],
        )

    def test_prepare_then_explicit_confirm_binds_exact_card_and_registry(self) -> None:
        prepared_result = self.run_cli("prepare", "--contract", str(self.draft), "--json")
        prepared_payload = json.loads(prepared_result.stdout)
        self.assertIsNone(prepared_payload["contract"]["confirmation"]["confirmed_at"])
        prepared_path = self._write_json(prepared_payload, "prepared.json")
        confirmed = self.run_cli(
            "confirm",
            "--prepared",
            str(prepared_path),
            "--card-sha256",
            prepared_payload["binding"]["card_sha256"],
            "--registry-sha256",
            prepared_payload["binding"]["registry_sha256"],
            "--referenced-records-sha256",
            prepared_payload["binding"]["referenced_records_sha256"],
            "--confirmed-at",
            NOW,
            "--confirmed-by",
            "user",
            "--json",
        )
        confirmed_payload = json.loads(confirmed.stdout)
        contract = confirmed_payload["contract"]
        self.assertEqual(
            contract["confirmation"]["registry_sha256"],
            prepared_payload["binding"]["registry_sha256"],
        )
        confirmed_path = self._write_json(confirmed_payload, "confirmed.json")
        self.run_cli(
            "init",
            str(self.session),
            "--contract",
            str(confirmed_path),
            "--json",
        )

    def test_init_rejects_confirmed_question_swap(self) -> None:
        swapped = copy.deepcopy(json.loads(self.contract.read_text(encoding="utf-8")))
        swapped["question"] = "Question B"
        swapped_path = self._write_json(swapped, "swapped.json")
        result = self.run_cli(
            "init", str(self.session), "--contract", str(swapped_path), "--json", check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("confirmed card hash does not match contract", result.stderr)

    def test_confirm_rejects_card_hash_not_shown_to_user(self) -> None:
        prepared = json.loads(
            self.run_cli("prepare", "--contract", str(self.draft), "--json").stdout
        )
        result = self.run_cli(
            "confirm",
            "--prepared",
            str(self._write_json(prepared, "prepared-bad-hash.json")),
            "--card-sha256",
            "0" * 64,
            "--registry-sha256",
            prepared["binding"]["registry_sha256"],
            "--referenced-records-sha256",
            prepared["binding"]["referenced_records_sha256"],
            "--confirmed-at",
            NOW,
            "--confirmed-by",
            "user",
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("card hash does not match prepared contract", result.stderr)

    def test_confirm_rejects_contract_mutated_after_prepare(self) -> None:
        prepared = json.loads(
            self.run_cli("prepare", "--contract", str(self.draft), "--json").stdout
        )
        shown_hash = prepared["binding"]["card_sha256"]
        prepared["contract"]["resource_envelope"]["physical_ceiling"]["host_retrieval"] = 99
        result = self.run_cli(
            "confirm",
            "--prepared",
            str(self._write_json(prepared, "prepared-mutated.json")),
            "--card-sha256",
            shown_hash,
            "--registry-sha256",
            prepared["binding"]["registry_sha256"],
            "--referenced-records-sha256",
            prepared["binding"]["referenced_records_sha256"],
            "--confirmed-at",
            NOW,
            "--confirmed-by",
            "user",
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prepared contract bytes changed", result.stderr)

    def test_confirm_rejects_registry_hash_not_shown_to_user(self) -> None:
        prepared = json.loads(
            self.run_cli("prepare", "--contract", str(self.draft), "--json").stdout
        )
        result = self.run_cli(
            "confirm",
            "--prepared",
            str(self._write_json(prepared, "prepared-bad-registry.json")),
            "--card-sha256",
            prepared["binding"]["card_sha256"],
            "--registry-sha256",
            "0" * 64,
            "--referenced-records-sha256",
            prepared["binding"]["referenced_records_sha256"],
            "--confirmed-at",
            NOW,
            "--confirmed-by",
            "user",
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("registry hash does not match prepared registry", result.stderr)

    def test_cli_refuses_unconfirmed_contract(self) -> None:
        result = self.run_cli(
            "init",
            str(self.session),
            "--contract",
            str(self.draft),
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contract is not user-confirmed", result.stderr)

    def test_json_runtime_error_envelope_lands_on_stdout(self) -> None:
        # main()'s except-Exception path used to print only to stderr and
        # leave stdout EMPTY even with --json -- a --json caller had no
        # single-stream contract to parse on failure. Now stdout also carries
        # a {"error", "command"} envelope, on top of the unchanged stderr line.
        result = self.run_cli(
            "init",
            str(self.session),
            "--contract",
            str(self.draft),
            "--json",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["command"], "init")
        self.assertIn("contract is not user-confirmed", payload["error"])
        self.assertIn("contract is not user-confirmed", result.stderr)

    def test_json_argparse_error_envelope_lands_on_stdout(self) -> None:
        # argparse failures (missing required arg, bad --count type) raise
        # SystemExit(2) from inside build_parser().parse_args(), before
        # main()'s try/except ever runs -- previously always stderr-only and
        # stdout-empty regardless of --json.
        result = self.run_cli(
            "permit",
            str(self.session),
            "--action-id",
            "A1",
            "--stage",
            "primary_scout",
            "--category",
            "host_retrieval",
            "--route",
            "host-web",
            "--count",
            "not-an-int",
            "--fingerprint",
            "sha256:test",
            "--json",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["command"], "permit")
        self.assertIn("--count", payload["error"])
        self.assertIn("invalid int value", result.stderr)

    def test_argparse_error_without_json_flag_leaves_stdout_empty(self) -> None:
        # Non-json behavior must stay exactly as before: stderr-only usage
        # and error text, empty stdout, exit 2.
        result = self.run_cli(
            "patch",
            str(self.session),
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--patch", result.stderr)

    def test_cli_lists_capabilities_without_secret_values(self) -> None:
        secret = "test-secret-must-not-appear"
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = secret
        result = subprocess.run(
            [sys.executable, str(self.cli), "providers", "--json"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("registry_sha256", payload)
        self.assertIn("required_env", payload["providers"][0])
        self.assertNotIn(secret, result.stdout)

    def test_cli_loads_nearest_dotenv_without_printing_secret(self) -> None:
        secret = "nearest-dotenv-secret-must-not-appear"
        (self.root / ".env").write_text(f"OPENALEX_API_KEY={secret}\n", encoding="utf-8")
        env = os.environ.copy()
        env.pop("OPENALEX_API_KEY", None)
        result = subprocess.run(
            [sys.executable, str(self.cli), "providers", "--json"],
            cwd=self.root,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        providers = json.loads(result.stdout)["providers"]
        openalex = next(provider for provider in providers if provider["id"] == "openalex")
        self.assertEqual(
            openalex["required_env"],
            [{"name": "OPENALEX_API_KEY", "present": True}],
        )
        self.assertNotIn(secret, result.stdout)

    def test_providers_default_is_human_readiness_table(self) -> None:
        result = subprocess.run(
            [sys.executable, str(self.cli), "providers"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            env={**os.environ, "EXA_API_KEY": "secret-value", "BRAVE_SEARCH_API_KEY": ""},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ROUTE", result.stdout)
        self.assertIn("STATE", result.stdout)
        self.assertIn("exa", result.stdout)
        self.assertIn("ready", result.stdout)
        self.assertIn("brave", result.stdout)
        self.assertIn("missing-key", result.stdout)
        self.assertIn("BRAVE_SEARCH_API_KEY", result.stdout)
        self.assertNotIn("secret-value", result.stdout)
        self.assertNotIn("demo-probe", result.stdout)
        self.assertNotIn("test-only-unbound-candidate", result.stdout)
        self.assertIn("Machine output: providers --json", result.stdout)

    def test_providers_human_view_marks_disabled_routes(self) -> None:
        disabled = copy.deepcopy(
            next(item for item in load_provider_registry()["providers"] if item["id"] == "exa")
        )
        disabled["enabled"] = False
        overlay = write_overlay(self.root / "providers-overlay.json", [disabled])
        result = subprocess.run(
            [sys.executable, str(self.cli), "providers", "--registry-overlay", str(overlay)],
            cwd=self.repo,
            text=True,
            capture_output=True,
            env=os.environ.copy(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"(?m)^exa\s+disabled\s+-\s*$")

    def test_provider_readiness_formatter_marks_unsupported_binding_unbound(self) -> None:
        payload = {
            "providers": [
                {
                    "id": "unsupported-route",
                    "enabled": True,
                    "execution_binding": "future_binding",
                    "required_env": [],
                }
            ]
        }
        rendered = research_state._format_provider_readiness(payload)
        self.assertRegex(rendered, r"(?m)^unsupported-route\s+unbound\s+-\s*$")

    def test_provider_readiness_formatter_hides_test_only_id_without_adoption_status(self) -> None:
        payload = {
            "providers": [
                {
                    "id": "test-only-synthetic-route",
                    "enabled": True,
                    "execution_binding": "local",
                    "required_env": [],
                }
            ]
        }
        rendered = research_state._format_provider_readiness(payload)
        self.assertNotIn("test-only-synthetic-route", rendered)
        self.assertIn("Counts: ready=0, missing-key=0, disabled=0, unbound=0", rendered)

    def test_provider_readiness_formatter_handles_all_hidden_payload(self) -> None:
        payload = {
            "providers": [
                {
                    "id": "contract-route",
                    "roles": ["contract-test"],
                    "enabled": True,
                    "execution_binding": "local",
                    "required_env": [],
                },
                {
                    "id": "test-only-route",
                    "adoption_status": "not_tested",
                    "enabled": True,
                    "execution_binding": "local",
                    "required_env": [],
                },
            ]
        }
        rendered = research_state._format_provider_readiness(payload)
        self.assertIn("ROUTE", rendered)
        self.assertIn("STATE", rendered)
        self.assertIn("Counts: ready=0, missing-key=0, disabled=0, unbound=0", rendered)
        self.assertIn("Machine output: providers --json", rendered)

    def test_provider_readiness_formatter_keeps_headers_aligned_for_short_route(self) -> None:
        payload = {
            "providers": [
                {
                    "id": "exa",
                    "enabled": True,
                    "execution_binding": "local",
                    "required_env": [],
                }
            ]
        }
        rendered = research_state._format_provider_readiness(payload)
        self.assertEqual(
            rendered.splitlines()[:3],
            [
                "ROUTE  STATE  REQUIREMENT",
                "-----  -----  ------------",
                "exa    ready  none",
            ],
        )

    def test_init_snapshots_validated_registry_overlay(self) -> None:
        # Templated from the permanent "test-only-unbound-candidate" sentinel
        # (always disabled) rather than a real provider id -- copying brave
        # here relied on it still being disabled, which broke the moment
        # adapter/brave got built out for real (2026-07-11).
        added = copy.deepcopy(
            next(item for item in load_provider_registry()["providers"] if item["id"] == "test-only-unbound-candidate")
        )
        added["id"] = "disabled-extra"
        overlay = write_overlay(
            self.root / "overlay.json",
            [added],
        )
        resolved = load_provider_registry(overlay=overlay)
        contract = self._write_json(
            confirmed_medium_contract(resolved), "overlay-contract.json"
        )
        self.run_cli(
            "init",
            str(self.session),
            "--contract",
            str(contract),
            "--registry-overlay",
            str(overlay),
            "--json",
        )
        self.assertEqual(
            load_state(self.session)["capabilities"]["registry_sha256"],
            provider_registry_sha256(resolved),
        )

    def test_cli_artifact_add_uses_secure_ingestion(self) -> None:
        self._init_session()
        self._acquire_local()
        result = self.run_cli(
            "artifact-add",
            str(self.session),
            "--source",
            str(self.source),
            "--artifact-id",
            "A1",
            "--media-type",
            "text/plain",
            "--origin-kind",
            "local_output",
            "--action-id",
            "L1",
            "--sensitivity",
            "public",
            "--retention",
            "session",
            "--now",
            NOW,
            "--json",
        )
        artifact = json.loads(result.stdout)["artifact"]
        self.assertTrue((self.session / artifact["relative_path"]).exists())

    def test_cli_cannot_relabel_provider_payload_as_generic_artifact(self) -> None:
        self._init_session()
        result = self.run_cli(
            "artifact-add",
            str(self.session),
            "--source",
            str(self.source),
            "--artifact-id",
            "A1",
            "--media-type",
            "text/plain",
            "--origin-kind",
            "provider_payload",
            "--provider-id",
            "brave",
            "--attempt-id",
            "ATT1",
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provider artifacts require a bound adapter operation", result.stderr)

    def test_cli_promote_provider_payload_end_to_end(self) -> None:
        # No live network from a subprocess test: this session is built
        # entirely through CLI subcommands, with the boundary's own
        # spool-then-occurrence bookkeeping (research_harness.boundary.
        # execute_probe / _record_occurrence) stood in for directly -- a
        # hand-written spool file plus a `patch` adding the matching minimal
        # retrieval_occurrence -- rather than hitting the real GitHub API.
        # This mirrors the minimal-occurrence pattern tests/helpers.py
        # already uses for its own fetched-source fixtures (see
        # make_complete_pass_session's retrieval_occurrences patch).
        registry = load_provider_registry()
        contract = confirmed_demo_contract(
            route="github", request_count=1, probe_ceiling=1, registry=registry
        )
        contract["artifact_policy"]["allow_provider_payloads"] = True
        records = referenced_provider_records(contract, registry)
        contract["confirmation"] = {
            "confirmed_by": "user",
            "confirmed_at": NOW,
            "card_sha256": contract_card_sha256(contract),
            "registry_sha256": provider_registry_sha256(registry),
            "referenced_records_sha256": provider_records_sha256(records),
        }
        contract_path = self._write_json(contract, "github-promote-contract.json")
        session = self.root / "github-promote-session"
        self.run_cli(
            "init", str(session),
            "--contract", str(contract_path),
            "--json",
        )
        self.run_cli(
            "permit", str(session),
            "--action-id", "A1",
            "--stage", "primary_scout",
            "--category", "probe",
            "--route", "github",
            "--count", "1",
            "--fingerprint", "sha256:a1",
            "--now", NOW,
            "--json",
        )
        spool_dir = session / "provider_spool"
        spool_dir.mkdir(mode=0o700)
        (spool_dir / "A1.raw.json").write_bytes(
            json.dumps({"full_name": "octocat/Hello-World"}, ensure_ascii=False).encode("utf-8")
        )
        patch_path = self._write_json(
            {
                "operations": [
                    {
                        "op": "add",
                        "path": "/retrieval_occurrences/-",
                        "value": {"id": "occ-A1", "provider_id": "github", "action_id": "A1"},
                    }
                ]
            },
            "occurrence-patch.json",
        )
        self.run_cli("patch", str(session), "--patch", str(patch_path), "--now", NOW, "--json")

        result = self.run_cli(
            "promote", str(session),
            "--action-id", "A1",
            "--artifact-id", "PA1",
            "--now", NOW,
            "--json",
        )
        artifact = json.loads(result.stdout)["artifact"]
        self.assertEqual(artifact["id"], "PA1")
        self.assertEqual(
            artifact["provenance"],
            {
                "origin_kind": "provider_payload",
                "provider_id": "github",
                "attempt_or_occurrence_id": "A1",
            },
        )
        self.assertTrue((session / artifact["relative_path"]).exists())

    def test_cli_promote_rejects_path_traversal_action_id(self) -> None:
        # Security regression at the CLI boundary: `patch` can inject a
        # retrieval_occurrence with any action_id (organizer tooling), and
        # `promote --action-id` must refuse a path-traversal id rather than
        # walking provider_spool/<action_id>.raw.json outside the session.
        registry = load_provider_registry()
        contract = confirmed_demo_contract(
            route="github", request_count=1, probe_ceiling=1, registry=registry
        )
        contract["artifact_policy"]["allow_provider_payloads"] = True
        records = referenced_provider_records(contract, registry)
        contract["confirmation"] = {
            "confirmed_by": "user",
            "confirmed_at": NOW,
            "card_sha256": contract_card_sha256(contract),
            "registry_sha256": provider_registry_sha256(registry),
            "referenced_records_sha256": provider_records_sha256(records),
        }
        contract_path = self._write_json(contract, "github-traversal-contract.json")
        session = self.root / "github-traversal-session"
        self.run_cli(
            "init", str(session),
            "--contract", str(contract_path),
            "--json",
        )
        self.run_cli(
            "permit", str(session),
            "--action-id", "A1",
            "--stage", "primary_scout",
            "--category", "probe",
            "--route", "github",
            "--count", "1",
            "--fingerprint", "sha256:a1",
            "--now", NOW,
            "--json",
        )
        spool_dir = session / "provider_spool"
        spool_dir.mkdir(mode=0o700)
        (spool_dir / "A1.raw.json").write_bytes(
            json.dumps({"full_name": "octocat/Hello-World"}, ensure_ascii=False).encode("utf-8")
        )

        # Bait file OUTSIDE the session directory: session/provider_spool/
        # ../../pwned.raw.json resolves to session.parent / "pwned.raw.json".
        bait_path = self.root / "pwned.raw.json"
        bait_bytes = b'{"exfiltrated": "outside the session directory"}\n'
        bait_path.write_bytes(bait_bytes)

        malicious_action_id = "../../pwned"
        patch_path = self._write_json(
            {
                "operations": [
                    {
                        "op": "add",
                        "path": "/retrieval_occurrences/-",
                        "value": {
                            "id": "occ-evil",
                            "provider_id": "github",
                            "action_id": malicious_action_id,
                        },
                    }
                ]
            },
            "occurrence-traversal-patch.json",
        )
        self.run_cli("patch", str(session), "--patch", str(patch_path), "--now", NOW, "--json")

        result = self.run_cli(
            "promote", str(session),
            "--action-id", malicious_action_id,
            "--artifact-id", "PWNED1",
            "--now", NOW,
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("action_id", result.stderr)
        self.assertEqual(load_state(session)["artifact_index"], [])
        self.assertFalse((session / "raw").exists())
        self.assertEqual(bait_path.read_bytes(), bait_bytes)

    def test_cli_citations_deduplicates_by_url_and_flags_directly_verified(self) -> None:
        self._init_session()
        patch_path = self._write_json(
            {
                "operations": [
                    {
                        "op": "add",
                        "path": "/retrieval_occurrences/-",
                        "value": {
                            "id": "occ-A1",
                            "provider_id": "host-web",
                            "action_id": "A1",
                            "citations": [
                                {"url": "https://example.test/a", "title": "A"},
                                {"url": "https://example.test/b", "title": "B"},
                            ],
                        },
                    },
                    {
                        "op": "add",
                        "path": "/retrieval_occurrences/-",
                        "value": {
                            "id": "occ-A2",
                            "provider_id": "host-web",
                            "action_id": "A2",
                            "citations": [
                                {"url": "https://example.test/a", "title": "A dup"},
                                {"url": "https://example.test/c", "title": "C"},
                            ],
                        },
                    },
                    {
                        "op": "add",
                        "path": "/source_origins/-",
                        "value": {"id": "O1", "kind": "primary-authority", "independent": True},
                    },
                    {
                        "op": "add",
                        "path": "/sources/-",
                        "value": {
                            "id": "S1",
                            "origin_id": "O1",
                            "tier": "T1",
                            "title": "Fetched A",
                            "url": "https://example.test/a",
                            "direct_fetch": True,
                        },
                    },
                ]
            },
            "citations-patch.json",
        )
        self.run_cli("patch", str(self.session), "--patch", str(patch_path), "--now", NOW, "--json")

        result = self.run_cli("citations", str(self.session), "--json")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["unverified"], 2)
        by_url = {item["url"]: item for item in payload["citations"]}
        self.assertTrue(by_url["https://example.test/a"]["directly_verified"])
        self.assertEqual(
            sorted(by_url["https://example.test/a"]["occurrence_action_ids"]), ["A1", "A2"]
        )
        self.assertFalse(by_url["https://example.test/b"]["directly_verified"])
        self.assertFalse(by_url["https://example.test/c"]["directly_verified"])

        filtered = self.run_cli("citations", str(self.session), "--action-id", "A1", "--json")
        filtered_payload = json.loads(filtered.stdout)
        self.assertEqual(filtered_payload["total"], 2)
        self.assertEqual(
            sorted(item["url"] for item in filtered_payload["citations"]),
            ["https://example.test/a", "https://example.test/b"],
        )

    def test_public_purge_revalidates_and_rerenders_partial_session(self) -> None:
        session = make_complete_pass_session(
            self.root, tier="medium", posture="lookup", safe_action=True
        )
        render_session_result(session)
        result = purge_artifact(
            session, "A1", "retention expired", "PARTIAL", ("SA1",), NOW
        )
        state = load_state(session)
        self.assertEqual(state["summary"]["status"], "PARTIAL")
        self.assertTrue(result["validation"]["ok"], result)
        self.assertIn(
            state_sha256(state), (session / "report.html").read_text(encoding="utf-8")
        )

    def test_public_purge_defaults_to_blocked_and_renders_current_report(self) -> None:
        session = make_complete_pass_session(self.root, "medium", "lookup", safe_action=False)
        result = purge_artifact(session, "A1", "retention expired", "BLOCKED", (), NOW)
        self.assertEqual(load_state(session)["summary"]["status"], "BLOCKED")
        self.assertTrue(Path(result["report_path"]).exists())

    def test_public_recover_completes_pending_purge_validates_and_renders(self) -> None:
        session = make_complete_pass_session(self.root, "medium", "lookup")
        with mock.patch(
            "research_harness.artifacts._finalize_purge_tombstone", side_effect=OSError("crash")
        ):
            with self.assertRaises(OSError):
                purge_raw_artifact(session, "A1", "retention expired", "BLOCKED", (), NOW)
        result = recover_operation(session, LATER)
        state = load_state(session)
        self.assertEqual(state["artifact_index"][0]["availability"], "purged")
        self.assertEqual(result["validation"]["state_sha256"], state_sha256(state))
        self.assertIn(
            state_sha256(state), Path(result["report_path"]).read_text(encoding="utf-8")
        )

if __name__ == "__main__":
    unittest.main()
