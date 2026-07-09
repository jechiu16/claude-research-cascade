#!/usr/bin/env python3
"""Local diagnostics for the /deep worker harness.

This script does not call external APIs. It checks the local runtime, imports,
environment keys, writable reports directory, and provider readiness.
"""

import argparse
import importlib.util
import json
import os
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deep_research.py"
REPORTS_DIR = Path.cwd() / "reports"

PACKAGES = {
    "requests": {
        "module": "requests",
        "required_for": ["sonar", "cascade", "scholar", "perplexity", "openai", "deepseek"],
    },
    "python-dotenv": {
        "module": "dotenv",
        "required_for": ["loading .env files"],
    },
    "google-genai": {
        "module": "google.genai",
        "required_for": ["gemini"],
        "optional": True,
    },
}

PROVIDERS = {
    "demo": {"keys": [], "packages": []},
    "scholar": {"keys": [], "optional_keys": ["S2_API_KEY"], "packages": ["requests"]},
    "sonar": {"keys": ["PERPLEXITY_API_KEY"], "packages": ["requests"]},
    "cascade": {"keys": ["PERPLEXITY_API_KEY"], "packages": ["requests"]},
    "perplexity": {"keys": ["PERPLEXITY_API_KEY"], "packages": ["requests"]},
    "openai": {"keys": ["OPENAI_API_KEY"], "packages": ["requests"]},
    "gemini": {"keys": ["GEMINI_API_KEY"], "packages": ["google-genai"]},
    "deepseek": {"keys": ["DEEPSEEK_API_KEY"], "packages": ["requests"]},
}


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def load_dotenv_if_available() -> bool:
    if not has_module("dotenv"):
        return False
    from dotenv import find_dotenv, load_dotenv

    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found)
    load_dotenv(ROOT / ".env")
    return True


def scan_pending_jobs() -> list:
    """已提交未收割的 async job（讀 cwd ledgers，不打網路）— 開 session 先收割再花新錢。
    配對邏輯與 deep_research.py scan_pending 一致：submitted / 非終局 failed / interrupted
    = pending；completed 或 terminal failed = cleared。"""
    state = {}
    for ledger in sorted(REPORTS_DIR.glob("*.ledger.jsonl")):
        try:
            lines = ledger.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            token = rec.get("resume")
            if not token:
                continue
            if rec.get("event") == "completed" or (rec.get("event") == "failed" and rec.get("terminal")):
                state[token] = ("cleared", str(ledger))
            elif state.get(token, ("",))[0] != "cleared":
                state[token] = ("pending", str(ledger))
    return [{"resume": token, "ledger": path}
            for token, (status, path) in state.items() if status == "pending"]


def check_reports_dir() -> dict:
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        probe = REPORTS_DIR / ".doctor_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"ok": True, "path": str(REPORTS_DIR)}
    except OSError as exc:
        return {"ok": False, "path": str(REPORTS_DIR), "error": str(exc)}


def check_worker_compile() -> dict:
    if not SCRIPT.exists():
        return {"ok": False, "error": "worker script not found"}
    try:
        py_compile.compile(str(SCRIPT), doraise=True)
        return {"ok": True}
    except py_compile.PyCompileError as exc:
        return {"ok": False, "error": str(exc)}


def provider_status(packages: dict) -> dict:
    out = {}
    for provider, req in PROVIDERS.items():
        missing_packages = [p for p in req.get("packages", []) if not packages[p]["installed"]]
        missing_keys = [k for k in req.get("keys", []) if not os.getenv(k)]
        optional_missing = [k for k in req.get("optional_keys", []) if not os.getenv(k)]
        if missing_packages or missing_keys:
            status = "blocked"
        elif optional_missing:
            status = "ready-keyless"
        else:
            status = "ready"
        out[provider] = {
            "status": status,
            "missing_packages": missing_packages,
            "missing_keys": missing_keys,
            "missing_optional_keys": optional_missing,
        }
    return out


def build_report() -> dict:
    packages = {
        name: {
            "installed": has_module(spec["module"]),
            "module": spec["module"],
            "optional": bool(spec.get("optional")),
            "required_for": spec["required_for"],
        }
        for name, spec in PACKAGES.items()
    }
    dotenv_loaded = load_dotenv_if_available()
    reports = check_reports_dir()
    providers = provider_status(packages)
    worker_compile = check_worker_compile()
    python_ok = sys.version_info >= (3, 9)
    smoke_ok = python_ok and worker_compile["ok"] and reports["ok"]
    return {
        "status": "ok" if smoke_ok else "error",
        "python": {
            "version": sys.version.split()[0],
            "ok": python_ok,
            "executable": sys.executable,
        },
        "paths": {
            "root": str(ROOT),
            "worker": str(SCRIPT),
            "worker_compile": worker_compile,
            "reports_dir": reports,
        },
        "dotenv_loaded": dotenv_loaded,
        "packages": packages,
        "providers": providers,
        "pending_async_jobs": scan_pending_jobs(),
        "next_smoke_test": (
            'python scripts/deep_research.py --provider demo '
            '--ledger reports/deep_state_demo.ledger.jsonl "smoke test"'
        ),
    }


def print_human(report: dict):
    def mark(ok: bool) -> str:
        return "OK" if ok else "FAIL"

    print("/deep doctor")
    print(f"{mark(report['python']['ok'])} python {report['python']['version']} ({report['python']['executable']})")
    print(f"{mark(report['paths']['worker_compile']['ok'])} worker {report['paths']['worker']}")
    if not report["paths"]["worker_compile"]["ok"]:
        print(f"  error: {report['paths']['worker_compile'].get('error')}")
    reports = report["paths"]["reports_dir"]
    print(f"{mark(reports['ok'])} reports dir {reports['path']}")
    if not reports["ok"]:
        print(f"  error: {reports.get('error')}")
    print(("OK" if report["dotenv_loaded"] else "WARN") + " .env loading via python-dotenv")

    print("\nPackages")
    for name, item in report["packages"].items():
        label = "OK" if item["installed"] else ("WARN" if item["optional"] else "WARN")
        print(f"{label} {name} ({item['module']})")

    print("\nProviders")
    for name, item in report["providers"].items():
        label = "OK" if item["status"].startswith("ready") else "WARN"
        print(f"{label} {name}: {item['status']}")
        if item["missing_packages"]:
            print(f"  missing packages: {', '.join(item['missing_packages'])}")
        if item["missing_keys"]:
            print(f"  missing keys: {', '.join(item['missing_keys'])}")
        if item["missing_optional_keys"]:
            print(f"  optional key not set: {', '.join(item['missing_optional_keys'])}")

    pending = report["pending_async_jobs"]
    if pending:
        print("\nPending async jobs (submitted, not harvested — resume before new spend)")
        for job in pending:
            print(f"WARN {job['resume']}  ({job['ledger']})")

    print("\nNext")
    print(report["next_smoke_test"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local /deep worker harness readiness")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
