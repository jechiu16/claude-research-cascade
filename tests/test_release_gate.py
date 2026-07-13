from __future__ import annotations

import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import release_gate


class ReleaseGateTests(unittest.TestCase):
    def test_module_docstring_discloses_dependency_audit_network_access(self) -> None:
        self.assertEqual(
            release_gate.__doc__,
            "Run release-readiness checks; pip_audit may require network access.",
        )

    @mock.patch("scripts.release_gate.subprocess.run")
    def test_run_raises_on_failure(self, subprocess_run: mock.Mock) -> None:
        subprocess_run.return_value = subprocess.CompletedProcess(["false"], 2)
        with self.assertRaisesRegex(RuntimeError, "failed with exit code 2"):
            release_gate.run("probe", ["false"])

    @mock.patch("scripts.release_gate.subprocess.run")
    def test_run_records_success(self, subprocess_run: mock.Mock) -> None:
        subprocess_run.return_value = subprocess.CompletedProcess(["true"], 0)
        self.assertEqual(release_gate.run("probe", ["true"]), {"name": "probe", "status": "passed"})

    def _sdist(self, names: list[str]) -> str:
        root = Path(self.tempdir.name)
        source = root / "source"
        for name in names:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        archive = root / "package.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(source, arcname="package")
        return str(archive)

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def test_sdist_field_package_requires_direct_capture_bytes(self) -> None:
        required = [
            "examples/field/04-duckdb-concurrency-boundary/session/state.json",
            "examples/field/04-duckdb-concurrency-boundary/session/events.jsonl",
            "examples/field/04-duckdb-concurrency-boundary/session/report.html",
            "examples/field/04-duckdb-concurrency-boundary/session/raw/A1.bin",
            "examples/field/04-duckdb-concurrency-boundary/session/raw/A2.bin",
        ]
        self.assertEqual(
            release_gate.check_sdist_field_package([self._sdist(required)]),
            {"name": "sdist field package", "status": "passed"},
        )

    def test_sdist_field_package_rejects_provider_spool(self) -> None:
        required = [
            "examples/field/04-duckdb-concurrency-boundary/session/state.json",
            "examples/field/04-duckdb-concurrency-boundary/session/events.jsonl",
            "examples/field/04-duckdb-concurrency-boundary/session/report.html",
            "examples/field/04-duckdb-concurrency-boundary/session/raw/A1.bin",
            "examples/field/04-duckdb-concurrency-boundary/session/raw/A2.bin",
            "examples/field/04-duckdb-concurrency-boundary/session/provider_spool/D1.raw.json",
        ]
        with self.assertRaisesRegex(RuntimeError, "must not contain provider_spool"):
            release_gate.check_sdist_field_package([self._sdist(required)])


if __name__ == "__main__":
    unittest.main()
