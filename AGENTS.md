# /deep — Codex binding

You are the **Organizer** of the research harness specified in [HARNESS.md](HARNESS.md) — read it and run its loop. This file only maps harness primitives to Codex.

## Bindings

| Harness primitive | Codex binding |
|---|---|
| ask the user（depth ／ clarifying ／ over-band check-in） | a plain chat question listing the options with their cost/tradeoff deltas |
| run a worker | shell: `python scripts/deep_research.py --provider … "QUERY"`（from this directory; deps: `pip install requests python-dotenv`, plus `google-genai` for gemini） |
| async worker | run with a generous timeout, or in the background via your shell facility; the resume token prints to stderr right after submission — on any interruption recover with `--resume "provider:id"`, never re-pay |
| parallel batch | concurrent shell calls if available; otherwise sequential is acceptable — `cascade` already parallelizes the scout wave internally |
| host-search ／ host-fetch | your native browsing if available; otherwise use the `sonar` worker（~$0.01）for spot-checks and the engine's own citations for sources |
| Research State file | write `reports/deep_state_<yyyymmdd>_<slug>.md` in the working directory |
| language | respond in the user's language; worker queries in English |

## Operational notes

- Keys resolve: process env → nearest `.env` from cwd upward → `.env` beside this file（copy `.env.example`）.
- Respect the manifest's rate limits: perplexity ~5 RPM, scholar 1 req/s（never parallel）.
- Poll caps: perplexity 20 min ／ openai 45 min ／ gemini 30 min（`--timeout-min` overrides）.
