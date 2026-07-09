---
name: deep
description: /deep — meta-research trigger. Wakes the host agent as Organizer of a bounded, stateful research harness over multi-provider workers (Perplexity, OpenAI, Gemini, Semantic Scholar, DeepSeek), from a $0.01 fact-check to a cross-validated investigation. Use when the user types /deep, or asks for deep research, a cited report, a literature review, or a cross-checked investigation of any topic.
---

# /deep — Claude Code binding

You are the **Organizer**. The full contract — workers manifest, Research State schema, loop, hooks, depth presets, verification floor — lives in [HARNESS.md](HARNESS.md), in this skill's directory. **Read it now and run its loop.** This file only maps harness primitives to Claude Code.

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
| language | respond in the user's language; worker queries in English |

## Operational notes

- Missing key → name the env var（`PERPLEXITY_API_KEY`／`OPENAI_API_KEY`／`GEMINI_API_KEY`／`DEEPSEEK_API_KEY`; `S2_API_KEY` optional）and both `.env` locations（project cwd ／ this skill's directory）.
- While async workers run, tell the user what's running and the expected time, and keep the conversation going.
- Depth selection: infer when obvious from the question's stakes; otherwise one AskUserQuestion with the four presets and their typical bands.
- Poll caps: perplexity 20 min ／ openai 45 min ／ gemini 30 min（`--timeout-min` overrides）; on timeout the error JSON carries `resume` — recover, never re-pay.
