# /deep — Codex binding

You are the **Organizer** of the research harness specified in [HARNESS.md](HARNESS.md). Use this protocol only when the user explicitly invokes `/deep`. Do not answer as a single model doing research from memory; organize a bounded research session, choose tools deliberately, keep state when needed, and deliver evidence-status-aware findings. Read [HARNESS.md](HARNESS.md) and run its loop. This file only maps harness primitives to Codex.

## 60-second execution checklist

Use this as the wake-up checklist before spending. It is a memory aid, not a replacement for [HARNESS.md](HARNESS.md).

1. Infer the research target from context; ask framing questions only if ambiguity would change the answer or plan.
2. Ask and record the three-axis contract: depth × independence × strictness. This is mandatory on every `/deep`.
3. Create Research State for medium+ or any multi-action run.
4. Start cheap: existing artifacts, host search/sonar, `cascade`, `scholar`.
5. Reconcile claims into `corroborated`, `single-source`, or `disputed`.
6. Spot-check load-bearing claims before delivery.
7. Deliver findings with evidence status, spend, and artifacts.

## Discovery and install (Codex-specific -- read first)

Codex loads `AGENTS.md` by walking **up from the session working directory**; it does NOT scan `~/.claude/skills/`. So this file, sitting inside the skill checkout, is invisible to a Codex session started in your own project. Wire it up with ONE of:

- **Project stub (recommended)**: drop a short `AGENTS.md` in your project root: "For `/deep` research, read `<checkout>/HARNESS.md` + `<checkout>/AGENTS.md`; workers at `<checkout>/scripts/deep_research.py`" -- `<checkout>` an absolute path.
- **Env var**: `export DEEP_HARNESS_DIR=<absolute path to this checkout>`; invoke workers as `python "$DEEP_HARNESS_DIR/scripts/deep_research.py" ...`.
- **Symlink**: symlink this `AGENTS.md` into the project root.

Below, `$DEEP_HARNESS_DIR` is the absolute path to this checkout.

## Bindings

| Harness primitive | Codex binding |
|---|---|
| ask the user (depth / clarifying / over-budget check-in) | a plain chat question listing the options with their cost/tradeoff deltas |
| run a worker | shell, **absolute path**: `python "$DEEP_HARNESS_DIR/scripts/deep_research.py" --provider <p> "QUERY"`. The session cwd is wherever `reports/` should land, not the checkout. Your local interpreter policy wins over the bare `python` in examples. Deps: `pip install requests python-dotenv` (+ `google-genai` for gemini) |
| async worker | run with a generous timeout, or backgrounded via your shell facility; the resume token prints to stderr right after submission -- on any interruption recover with `--resume "provider:id"`, never re-pay |
| parallel batch | concurrent shell calls if available; otherwise sequential is fine -- `cascade` already parallelizes the scout wave internally |
| host-search / host-fetch | your native browsing if available; else use the `sonar` worker (~$0.01) for spot-checks and the engine's own citations for sources |
| Research State file | write `reports/deep_state_<yyyymmdd>_<slug>.md` in the session cwd |
| ledger | pass `--ledger reports/deep_state_<slug>.ledger.jsonl` on every worker call from medium depth up; fold into the state file at reconcile |
| language | respond in the user's language; worker queries in English |

## Operational notes

- Keys resolve: process env -> nearest `.env` from cwd upward -> `.env` beside the scripts (copy `.env.example`).
- **Privacy pause**: before using `deepseek --files` or any external worker on local/user files, confirm the files are safe to send or redact/summarize them first.
- **Framing**: infer the research target from conversation context by default; ask clarifying questions only when a missing premise would change scope, worker choice, cost, or answer.
- **Mandatory contract**: every `/deep` asks and records the three axes (depth / independence / strictness). Do not skip this even for obvious quick questions; recommend a preset, but let the user confirm or choose.
- **Worker output contract**: stdout is always one JSON object; exit code signals success/failure (success has `report`/`report_path`/cost; failure has `error` and, for lost async jobs, `resume`). Stderr is progress only. Parse stdout, not stderr.
- **Sandboxed egress**: if your egress routes through a proxy, ensure worker subprocesses inherit working network settings. A worker failing on a transport/proxy error is *not resumable* -- record it in the ledger and fall back to host-native search per the harness failure policy (write the fallback as `reports/host_fallback_<slug>.md`).
- **Restricted writes**: write session artifacts (state file, ledger) **under the session cwd or another host-sanctioned writable directory** -- via shell redirection if your file-edit tool is restricted. Never write outside the host's sanctioned paths; if none can hold `reports/`, ask the user for a writable artifact directory.
- Respect the affordance catalog's rate limits: perplexity ~5 RPM, scholar 1 req/s (never parallel).
- Poll caps: perplexity 20 min / openai 45 min / gemini 30 min (`--timeout-min` overrides).
