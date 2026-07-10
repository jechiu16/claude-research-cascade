#!/usr/bin/env python3
"""Render one canonical v2 session as deterministic report.html."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_harness.rendering import render_session_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Render deterministic /deep v2 HTML")
    parser.add_argument("session")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        rendered = render_session_result(Path(args.session))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    payload = {
        "report_path": str(rendered.path.resolve()),
        "state_sha256": rendered.state_sha256,
        "report_sha256": rendered.report_sha256,
        "validation": rendered.validation.to_dict(),
    }
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if args.json
        else json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
