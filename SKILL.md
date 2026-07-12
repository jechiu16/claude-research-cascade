---
name: deep
description: Portable /deep research trigger for Claude Code and OpenAI Codex. Use only when the user explicitly types /deep to start a bounded, evidence-gated research session.
---

# Agent Deep Research Trigger

You are the **Organizer**. This Agent Skills-compatible workflow is shared by
Claude Code and OpenAI Codex. Read [HARNESS.md](HARNESS.md) and execute its v2
protocol.

## Hard Boundary

The resolved provider registry is the sole source of truth for which routes are enabled. Inspect current capabilities with `"$PY" <skill-dir>/scripts/research_state.py providers --json`; it reports each route's enabled state, binding, adoption status, and required-key presence without reading secret values. A present credential is not execution readiness: a route is usable only when the registry marks it enabled and v2-bound. Every other route stays unusable until its adapter meets the same boundary and adoption gates. Use Exa for anti-lock-in or verification where its independent index is valuable; Brave is the recommended general scout.

## First-Run Sanity Check

Resolve the directory containing this `SKILL.md`, then run
`"$PY" <skill-dir>/scripts/research_state.py demo /tmp/deep-demo --json`. It
exercises permit, boundary execution, occurrence, validation, and rendering
with zero network, zero keys, and zero cost. If it prints
`"validation_ok": true`, the runtime is healthy.

## Required Flow

1. Infer the question and select an epistemic `posture`: `lookup`, `synthesis`, `scientific`, or `decision`.
2. Recommend a `tier`: `low`, `medium`, `high`, or an exact custom envelope. Show the user the selected provider route, logical invocations, physical request counts, reserved reinforcement calls, host-context class, and estimated spend uncertainty.
3. Run `scripts/research_state.py prepare`. Show its contract card and binding hashes. Do not run `confirm`, `init`, or any research action until the user explicitly pulls the trigger.
4. After confirmation, run `confirm` with all three exact displayed hashes (card, registry, referenced route records), then `init` with the confirmed contract. One primary scout route is allowed.
5. Before every action, acquire its exact `(stage, category, route)` permit. Record uncertain attempts as consumed; never invent a refund.
6. Maintain canonical `state.json` through revision-checked `patch` operations. Ingest only provenance-bound raw artifacts through `artifact-add`; never create a second full Markdown report.
7. Medium/High scientific or decision work performs anti-lock-in and coverage-audit checks. High `PASS` additionally requires a context-separated verifier that did not produce the candidate conclusion.
8. Run `validate`, then `render`. `PASS` is deliverable only when validation returns `ok=true`; otherwise return `PARTIAL` or `BLOCKED` with safe actions and gaps.

## Host Map

| Harness operation | Binding |
|---|---|
| Contract choice | Use the host's user-input surface when available; otherwise use concise chat options |
| Host retrieval | Use the host's native search/fetch tools, only after the matching permit |
| Local applicability | Bash or file inspection, only after a local permit; no network egress |
| Canonical runtime | `"$PY" "$AGENT_DEEP_RESEARCH_DIR/scripts/research_state.py" <command>` |
| State recovery | `research_state.py recover <session> --json` |
| Final gate | `research_state.py validate <session> --json` |
| Human report | `research_state.py render <session> --json` |
| Language | Answer in the user's language; use English worker queries only when a bound route requires it |

When the user's working language is Traditional Chinese, author human-facing canonical narrative fields in Traditional Chinese before validation and rendering. Preserve exact evidence excerpts, source titles, identifiers, URLs, hashes, provider IDs, status tokens, and machine diagnostics in their original form. The deterministic renderer does not call a translation model.

Use the project virtual environment when available. Keep session state, raw artifacts, events, and `report.html` under a host-sanctioned session directory.
