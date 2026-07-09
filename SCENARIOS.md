# /deep Scenario Calibration

Read this when validating the skill, tuning behavior, or when the Organizer is unsure how strict a `/deep` run should be. These are behavior calibrations, not pipelines.

## Expected Postures

| Scenario | Expected Organizer posture |
|---|---|
| `/deep quick fact check` | Infer framing, ask the three-axis contract, recommend `fast`, use one narrow source or lookup if confirmed, deliver with evidence status. |
| `/deep` after a long conversation | Infer the research target from the conversation; ask framing questions only if multiple targets are plausible; still ask the three-axis contract. |
| `/deep literature review` | Recommend at least `standard`, include `scholar`, keep paper claims separate from model summaries, avoid over-trusting citation counts. |
| `/deep decision-critical research` | Recommend `decision`, require cross-family evidence and at least one blind isolated verification pass for load-bearing claims. |
| `/deep market or product research` | Mix current web evidence with source-of-record checks; prices, policies, and availability need fresh verification. |
| `/deep with missing API keys` | Name missing keys, use available host-native tools or free workers, record substitutions in state/log. |
| `/deep local files plus web context` | Pause before sending local files externally; prefer host-side extraction unless the user approves egress. |
| Conflicting sources | Promote the claim to `disputed`, state what would settle it, and spend only if the dispute is load-bearing. |
| Host session crashed mid-`/deep` | Run `--list-pending`, harvest pending tokens with `--resume`, reconcile the ledger, then continue under the same contract — never re-submit paid work. |

## Mini State Example

```md
# Research State: Should we adopt Tool X for regulated customer support?
contract: depth=medium | independence=two-source | strictness=gaps | status=running | started=2026-07-09T10:00:00
framing: evaluate fit for regulated support teams; exclude general marketing claims
current hypothesis: promising for triage, unresolved on audit logging and data retention
next cheapest action: verify audit-log claims against official docs and one customer/security review

## Spend
running total: $0.11
| # | action | worker | actual$ | artifact |
| 1 | orientation | cascade | $0.11 | reports/deep_..._tool_x.md |

## Load-Bearing Claims
| id | claim | why it matters | status | next check |
| C1 | Tool X supports immutable audit logs | compliance blocker | single-source | fetch official security docs |
| C2 | Tool X stores data in-region | procurement blocker | disputed | compare official docs and DPA |

## Evidence Pool
| id | claim | status | sources | independence |
| E1 | audit logs available on enterprise plan | single-source | cascade -> report path | Perplexity |

## Open
gaps: pricing tier, retention period, export format
disputes: C2 needs official DPA or support statement

## Log
- 1: chose cascade because the question needed broad orientation before targeted verification
```

## Evaluation Prompts

Use these to forward-test whether the skill activates the right behavior without leaking expected answers.

For complete expected-session examples, see [examples/transcripts](examples/transcripts). Validate them with:

```bash
python scripts/validate_transcripts.py
```

```text
/deep Compare whether SQLite or DuckDB is the better default for local analytics in a Python desktop app.
```

Pass condition: asks the three-axis contract, recommends a reasonable preset, uses current/contextual evidence if spending proceeds, and separates recommendation from evidence.

```text
/deep
```

Pass condition: infers the likely research target from the conversation if available; asks a framing question only if target ambiguity matters; still asks the mandatory contract.

```text
/deep Is this vendor safe enough for a healthcare workflow?
```

Pass condition: recommends `decision`, requires cross-family or source-of-record evidence for compliance/security claims, marks unresolved claims explicitly.

## Anti-Patterns

- Starting worker calls before the three-axis contract is confirmed.
- Treating `cascade` or a deep report as the verdict.
- Running one worker at a time when independent checks can be batched.
- Chasing every interesting question instead of load-bearing uncertainty.
- Hiding missing keys, weak citations, or verification failures.
- Sending local/user files to external workers without a privacy pause.
- Re-submitting a paid async job while the ledger holds an unharvested resume token.
- Treating unanimous cross-engine agreement as independence without checking for a shared upstream source.
- Handing the blind-check agent the state file or current hypothesis — that is not blind.
