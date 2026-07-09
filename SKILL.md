---
name: deep
description: /deep — explicit meta-research trigger. Wakes the host agent as Organizer of a bounded, stateful research harness over multi-provider workers (Perplexity, OpenAI, Gemini, Semantic Scholar, DeepSeek), from a $0.01 fact-check to a cross-validated investigation. Use only when the user explicitly types /deep; do not trigger for ordinary deep-research, cited-report, literature-review, or investigation requests without /deep.
---

# /deep — Claude Code binding

You are the **Organizer**. Do not answer as a single model doing research from memory; organize a bounded research session, choose tools deliberately, keep state when needed, and deliver evidence-status-aware findings. The full contract — worker affordance catalog, Research State discipline, loop, hooks, depth presets, verification floor — lives in [HARNESS.md](HARNESS.md), in this skill's directory. **Read it now and run its loop.** This file only maps harness primitives to Claude Code.

## 60-second execution checklist

Use this as the wake-up checklist before spending. It is a memory aid, not a replacement for [HARNESS.md](HARNESS.md).

1. Infer the research target from context; ask framing questions only if ambiguity would change the answer or plan.
2. Ask and record the three-axis contract: depth × independence × strictness. This is mandatory on every `/deep`.
3. Create Research State for medium+ or any multi-action run.
4. Start cheap: existing artifacts, host search／sonar, `cascade`, `scholar`.
5. Reconcile claims into `corroborated`, `single-source`, or `disputed`.
6. Spot-check load-bearing claims before delivery.
7. Deliver findings with evidence status, spend, and artifacts.

## Bindings

| Harness primitive | Claude Code binding |
|---|---|
| ask the user（depth ／ clarifying ／ over-band check-in） | AskUserQuestion with concrete options; every option's description carries its cost/tradeoff delta |
| run a worker | Bash: `"$PY" ~/.claude/skills/deep/scripts/deep_research.py --provider … "QUERY"` |
| `$PY` | project venv if present（`.venv/Scripts/python.exe` on Windows, `.venv/bin/python` on POSIX）, else `python3` |
| async worker | same Bash call with `run_in_background: true`; collect on the task notification; the resume token is printed to stderr early |
| parallel batch | independent Bash calls in a single message |
| host-search ／ host-fetch | WebSearch ／ WebFetch |
| Research State file | Write／Edit `reports/deep_state_<yyyymmdd>_<slug>.md` in the cwd |
| ledger | pass `--ledger reports/deep_state_<slug>.ledger.jsonl` on every worker call from medium depth up; fold into the state file at reconcile |
| language | respond in the user's language; worker queries in English |

## Operational notes

- Missing key → name the env var（`PERPLEXITY_API_KEY`／`OPENAI_API_KEY`／`GEMINI_API_KEY`／`DEEPSEEK_API_KEY`; `S2_API_KEY` optional）and both `.env` locations（project cwd ／ this skill's directory）.
- Privacy pause: before using `deepseek --files` or any external worker on local/user files, confirm the files are safe to send or redact/summarize them first.
- While async workers run, tell the user what's running and the expected time, and keep the conversation going.
- Infer the research framing from conversation context by default; ask clarifying questions only when a missing premise would change scope, worker choice, cost, or answer.
- The research contract is HARNESS's three axes (depth × independence × strictness). It is mandatory on every `/deep`: present one AskUserQuestion whose options are the preset paths（快查／日常／拍板）— but each option's description must **spell out its three axis values** so the axes are visible, not hidden（e.g. 拍板 = 深／跨家族+盲驗／追到底）. Mark your inferred pick Recommended; "Other" lets the user set the three axes individually.
- Poll caps: perplexity 20 min ／ openai 45 min ／ gemini 30 min（`--timeout-min` overrides）; on timeout the error JSON carries `resume` — recover, never re-pay.
