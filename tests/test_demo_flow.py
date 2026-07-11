from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import research_state  # noqa: E402  (scripts/ path injected above)


class DemoFlowTests(unittest.TestCase):
    def test_demo_command_runs_full_loop_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            session = Path(tempdir) / "session"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = research_state.main(["demo", str(session), "--json"])
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["validation_ok"])
            self.assertEqual(payload["occurrence"], "occ-demo-1")
            self.assertTrue((session / "report.html").exists())
            self.assertTrue((session / "provider_spool" / "demo-1.raw.json").exists())
            state = json.loads((session / "state.json").read_text(encoding="utf-8"))
            occurrence = state["retrieval_occurrences"][0]
            self.assertEqual(occurrence["kind"], "demo_probe")
            self.assertEqual(occurrence["cost_usd"], 0.0)

    def test_demo_probe_route_cannot_support_claims(self) -> None:
        # The registry bars demo routes from evidence; the demo exercises the
        # machine, it must never masquerade as research.
        from research_harness.providers import load_provider_registry

        registry = load_provider_registry()
        demo = next(p for p in registry["providers"] if p["id"] == "demo-probe")
        self.assertFalse(demo["evidence_capabilities"]["can_support_claims"])


if __name__ == "__main__":
    unittest.main()
