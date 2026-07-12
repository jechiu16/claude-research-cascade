from __future__ import annotations

import subprocess
import unittest
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


if __name__ == "__main__":
    unittest.main()
