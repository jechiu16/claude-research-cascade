#!/usr/bin/env python3
"""Validate a real /deep session's artifacts (Research State + ledger).

This is the artifact gate: it constrains the *product*, never the process.
The Organizer researches however it judges best; before delivery this script
checks that the deliverable's skeleton is intact — contract axes recorded,
claims carry recognized evidence statuses, spend reconciles against the
ledger, and no paid async job is silently unharvested.

Usage:
  python validate_state.py [STATE_FILE] [--ledger FILE] [--json]

With no STATE_FILE, validates the newest reports/deep_state_*.md under cwd.
Without --ledger, tries the `ledger=<path>` pointer inside the state file.

Exit 1 only on FAIL (missing skeleton). WARNs are for the Organizer to
report honestly in delivery; they never fail the run.
"""

import argparse
import json
import re
import sys
from pathlib import Path

STATUS_VOCAB = ("corroborated", "single-source", "corroborated-same-family",
                "disputed", "retired", "unverified")
CONTRACT_RE = re.compile(r"depth=(\S+)\s*\|\s*independence=(\S+)\s*\|\s*strictness=(\S+)")


def newest_state(cwd: Path):
    candidates = sorted(cwd.glob("reports/deep_state_*.md"),
                        key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def parse_ledger(path: Path):
    records, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return records, bad


def pending_tokens(records):
    state = {}
    for rec in records:
        token = rec.get("resume")
        if not token:
            continue
        if rec.get("event") == "completed" or (rec.get("event") == "failed" and rec.get("terminal")):
            state[token] = "cleared"
        elif state.get(token) != "cleared":
            state[token] = "pending"
    return [t for t, s in state.items() if s == "pending"]


def validate(state_path: Path, ledger_path):
    fails, warns, info = [], [], []
    text = state_path.read_text(encoding="utf-8")

    contract = CONTRACT_RE.search(text)
    if not contract:
        fails.append("contract line missing or malformed "
                     "(need `depth=... | independence=... | strictness=...`)")
    status_done = "status=done" in text

    if not any(re.search(rf"\b{s}\b", text) for s in STATUS_VOCAB):
        fails.append("no recognized evidence status found "
                     f"(expected one of: {', '.join(STATUS_VOCAB)})")
    if not re.search(r"(?i)\bclaims?\b", text):
        fails.append("no claims section/line found")

    if "$" not in text:
        warns.append("no spend figure ($) found in state")
    if status_done and re.search(r"\bunverified\b", text):
        warns.append("status=done but some claims are still `unverified`")
    if status_done and re.search(r"\bdisputed\b", text):
        info.append("delivery carries `disputed` claims — fine if surfaced honestly")

    if ledger_path is None:
        pointer = re.search(r"ledger=([^\s;]+)", text)
        if pointer:
            ledger_path = Path(pointer.group(1))

    ledger_summary = None
    if ledger_path is not None:
        ledger_path = Path(ledger_path)
        if not ledger_path.is_absolute():
            ledger_path = Path.cwd() / ledger_path
        if not ledger_path.exists():
            warns.append(f"ledger not found: {ledger_path}")
        else:
            records, bad = parse_ledger(ledger_path)
            if bad:
                warns.append(f"{bad} unparsable ledger line(s) in {ledger_path.name}")
            total = sum(r.get("cost_usd") or 0.0 for r in records)
            ledger_summary = {"path": str(ledger_path), "records": len(records),
                              "cost_sum_usd": round(total, 4)}
            stated_m = re.search(r"running total:?\s*\$([0-9]+(?:\.[0-9]+)?)", text)
            if stated_m:
                stated = float(stated_m.group(1))
                if abs(stated - total) > max(0.05, 0.25 * max(stated, total)):
                    warns.append(f"state says running total ${stated:.2f} but ledger sums "
                                 f"${total:.2f} — reconcile before delivery")
            else:
                warns.append("no `running total $X` figure found to reconcile against ledger")
            pending = pending_tokens(records)
            if pending:
                warns.append("unharvested async job(s) — harvest with --resume before "
                             "paying for new work: " + ", ".join(pending))

    return {"state": str(state_path), "contract": contract.groups() if contract else None,
            "status_done": status_done, "ledger": ledger_summary,
            "fails": fails, "warns": warns, "info": info}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate /deep Research State + ledger artifacts")
    parser.add_argument("state", nargs="?", default=None,
                        help="state file path (default: newest reports/deep_state_*.md)")
    parser.add_argument("--ledger", default=None, help="ledger path (default: `ledger=` pointer in state)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    state_path = Path(args.state) if args.state else newest_state(Path.cwd())
    if state_path is None or not state_path.exists():
        print(json.dumps({"error": "no state file found", "hint": "reports/deep_state_*.md"})
              if args.json else "FAIL no state file found (reports/deep_state_*.md)")
        return 1

    result = validate(state_path, args.ledger)
    ok = not result["fails"]
    if args.json:
        result["ok"] = ok
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"/deep state validation — {state_path}")
        if result["contract"]:
            depth, independence, strictness = result["contract"]
            print(f"OK   contract depth={depth} independence={independence} strictness={strictness}")
        for item in result["fails"]:
            print(f"FAIL {item}")
        for item in result["warns"]:
            print(f"WARN {item}")
        for item in result["info"]:
            print(f"INFO {item}")
        if result["ledger"]:
            print(f"OK   ledger {result['ledger']['records']} record(s), "
                  f"cost sum ${result['ledger']['cost_sum_usd']:.4f}")
        if ok and not result["warns"]:
            print("OK   deliverable skeleton intact")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
