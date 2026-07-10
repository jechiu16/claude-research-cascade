#!/usr/bin/env python3
"""Validate canonical v2 sessions or retained legacy Markdown state.

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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_harness.validation import validate_session

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

    depth = contract.group(1) if contract else None
    if status_done and depth and depth != "shallow":
        if not re.search(r"\[T[123]\]|\bT[123]\b", text):
            warns.append("no source tier annotations ([T1]/[T2]/[T3]) — corroboration is "
                         "authority-weighted; untiered sources default to T3 suspicion")
        if not re.search(r"(?im)^verification:", text):
            warns.append("no `verification:` line (checked=N flipped=M) — the session's "
                         "calibration signal is missing")

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

    v2_session = None
    if state_path.is_dir():
        v2_session = state_path
    elif state_path.name == "state.json":
        try:
            candidate = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            candidate = None
        if isinstance(candidate, dict) and candidate.get("schema_version") == "2.0":
            v2_session = state_path.parent
    if v2_session is not None:
        try:
            report = validate_session(v2_session)
        except Exception as exc:
            print(
                json.dumps({"schema_version": "2.0", "ok": False, "error": str(exc)})
                if args.json
                else f"FAIL {exc}"
            )
            return 1
        result = {"schema_version": "2.0", "session": str(v2_session), **report.to_dict()}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        else:
            print(f"/deep v2 session validation — {v2_session}")
            for issue in report.issues:
                print(f"{issue.level} {issue.code}: {issue.message} ({issue.path})")
            if report.ok:
                print("OK   all deterministic v2 gates passed")
        return 0 if report.ok else 1

    result = validate(state_path, args.ledger)
    result["schema_version"] = "legacy"
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
