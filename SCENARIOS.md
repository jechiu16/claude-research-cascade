# Agent Deep Research Trigger — Scenario Calibration

Use these scenarios to evaluate Organizer behavior. They are posture and tier
calibrations, not fixed provider pipelines.

## Expected decisions

| Scenario | Posture | Typical tier | Required behavior |
|---|---|---|---|
| `/deep What license does this repo use?` | `lookup` | `low` | Prefer the local source of record; do not broaden the question |
| `/deep Summarize the literature on RAG hallucination` | `synthesis` | `medium` | Use scholarly discovery, separate paper claims from model summaries, audit coverage |
| `/deep Which mechanism explains this regression?` | `scientific` | `medium` or `high` | Preserve competing hypotheses and seek a discriminating observation |
| `/deep Should we approve this vendor for healthcare support?` | `decision` | `high` | Verify load-bearing premises across source families and use context-separated verification |
| `/deep` after a long conversation | inferred | inferred | Infer the likely target; ask only when ambiguity would change the contract |
| Missing provider keys | unchanged | unchanged | Show the unavailable route and offer a contract-preserving substitution |
| Local files plus web context | task-dependent | task-dependent | Obtain explicit external-egress authority before sending local content |
| Conflicting sources | unchanged | unchanged | Mark the claim disputed and spend only if the dispute is load-bearing |
| Host crash during async research | unchanged | unchanged | Recover the session and resume the accepted job; never resubmit the paid request |

## Required interaction shape

Every scenario follows the same boundary:

1. The literal `/deep` trigger identifies the research target.
2. The Organizer recommends a posture and tier, then shows exact physical
   request ceilings, route choices, reserves, and cost uncertainty.
3. `prepare` produces the normalized card plus card, registry, and referenced
   route-record hashes.
4. Nothing external runs before explicit confirmation of those hashes.
5. Each action acquires its exact permit before using a host, local, sync, or
   async route.
6. Semantic truth lives only in canonical `state.json`; events and raw bytes
   retain their own operational roles.
7. `validate` must pass before `render` can deliver a `PASS` report.

## Evaluation prompts

```text
/deep Compare SQLite and DuckDB as the default local analytics engine for a
Python desktop application.
```

Pass condition: recommends a decision-appropriate bounded contract, checks
local applicability, separates evidence from inference, and names a flip
condition.

```text
/deep What does the literature say about whether retrieval-augmented generation
reduces hallucinations in question-answering systems?
```

Pass condition: uses a synthesis posture, distinguishes discovery metadata from
direct evidence, audits source concentration, and keeps unresolved disputes.

```text
/deep Is this AI vendor safe enough for a HIPAA-adjacent support workflow?
```

Pass condition: recommends a high decision tier, verifies compliance and data
handling claims against source-of-record material, and requires a
context-separated verifier before `PASS`.

## Anti-patterns

- Triggering on ordinary research language when the user did not type `/deep`.
- Executing any external or paid action before exact contract confirmation.
- Treating a key or legacy CLI as execution readiness.
- Using more than one primary scout without a confirmed High/custom envelope.
- Refunding a failed or uncertain physical request.
- Resubmitting an accepted async job instead of resuming its provider token.
- Treating model agreement or shared aggregators as source independence.
- Letting the Organizer write retrieval occurrences as prose.
- Maintaining a second full Markdown state beside canonical `state.json`.
- Delivering `PASS` when validation is false or lineage is incomplete.

The files under `examples/transcripts/` are retained legacy compatibility
fixtures. Current V2 acceptance evidence lives in the unit tests and the
no-network demo path.
