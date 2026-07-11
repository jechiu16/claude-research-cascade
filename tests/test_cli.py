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
from research_harness.operations import purge_artifact, recover_operation
from research_harness.providers import load_provider_registry, provider_registry_sha256
from research_harness.rendering import render_session
from research_harness.state import state_sha256
from research_harness.storage import load_state
from tests.helpers import (
    NOW,
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
        self.validator_cli = self.repo / "scripts" / "validate_state.py"
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
            "--question",
            "Choose a cache",
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
        contract = json.loads(confirmed.stdout)["contract"]
        self.assertEqual(
            contract["confirmation"]["registry_sha256"],
            prepared_payload["binding"]["registry_sha256"],
        )
        confirmed_path = self._write_json(contract, "confirmed.json")
        self.run_cli(
            "init",
            str(self.session),
            "--question",
            "Q",
            "--contract",
            str(confirmed_path),
            "--json",
        )

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
            "--question",
            "Q",
            "--contract",
            str(self.draft),
            "--json",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contract is not user-confirmed", result.stderr)

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

    def test_init_snapshots_validated_registry_overlay(self) -> None:
        added = copy.deepcopy(next(item for item in load_provider_registry()["providers"] if item["id"] == "brave"))
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
            "--question",
            "Q",
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

    def test_public_purge_revalidates_and_rerenders_partial_session(self) -> None:
        session = make_complete_pass_session(
            self.root, tier="medium", posture="lookup", safe_action=True
        )
        render_session(session)
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

    def test_validate_state_script_accepts_v2_session_directory(self) -> None:
        self._init_session()
        result = subprocess.run(
            [sys.executable, str(self.validator_cli), str(self.session), "--json"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["schema_version"], "2.0")


if __name__ == "__main__":
    unittest.main()
