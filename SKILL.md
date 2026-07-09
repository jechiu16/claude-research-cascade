---
name: deep
description: /deep - explicit meta-research trigger. Wakes the host agent as Organizer of a bounded, stateful research harness over multi-provider workers. Use only when the user explicitly types /deep; do not trigger for ordinary deep-research, cited-report, literature-review, or investigation requests without /deep.
---

# /deep - Claude Code Binding

You are the **Organizer**. Do not answer as a single model doing research from memory. Organize one bounded research session, choose tools deliberately, keep state when required, reconcile evidence, and deliver evidence-status-aware findings.

Read [HARNESS.md](HARNESS.md) now and run its loop. Read [WORKERS.md](WORKERS.md) only when selecting, invoking, debugging, or resuming workers. Read [SCENARIOS.md](SCENARIOS.md) only when calibrating behavior or validating the skill.

## 60-Second Execution Checklist

Use this before spending. It is a memory aid, not a replacement for [HARNESS.md](HARNESS.md).

1. Infer the research target from context; ask framing questions only if ambiguity would change the answer or plan.
2. Ask and record the three-axis contract: depth x independence x strictness. This is mandatory on every `/deep`.
3. Create Research State for `medium+` or any multi-action run.
4. Compose tools freely; choose the cheapest action that reduces the weakest load-bearing uncertainty.
5. Reconcile claims into `corroborated`, `single-source`, `disputed`, or another HARNESS status.
6. Spot-check load-bearing claims before delivery.
7. Deliver a handoff artifact with evidence status, verification checks, spend, artifacts, and next inspection points.

## Binding Map

| Harness primitive | Claude Code binding |
|---|---|
| ask the user | `AskUserQuestion` with concrete options and cost/tradeoff descriptions |
| run a worker | Bash: `"$PY" ~/.claude/skills/deep/scripts/deep_research.py --provider <p> "QUERY"` |
| `$PY` | project venv if present (`.venv/Scripts/python.exe` on Windows, `.venv/bin/python` on POSIX), else `python3` |
| async worker | same Bash call with background execution; keep the resume token printed to stderr |
| parallel batch | independent Bash calls in one message |
| parallel deep wave | `--submit-only` each engine in one message, do cheap verification while they run, then `--resume` each token |
| isolated blind check | spawn a fresh subagent (Agent tool) whose prompt contains only the claim verbatim — it must not receive or read the state file, the evidence pool, or the current hypothesis |
| host search/fetch | `WebSearch` / `WebFetch` |
| Research State | write/edit `reports/deep_state_<yyyymmdd>_<slug>.md` in the cwd |
| ledger | pass `--ledger reports/deep_state_<slug>.ledger.jsonl` from `medium` depth up |
| artifact gate | before delivery from `medium` up: `"$PY" ~/.claude/skills/deep/scripts/validate_state.py <state> --ledger <ledger>`; fix FAILs, report WARNs honestly in delivery |
| language | respond in the user's language; write worker queries in English (plus one native-language probe when the topic is region-bound) |

## Operational Notes

- Missing key: name the env var (`PERPLEXITY_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`; `S2_API_KEY` optional) and both `.env` locations.
- Framing: infer the research target from context; ask clarifiers only when a missing premise changes scope, worker choice, cost, or answer.
- Mandatory contract: ask one card every `/deep`. Recommend `fast`, `standard`, or `decision`, and spell out the three axis values in each option. Include the estimated spend range and the intended first wave in each option — the user pulls the trigger with the price and the plan visible. Let `Other` set the axes individually.
- Harvest before you buy: at INSPECT, if `reports/*.ledger.jsonl` exists, run `--list-pending` and `--resume` any pending token before new spend. `doctor.py` also surfaces these.
- Reuse before you buy: `reports/` accumulates paid artifacts; `ls -t reports/deep_*.md` plus a topic grep before re-purchasing research that may already exist.
- Privacy pause: before using `deepseek --files` or any external worker on local/user files, confirm the files are safe to send or redact/summarize first.
- Async polling caps: Perplexity 20 min, OpenAI 45 min, Gemini 30 min (`--timeout-min` overrides). On timeout, recover with `--resume`; never re-pay while a resume token exists.
