# /deep Organizer Harness

**Host-neutral runtime spine.** Claude Code uses [SKILL.md](SKILL.md); Codex uses [AGENTS.md](AGENTS.md). Worker details live in [WORKERS.md](WORKERS.md). Calibration examples live in [SCENARIOS.md](SCENARIOS.md).

## What This Is

`/deep` is not a research engine. It is an explicit trigger that wakes the host agent into an **Organizer** role for one bounded research session.

The Organizer's job is to frame the question, set the research contract, choose tools, maintain state, reconcile claims, verify load-bearing evidence, and deliver a handoff-ready answer.

The objective is **maximum information gain per dollar across the available tool portfolio**. The steering question is always:

> Which load-bearing claim is weakest right now, and what is the cheapest action that strengthens it?

## Non-Negotiables

- Trigger only on explicit `/deep`; ordinary research requests do not activate this protocol.
- Infer the research target from context by default; ask framing questions only when ambiguity would change scope, cost, worker choice, or answer.
- Always ask and record the three-axis research contract before worker spend.
- Keep Research State for `medium+` depth or any multi-action run.
- Treat worker reports as evidence inputs, not final truth.
- Reconcile claims into evidence statuses before delivery.
- Spot-check the most load-bearing claims before delivery.
- Include spend and artifact paths in the final answer.

## 60-Second Execution Checklist

1. Frame the question from context; ask only scope-changing clarifiers.
2. Ask and record the contract: depth x independence x strictness.
3. Create Research State if `medium+` or more than one action is likely.
4. Choose the first batch by weakest load-bearing uncertainty, not by a fixed tool order.
5. Execute parallel-safe actions together; respect rate limits.
6. Normalize and reconcile claims; mark disputed or single-source items honestly.
7. Verify load-bearing claims, then deliver answer, spend, artifacts, and handoff notes.

## Research Contract

One card, three axes. The Organizer may recommend a preset, but the user must confirm or choose the axes before worker spend.

| Axis | Options |
|---|---|
| **Depth** | `shallow`: one probe wave or quick answer; `medium`: probes plus one or two standard reports; `deep`: multiple engines and iteration |
| **Independence** | `single`: one adequate source; `two-source`: load-bearing claims need two sources; `cross-family-blind`: two index families plus one blind isolated pass |
| **Strictness** | `first`: stop at first satisfactory answer; `gaps`: close obvious gaps; `chase`: pursue disputes until resolved or clearly unresolvable |

Preset shortcuts: `fast` = shallow x single x first; `standard` = medium x two-source x gaps; `decision` = deep x cross-family-blind x chase.

Explicit user budgets override the depth preset's spending spirit, but prices are indicative only. No code enforces a hard budget ceiling.

## Research State

Research State is the Organizer's external working memory for this one trigger. Create `reports/deep_state_<yyyymmdd>_<slug>.md` from `medium` depth up, or whenever more than one action runs. Rewrite it after every reconcile step.

Use this compact shape:

```md
# Research State: <question>
contract: depth=<...> | independence=<...> | strictness=<...> | status=running | started=<ts>
framing: <core question, exclusions, success criteria>
hypothesis: <best answer so far; provisional until verified>
next action: <one sentence: cheapest uncertainty reducer>
spend: running total $X.XX; ledger=<path>
claims: <id | claim | why it matters | status | next check>
evidence: <id | claim | status | sources | independence | as-of>
open: gaps=<...>; disputes=<...>
log: <n>: chose <batch> because <one line>
```

Statuses: `corroborated`, `single-source`, `corroborated-same-family`, `disputed`, `retired`, `unverified`.

`as-of` is the evidence vintage: publication or retrieval date. Date-sensitive claims (prices, policies, versions, availability) must carry it; a stale source does not clear the bar on a volatile topic.

## Organizer Loop

**0 INIT** - Infer the target from conversation context. Ask up to three clarifying questions only if the answer would change the plan. Ask the three-axis contract every time and record it.

**1 INSPECT** - Read the state and recent `reports/` artifacts on overlapping topics. Reuse old paid reports only if their age and scope still fit the question. If a ledger exists, check for unharvested async submissions (`--list-pending`) and harvest them before paying for anything new.

**2 CHOOSE** - Pick the next batch with the best expected information gain per dollar. Use free reasoning over the current pool first, targeted lookups next, broad paid retrieval last. Read [WORKERS.md](WORKERS.md) when selecting or invoking workers.

Branch types:

- **shared**: builds on the current evidence pool.
- **isolated**: blind verification. Prefer architectural isolation when the host supports it: a fresh-context agent that receives only the claim verbatim — no state file, no evidence pool, no current hypothesis. Fallback where fresh contexts are unavailable: the query template `Verify or refute: <claim verbatim>. What is the primary evidence for and against?`
- **targeted**: narrow lookup for a specific gap or dispute.

**3 EXECUTE** - Run parallel-safe actions in one wave. Avoid micro-looping one worker at a time. Keep resume tokens. If the first wave gives a useful provisional answer, share it as provisional while deeper actions continue.

**4 NORMALIZE** - Extract verdict-relevant claims from each artifact with provenance. Use a processor only for already-fetched material; curate its output.

**5 RECONCILE** - Compare claims across sources. Same-family agreement does not clear a cross-family independence bar. Unanimous cross-engine agreement on a recent or contested topic is itself a signal: engines crawl the same web, so check whether the agreeing sources trace to one upstream origin before counting them as independent. Promote conflicts to `disputed` and write what would settle them. Update the state.

**6 TERMINATE?** - Stop when load-bearing claims meet the contract, or when marginal gain is clearly below marginal cost, or when further spend exceeds the contract without a strong reason. If justified overspend would be large, check in with the user. At `decision` strictness, weigh marginal spend against the cost of a wrong recommendation, not against dollars already spent — frugality is the default posture, not the point of a decision run.

## Verification Floor

Before delivery, independently spot-check the two or three most load-bearing claims: headline numbers, dates, official limits, or claims that would change the recommendation if wrong. Prefer host search/fetch when available; otherwise use a narrow worker probe. If verification is unavailable, say so plainly.

For `decision` runs, add one adversarial pass in a fresh context: `Argue that this recommendation is wrong: <recommendation + key evidence>`. The Organizer that formed the hypothesis should not be its only judge; a surviving recommendation is stronger, a broken one just saved the user from it.

## Delivery

Deliver in the user's language, optimized for a future Agent or Claude/Codex session to continue from it.

Include:

- executive answer
- research contract and framing assumptions
- key findings with evidence status
- load-bearing claims and what would change the conclusion
- verification checks and any changes they caused
- unresolved disputes and residual uncertainty
- spend, ledger, state file, and report paths
- recommendation, separated from evidence
- handoff block: what to inspect next

## Boundary Rules

- **Organizer judgment**: framing, contract, branch choice, reconciliation, verification, stop condition.
- **Host responsibility**: interpreter choice, writable artifact path, user questions, background execution, preserving resume tokens.
- **Worker guarantees**: see [WORKERS.md](WORKERS.md) for stdout JSON, exit codes, ledger behavior, reports, resume, and rate limits.
- **Privacy pause**: before sending local/user files to external workers, confirm they are safe to send or redact/summarize first.
- **Failure honesty**: missing keys, weak citations, transport failures, and conflicts are state facts, not annoyances to hide.
