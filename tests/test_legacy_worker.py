from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from scripts import deep_research


class GeminiWorkerTests(unittest.TestCase):
    def test_extract_joins_substantial_body_steps(self) -> None:
        short = types.SimpleNamespace(type="status", name="", title="", content=[types.SimpleNamespace(text="short")])
        first = types.SimpleNamespace(type="answer", name="", title="", content=[types.SimpleNamespace(text="a" * 600)])
        second = types.SimpleNamespace(type="answer", name="", title="", content=[types.SimpleNamespace(text="b" * 700)])
        interaction = types.SimpleNamespace(steps=[short, first, second], outputs=[])

        result = deep_research._gemini_extract(interaction, "agent")

        self.assertEqual(result["report_text"], "a" * 600 + "\n\n" + "b" * 700)
        self.assertEqual(result["model"], "agent")

    def test_extract_rejects_completed_response_without_text(self) -> None:
        interaction = types.SimpleNamespace(steps=[], outputs=[])
        with self.assertRaisesRegex(RuntimeError, "抽不到報告文字"):
            deep_research._gemini_extract(interaction, "agent")

    def test_poll_returns_completed_interaction_without_sleeping(self) -> None:
        completed = types.SimpleNamespace(status="completed")
        client = types.SimpleNamespace(
            interactions=types.SimpleNamespace(get=mock.Mock(return_value=completed))
        )

        self.assertIs(deep_research._gemini_poll(client, "job", 1), completed)
        client.interactions.get.assert_called_once_with("job")

    def test_poll_marks_terminal_failure(self) -> None:
        failed = types.SimpleNamespace(status="failed")
        client = types.SimpleNamespace(
            interactions=types.SimpleNamespace(get=mock.Mock(return_value=failed))
        )

        with self.assertRaises(deep_research.JobError) as caught:
            deep_research._gemini_poll(client, "job", 1)
        self.assertTrue(caught.exception.terminal)
        self.assertEqual(caught.exception.resume, "gemini:job")

    @mock.patch("importlib.metadata.version", return_value="1.70.0")
    def test_client_rejects_legacy_sdk(self, _version: mock.Mock) -> None:
        google = types.ModuleType("google")
        google.genai = types.SimpleNamespace()
        with mock.patch.dict(sys.modules, {"google": google}):
            with self.assertRaisesRegex(RuntimeError, "too old"):
                deep_research._gemini_client()


class WorkerLedgerTests(unittest.TestCase):
    def test_completed_event_clears_pending_resume_token(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.jsonl"
            records = [
                {"event": "submitted", "resume": "gemini:job"},
                {"event": "failed", "resume": "gemini:job", "terminal": False},
                {"event": "completed", "resume": "gemini:job"},
            ]
            ledger.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

            self.assertEqual(deep_research.scan_pending([ledger]), [])

    def test_nonterminal_failure_stays_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.jsonl"
            records = [
                {"event": "submitted", "resume": "perplexity:job"},
                {"event": "failed", "resume": "perplexity:job", "terminal": False},
            ]
            ledger.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

            pending = deep_research.scan_pending([ledger])

            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["resume"], "perplexity:job")


if __name__ == "__main__":
    unittest.main()
