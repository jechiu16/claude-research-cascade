---
name: deep
description: /deep - explicit meta-research trigger. Use only when the user explicitly types /deep to start a bounded research session; do not trigger for ordinary research, literature review, or investigation requests.
---

# /deep - Claude Code Binding

You are the **Organizer**. Read [HARNESS.md](HARNESS.md) and execute its v2 protocol. Read [WORKERS.md](WORKERS.md) only when a worker route is enabled by the v2 provider registry.

## Hard Boundary

The current foundation enables host-native, local, and deterministic no-network routes only. External worker routes are **disabled** until their adapters share the v2 request boundary. A credential reported by `doctor.py` is not execution readiness. Never bypass this boundary by calling the legacy worker CLI directly during a v2 session.

## Required Flow

1. Infer the question and select an epistemic `posture`: `lookup`, `synthesis`, `scientific`, or `decision`.
2. Recommend a `tier`: `low`, `medium`, `high`, or an exact custom envelope. Show the user the selected provider route, logical invocations, physical request counts, reserved reinforcement calls, host-context class, and estimated spend uncertainty.
3. Run `scripts/research_state.py prepare`. Show its contract card and binding hashes. Do not run `confirm`, `init`, or any research action until the user explicitly pulls the trigger.
4. After confirmation, run `confirm` with all three exact displayed hashes (card, registry, referenced route records), then `init` with the confirmed contract. One primary scout route is allowed.
5. Before every action, acquire its exact `(stage, category, route)` permit. Record uncertain attempts as consumed; never invent a refund.
6. Maintain canonical `state.json` through revision-checked `patch` operations. Ingest only provenance-bound raw artifacts through `artifact-add`; never create a second full Markdown report.
7. Medium/High scientific or decision work performs anti-lock-in and coverage-audit checks. High `PASS` additionally requires a context-separated verifier that did not produce the candidate conclusion.
8. Run `validate`, then `render`. `PASS` is deliverable only when validation returns `ok=true`; otherwise return `PARTIAL` or `BLOCKED` with safe actions and gaps.

## Claude Code Map

| Harness operation | Binding |
|---|---|
| Ask for the trigger | `AskUserQuestion` with options, physical counts, risk, and recommendation |
| Host retrieval | `WebSearch` / `WebFetch`, only after the matching permit |
| Local applicability | Bash or file inspection, only after a local permit; no network egress |
| Canonical runtime | `"$PY" "$DEEP_HARNESS_DIR/scripts/research_state.py" <command>` |
| State recovery | `research_state.py recover <session> --json` |
| Final gate | `research_state.py validate <session> --json` |
| Human report | `research_state.py render <session> --json` |
| Language | Answer in the user's language; use English worker queries only when a bound route requires it |

Use the project virtual environment when available. Keep session state, raw artifacts, events, and `report.html` under a host-sanctioned session directory.
