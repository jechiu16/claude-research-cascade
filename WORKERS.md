# Worker Reference

Read this when the Organizer needs to choose, invoke, debug, or resume workers. Workers are affordances, not pipeline stages. The Organizer owns judgment; tools only return evidence artifacts.

## CLI Contract

The bundled worker CLI is `scripts/deep_research.py`.

- Dependencies: stdlib only for `demo`; `requests` for network workers; `python-dotenv` for `.env` loading; `google-genai` for Gemini.
- One call is one action.
- Stdout is always one JSON object.
- Exit code signals success or failure.
- Success carries `report`, `report_path`, `usage`, `cost_estimate_usd`, and `wall_time_s`.
- Failure carries `error`; submitted-then-lost async work also carries `resume` as `provider:id`.
- Stderr is progress only, including `[deep] ...` lines and early resume tokens.
- Reports land in `<cwd>/reports/`.
- Keys resolve: process env -> nearest `.env` from cwd upward -> `.env` beside this file.
- If `--ledger reports/deep_state_<slug>.ledger.jsonl` is passed, the CLI appends event records (`submitted` / `completed` / `failed` / `interrupted`) with provider, cost, wall time, artifact path, and resume token when available.
- Async submissions are journaled at submission time (`event: submitted`), so a killed process never loses a paid resume token.
- `--submit-only` submits an async job (perplexity/openai/gemini), prints `{submitted, resume}`, and exits — fire several engines in one wave, then harvest each with `--resume`.
- `--list-pending` scans ledgers for submitted-but-unharvested async jobs and prints their resume tokens; free, no network.
- If extraction of a completed job fails (provider schema drift), the raw payload is saved to `reports/deep_raw_*.json` before the error is raised — paid content is never dropped, and `--resume` re-harvests after a fix at no extra cost.
- Ctrl-C / SIGINT during a poll still emits `{"error": "interrupted", "resume": token}` and journals the event.
- `sonar` retries transient transport/429/5xx failures (the duplicate-billing risk is about a cent); deep-engine submit POSTs never auto-retry — a duplicate submission is a duplicate full charge.

Example commands use bare `python` for clarity. Host bindings decide the actual interpreter and absolute path.

## Affordance Catalog

| Worker | Invocation core | Cost / latency | Output | Index family | Notes |
|---|---|---|---|---|---|
| `demo` | `--provider demo` | free / instant | local smoke-test report | none | validates JSON/report/ledger contract; never evidence |
| `cascade` | `--provider cascade` | about $0.10-0.15 / about 30 s | four merged probes: direct, counter, landscape, falsifier | Perplexity | strong orientation move; raises if all probes fail |
| `sonar` | `--provider sonar` | about $0.01 / about 3 s | one grounded cited answer | Perplexity | targeted lookup, dispute adjudication, verification floor |
| `scholar` | `--provider scholar --effort minimal..high` | free / about 5 s | 5-50 papers with TLDRs, citation counts, PDFs | Semantic Scholar | keyword queries, not questions; 1 req/s; never parallel |
| `perplexity` | `--provider perplexity --effort medium/high` | about $0.5-8 / 2-20 min | long cited report | Perplexity | async + resume; about 5 RPM; `minimal` is ungrounded and should not be used for real research |
| `openai` | `--provider openai --effort medium/high` | about $0.4-8 / 5-25 min | long cited report | OpenAI | `high` uses o3, otherwise o4-mini with tool caps; async + resume; verified org required |
| `gemini` | `--provider gemini` | varies / 3-30 min | long report with inline sources | Google | async + resume |
| `deepseek` | `--provider deepseek --files a.md --files b.md "instruction"` | about free / 1-3 min | processed artifact | none | processor only; never retrieval; may hallucinate without supplied material |
| host search | host-native browsing | usually free | search results | host-dependent | spot-checks, source discovery |
| host fetch | host-native URL fetch | usually free | page content | authoritative page | source-of-record reads |

## Selection Heuristics

- Choose the cheapest action that can reduce the weakest load-bearing uncertainty.
- Compose tools freely; do not follow a fixed ladder.
- Use `cascade` when the question needs fast orientation from multiple angles.
- Use `scholar` when the answer depends on papers, methods, citation trails, or academic consensus.
- Use `sonar` or host search/fetch for narrow facts, source-of-record checks, and verification-floor spot checks.
- Use deep engines only when cheap evidence cannot satisfy the contract's independence or strictness bar.
- Use `deepseek` only to process already-fetched material; never treat it as a retrieval source.
- High cross-engine agreement is not automatically independence: engines crawl the same web. On recent or contested topics, check whether the agreeing sources share one upstream origin.
- If the topic is region- or language-bound, send at least one probe in that language; English-only queries systematically miss local sources.

## Parallelism

Batch independent actions when they can safely run together.

Good parallel waves:

- `cascade` plus one `scholar` keyword query when broad orientation and literature context are both useful.
- several `sonar` probes for unrelated gaps, within provider limits.
- one deep engine plus targeted host/sonar verification work.
- a `decision` wave: `--submit-only` two or three deep engines from different index families in one batch, verify cheap claims while they run, then harvest each token with `--resume`.

Do not parallelize:

- Semantic Scholar calls; keep to 1 request per second.
- dependent actions whose queries should be shaped by the previous result.
- retries that may duplicate paid async submissions.

## Failure And Recovery

| Situation | Organizer move |
|---|---|
| Missing key | Name the missing env var, use available workers or host search/fetch, and record the substitution. |
| Worker fails before submission | Record the failure, fall back to a host-native equivalent or another worker, and write `reports/host_fallback_<slug>.md`. |
| Paid async job times out or poll dies | Resume with `--resume "provider:id"`; never re-submit paid work while a resume token exists. |
| Host session died mid-run | Run `--list-pending` (also shown by `doctor.py`); harvest every pending token with `--resume` before paying for anything new. |
| Extraction failed on a completed job | The raw payload is already in `reports/deep_raw_*.json`; read it directly or `--resume` after fixing — the money is not lost. |
| Citations are missing or weak | Mark the claim `single-source` or `unverified`; do not launder model prose into evidence. |
| Sources conflict | Mark the item `disputed`, write what evidence would settle it, and spend only if it is load-bearing. |
| Host-native retrieval satisfies the contract | Use it; evidence quality beats tool loyalty. Note the substitution in state/log. |

## Privacy

`deepseek --files` and any external worker receiving local files sends file contents outside the host. Before using it on user/local files, confirm the files are safe to send, or redact/summarize first. If privacy is unclear, use host-side reading and Organizer extraction instead.

## Command Examples

```bash
python scripts/doctor.py
python scripts/deep_research.py --provider demo --ledger reports/deep_state_demo.ledger.jsonl "smoke test"
python scripts/deep_research.py --provider sonar "quick question"
python scripts/deep_research.py --provider cascade "scout this research question"
python scripts/deep_research.py --provider scholar "dynamic factor model nowcasting"
python scripts/deep_research.py --provider perplexity --effort high "decision-critical question"
python scripts/deep_research.py --provider openai --effort high "cross-check this claim"
python scripts/deep_research.py --provider deepseek --files a.md --files b.md "merge into a claims table"
python scripts/deep_research.py --resume "openai:resp_abc123"
```
