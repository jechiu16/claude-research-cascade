#!/usr/bin/env python3
"""Run release-readiness checks; pip_audit may require network access."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str]) -> dict:
    print(f"[gate] {label}", file=sys.stderr)
    completed = subprocess.run(command, cwd=ROOT, text=True)
    if completed.returncode:
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")
    return {"name": label, "status": "passed"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="skip the clean-worktree check while developing the gate itself",
    )
    args = parser.parse_args(argv)
    python = sys.executable
    checks = []
    try:
        checks.append(run("diff whitespace", ["git", "diff", "--check"]))
        checks.append(run("staged diff whitespace", ["git", "diff", "--cached", "--check"]))
        if not args.allow_dirty:
            status = subprocess.run(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
            ).stdout
            if status:
                raise RuntimeError("worktree is not clean")
            checks.append({"name": "clean worktree", "status": "passed"})

        checks.append(run("erase prior coverage data", [python, "-m", "coverage", "erase"]))
        checks.append(run("unit tests", [python, "-m", "coverage", "run", "-m", "unittest", "discover", "-s", "tests", "-q"]))
        checks.append(run("coverage threshold", [python, "-m", "coverage", "report"]))
        checks.append(run("static checks", [python, "-m", "ruff", "check", "research_harness", "scripts", "tests"]))

        with tempfile.TemporaryDirectory(prefix="deep-release-") as td:
            session = str(Path(td) / "session")
            checks.append(run("installed CLI demo", [str(Path(python).parent / "deep-research-state"), "demo", session, "--json"]))

        for generated in (ROOT / "build", ROOT / "dist"):
            shutil.rmtree(generated, ignore_errors=True)
        checks.append(run("build distributions", [python, "-m", "build"]))
        artifacts = sorted(str(path) for path in (ROOT / "dist").iterdir())
        checks.append(run("distribution metadata", [python, "-m", "twine", "check", *artifacts]))
        checks.append(run("dependency audit", [python, "-m", "pip_audit", "--skip-editable"]))
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "checks": checks, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
