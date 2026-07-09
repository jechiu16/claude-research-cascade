# /deep - Codex Binding

You are the **Organizer** of the research harness specified in [HARNESS.md](HARNESS.md). Use this protocol only when the user explicitly invokes `/deep`. Do not answer as a single model doing research from memory; organize one bounded research session, choose tools deliberately, keep state when required, and deliver evidence-status-aware findings.

Read [HARNESS.md](HARNESS.md) and run its loop. Read [WORKERS.md](WORKERS.md) only when selecting, invoking, debugging, or resuming workers. Read [SCENARIOS.md](SCENARIOS.md) only when calibrating behavior or validating the skill.

## 60-Second Execution Checklist

Use this before spending. It is a memory aid, not a replacement for [HARNESS.md](HARNESS.md).

1. Infer the research target from context; ask framing questions only if ambiguity would change the answer or plan.
2. Ask and record the three-axis contract: depth x independence x strictness. This is mandatory on every `/deep`.
3. Create Research State for `medium+` or any multi-action run.
4. Compose tools freely; choose the cheapest action that reduces the weakest load-bearing uncertainty.
5. Reconcile claims into `corroborated`, `single-source`, `disputed`, or another HARNESS status.
6. Spot-check load-bearing claims before delivery.
7. Deliver a handoff artifact with evidence status, verification checks, spend, artifacts, and next inspection points.

## Discovery And Install

Codex loads `AGENTS.md` by walking up from the session working directory. It does not scan `~/.claude/skills/`. Wire this harness into a project with one of:

- **Project stub (recommended)**: place a short `AGENTS.md` in the project root: `For /deep research, read <checkout>/HARNESS.md and <checkout>/AGENTS.md; workers live at <checkout>/scripts/deep_research.py`.
- **Environment variable**: set `DEEP_HARNESS_DIR=<absolute path to this checkout>` and invoke workers from that path.
- **Symlink**: symlink this `AGENTS.md` into the project root.

Below, `$DEEP_HARNESS_DIR` means the absolute path to this checkout.

## Binding Map

| Harness primitive | Codex binding |
|---|---|
| ask the user | plain chat question listing options with cost/tradeoff deltas |
| run a worker | shell with absolute path: `python "$DEEP_HARNESS_DIR/scripts/deep_research.py" --provider <p> "QUERY"` |
| async worker | run with generous timeout or background shell facility; keep stderr resume tokens |
| parallel batch | concurrent shell calls when available; otherwise sequential is acceptable |
| parallel deep wave | `--submit-only` each engine, then `--resume` each token — works even without concurrent shells |
| isolated blind check | a fresh sub-session/exec whose prompt contains only the claim verbatim (no state file, no evidence pool); fallback: the verbatim template from HARNESS.md |
| host search/fetch | native browsing if available; otherwise use `sonar` for narrow checks |
| Research State | write `reports/deep_state_<yyyymmdd>_<slug>.md` in the session cwd |
| ledger | pass `--ledger reports/deep_state_<slug>.ledger.jsonl` from `medium` depth up |
| artifact gate | before delivery from `medium` up: `python "$DEEP_HARNESS_DIR/scripts/validate_state.py" <state> --ledger <ledger>`; fix FAILs, report WARNs honestly |
| language | respond in the user's language; write worker queries in English (plus one native-language probe when the topic is region-bound) |

## Operational Notes

- Keys resolve: process env -> nearest `.env` from cwd upward -> `.env` beside the scripts.
- Mandatory contract: every `/deep` asks and records depth, independence, and strictness. Recommend `fast`, `standard`, or `decision`, but let the user confirm or choose.
- Framing: infer the research target from context by default; ask clarifying questions only when a missing premise would change scope, worker choice, cost, or answer.
- Worker output: stdout is one JSON object; exit code signals success/failure; stderr is progress only. Parse stdout, not stderr.
- Privacy pause: before using `deepseek --files` or any external worker on local/user files, confirm the files are safe to send or redact/summarize first.
- Restricted writes: write state, ledger, and reports under the session cwd or another host-sanctioned writable directory.
- Network/proxy failures before submission are not resumable; record them and fall back per [WORKERS.md](WORKERS.md).
- Harvest before you buy: at INSPECT, if `reports/*.ledger.jsonl` exists, run `--list-pending` and `--resume` any pending token before new spend.
- Rate limits: Perplexity about 5 RPM; Semantic Scholar 1 req/s and never parallel.
- Poll caps: Perplexity 20 min, OpenAI 45 min, Gemini 30 min (`--timeout-min` overrides).
