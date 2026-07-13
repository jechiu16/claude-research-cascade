# Agent Deep Research Trigger — V2 Organizer Harness

> `SKILL.md` is the sole default and human protocol. This file is the
> Medium/High runtime bridge and implementation/recovery reference; it is read
> only after the user selects Medium or High.

This is a host-neutral implementation reference. Claude Code and Codex use the
sole protocol in [SKILL.md](SKILL.md); [AGENTS.md](AGENTS.md) only provides the
thin host binding. Low never reads or invokes this runtime. The design rationale
lives under `docs/superpowers/specs/`.

## Purpose

`/deep` is an explicit trigger for one bounded research session. The selected host model is always the **Organizer**. It frames the problem, chooses checks, reconciles evidence, judges inference quality, and turns the result into a development handoff. Workers may supply evidence or independent analysis; they never own the final verdict.

The runtime improves reliability by making unsupported success mechanically difficult. It does not guarantee truth or complete unknown-unknown discovery. A run ends as `PASS`, `PARTIAL`, or `BLOCKED`.

## Current Boundary

The runtime enables host-native retrieval, local inspection, Organizer passes, deterministic no-network test routes, and the external routes the resolved provider registry marks enabled and v2-bound. The registry is the sole source of truth; inspect it with `providers --json`. Exa is an independent-index anti-lock-in or verification route; Brave is the recommended general scout. Every other external network worker and processor route is **disabled** in `provider_registry.json` until its adapter:

1. uses the common v2 request boundary for every outbound request;
2. has deterministic request, error, recovery, provenance, and storage-rights fixtures;
3. has a named adoption status and evidence budget.

A present credential is not execution readiness. No disabled route may be exercised through any side channel. No new provider key should be requested before its adapter fixtures and benchmark budget exist.

## Non-Negotiables

- Activate only on explicit `/deep`.
- The user selects one tier after seeing the kernel-free seven-line card.
- Choose exactly one primary scout route.
- Boundary actions derive and reserve their exact request atomically; uncertain attempts remain consumed.
- Keep one semantic source of truth: canonical `state.json`.
- Treat model or retrieval agreement as discovery signal, not source-origin independence.
- Preserve exact raw evidence and offsets for load-bearing claims.
- Never let deterministic demo output support a canonical claim.
- Validate before `PASS`; render HTML only as a deterministic projection.
- Prefer a safe `PARTIAL` or `BLOCKED` over an unsupported conclusion, but do not use abstention to avoid a reachable answer.

## Public Protocol

`SKILL.md` is the sole public protocol. This internal reference records the
implementation and recovery boundary; it does not define another user flow.

1. The user types the literal `/deep`.
2. The Organizer shows the kernel-free seven-line card defined by `SKILL.md`.
3. The user chooses exactly one tier: `Low`, `Medium`, or `High`.
4. `Adjust` revises the scope and shows a new card; it does not start research.
5. The tier choice is the only confirmation for that run.

## Runtime Bridge

After Medium or High selection, the host reads this `HARNESS.md` beside the
canonical `SKILL.md` and uses the repo-local CLI. `ROOT` is the absolute
directory containing that canonical `SKILL.md`; `CLI` is always:

```bash
ROOT="/absolute/path/to/the/canonical-skill"
CLI="$ROOT/.venv/bin/deep-research-state"
SESSION="/absolute/path/to/this-run-package"
```

Every bridge command below works from any current working directory and uses
`$CLI`:

```bash
"$CLI" init "$SESSION" --contract "/absolute/path/to/confirmed-contract.json" --json
"$CLI" host-capture "$SESSION" --payload "/absolute/path/to/capture-file" \
  --artifact-id HC1 --source-url '<url>' --source-title '<title>' \
  --upstream-key '<upstream>' --fidelity host_rendered \
  --marginal-purpose '<named marginal purpose>' --json
"$CLI" patch "$SESSION" --patch "/absolute/path/to/state-patch.json" --json
"$CLI" validate "$SESSION" --json
"$CLI" render "$SESSION" --json
```

The host may patch canonical state between `host-capture` and `validate` when
needed. The bridge flow is therefore `init -> host-capture -> patch as needed
-> validate -> render`. A patch must at minimum link source/evidence/claim and
fill summary decision/terminal status plus engineering_handoff
constraints/safe_actions/acceptance_tests. Each acceptance-test string MUST use
`檢查方式 => 預期結果`, with non-empty text on both sides; this adds no schema.
Set status before `validate` for PASS; the final package must not retain
`IN_PROGRESS`.

The Medium/High canonical terminal, handoff, and completeness gates apply
equally to `host_native` and `external_managed` execution.

Fail closed with the matching reason: an evidence-floor gap sets canonical
`summary.status=BLOCKED`, `summary.human_status=證據不足`, and
`tier_contract_met=false`, with HTML `BLOCKED / EVIDENCE_INSUFFICIENT`; a
terminal/handoff/completeness gap sets canonical `summary.status=BLOCKED` and
`summary.human_status=交付不完整`, with HTML `BLOCKED / DELIVERY_INCOMPLETE`.

`host-capture` proves persisted exact bytes and internal consistency of
caller/host-attested metadata only. It does not prove that the payload came
from the declared URL or is a host observation.

Do not use `command -v`, a global CLI, or a user-facing bridge step. Low stops
before this section.

## Internal Binding

After tier selection, the Organizer internally derives and binds the canonical
contract. It may use `prepare`, `confirm`, and `init` as implementation details,
not as user steps or another confirmation. An external paid-request count or
local-data egress semantic change requires a new card and a new run, as defined
by `SKILL.md`.

`execution` is the Organizer/host home execution mode; `host_native` does not
exclude an optional external provider route already confirmed on the card.
Every repo-sent call still requires its stage-map entry and request boundary.

## Scientific Organizer Loop

### 1. Inspect

- Recover pending WAL or already-authorized purge work before new actions.
- Read current canonical state and overlapping retained artifacts.
- Identify the weakest load-bearing uncertainty, not the longest unanswered list.

### 2. Frame and Predict

- State scope, assumptions, exclusions, and decision boundary.
- For ambiguous work, record plausible alternatives without padding.
- Before a discriminating check, record expected observations and what each would update.
- Separate facts, observations, hypotheses, recommendation, and safe action.

### 3. Choose One Marginal Action

Use the lexicographic rule:

1. eliminate a load-bearing failure;
2. reduce a decision-relevant uncertainty;
3. add a genuinely new source origin or project observation;
4. minimize physical requests, admitted context, latency, and spend.

Do not run every cheap tool. Prefer direct source-of-record APIs for canonical facts, local inspection for project truth, and general discovery only when the target is not already known.

### 4. Execute, Reserve, Preserve

Boundary-managed requests build the actual request and reserve their exact
budget inside the execute command:

```bash
"$CLI" execute "$SESSION" \
  --action-id A1 --stage primary_scout --route openalex \
  --query '<question>' --now '<timestamp>' --json
```

Paid async requests use the same boundary-owned choreography; do not run a
separate paid `permit` command or provide a fingerprint:

```bash
"$CLI" deep-submit "$SESSION" \
  --action-id D1 --stage investigation --route perplexity \
  --query '<question>' --now '<timestamp>' --json

"$CLI" deep-poll "$SESSION" \
  --action-id D1 --poll-action-id T1 \
  --stage investigation --route perplexity \
  --now '<timestamp>' --json
```

One composite invocation reserves its full physical multiplicity atomically. A
failed or uncertain outbound attempt consumes the boundary action/request
count. Host, local, and organizer actions may still use the separate legacy
`permit` command, without a caller-supplied fingerprint.

Persist source or local bytes through typed ingestion. `artifact-add` accepts only `local_output`, `user_file`, or `fetched_source`. Provider and processor payloads require a bound adapter operation and cannot be relabelled through the generic CLI.

### 5. Reconcile

Patch only the affected canonical sections with the expected revision. Every load-bearing claim must trace through:

`claim -> evidence -> source + source_origin -> immutable raw artifact`

Use exact excerpts and byte offsets. Distinguish:

- source-origin independence;
- retrieval-index diversity;
- analyst-model diversity;
- context independence.

Only source origins establish empirical corroboration. One directly fetched T1 source (evidence with `source_tier: T1` whose source record has `direct_fetch: true`) may settle a source-of-record fact; one empirical study remains single-source.

### 6. Reinforce After a Candidate Appears

Medium/High scientific or decision runs perform:

- **anti-lock-in:** seek evidence that would overturn the provisional candidate. Disposition every anti-lock-in finding explicitly: refute it with evidence, absorb it by revising the candidate, or record it as an open tension with a revisit trigger. Merely noting counter-evidence does not count;
- **coverage audit:** inspect omitted premises, boundary conditions, and candidate omissions;
- **local applicability:** test project versions, environment, and constraints when feasible.

High MUST include a fresh, context-separated analyst pass over the exact claim packet. Its canonical verifier record minimally contains `verifier_actor != candidate_actor`, `packet_claim_ids`, a recomputable `packet_sha256`, `verdict` in `accept/revise/block`, `disposition`, `completed=true`, `context_separated=true`, and `produced_candidate=false`. This is host attestation plus canonical packet binding; it proves neither context nor source independence. A `host_native` verifier writes only the completed verifier record, with no permit or attempt event. An `external_managed` verifier additionally requires the existing completed organizer-pass action.

### 7. Terminate Honestly

Stop when the contract gates pass, when the next action has no material expected state delta, when quota is exhausted, or when the missing evidence is a user/vendor/local artifact that generic research cannot supply.

## Canonical Artifacts

Each session owns:

| Artifact | Role |
|---|---|
| `state.json` | Only canonical semantic state |
| `events.jsonl` | Hash-chained operational and revision journal |
| `raw/` | Immutable, hashed, policy-gated source and local bytes |
| `report.html` | Escaped deterministic projection bound to the state hash |

Do not persist a second full Markdown report. The host can read canonical JSON directly; humans use HTML.

When the user's working language is Traditional Chinese, author human-facing canonical narrative fields in Traditional Chinese before validation and rendering. Preserve exact evidence excerpts, source titles, identifiers, URLs, hashes, provider IDs, status tokens, and machine diagnostics in their original form. The deterministic renderer does not call a translation model.

Secret-classified data never enters raw storage. Local-sensitive artifacts require redaction review and never enter HTML. Provider payload retention and HTML inclusion must fit the session's immutable storage-rights snapshot.

Purge is a semantic transition: downgrade affected claims and verdict first, persist authorization, remove bytes, leave a tombstone, validate, and rerender. Recovery only resumes that persisted authorization.

## Gates

`PASS` requires:

- non-empty bounded decision and non-empty exact load-bearing claim set;
- confirmed evidence floor;
- passing claim status, source origin, entailing exact excerpt, available raw artifact, and applicability for every load-bearing claim;
- quota/event/state hash reconciliation;
- posture-specific checks (machine gates exist for lookup, scientific, and decision; synthesis shares the Medium/High coverage-audit gate but has no anti-lock-in requirement of its own);
- Medium/High anti-lock-in and coverage audit when required;
- context-separated High verifier;
- current HTML state hash when a report exists.

`PARTIAL` requires a named reversible safe action whose validity does not depend on unresolved or purged-evidence claims. Otherwise use `BLOCKED`.

Run:

```bash
"$CLI" validate "$SESSION" --json
"$CLI" render "$SESSION" --json
```

Never upgrade a verdict because HTML looks complete. Rendering an invalid state labels it `INVALID`.

## Development Handoff

The final chat and canonical state should make the next coding session cheaper. Include:

- bounded answer and decision scope;
- load-bearing claims, evidence status, dates, and flip conditions;
- assumptions that must remain reversible;
- safe next actions and prohibited hard dependencies;
- project constraints, proposed local experiments, and acceptance tests;
- disputes, research debt, quota use, and artifact paths;
- what new evidence should trigger a revisit.

## Recovery Commands

```bash
"$CLI" status "$SESSION" --json
"$CLI" recover "$SESSION" --json
"$CLI" artifact-purge "$SESSION" \
  --artifact-id A1 --reason "retention expired" \
  --requested-status BLOCKED --json
```

Unowned malformed event bytes, conflicting purge metadata, unexpected paths, or missing hashes fail closed. Recovery never invents a deletion target or a research action.

For an async submit or poll, the boundary reserves the request before sending
it. Therefore an attempted action with no recorded token is always
`consumed=true` and `pollable=false`: inspect the provider outcome manually and
never retry or resubmit that same action. It is not safe to invent a token or
call `deep-poll` without one.

An accepted or uncertain deep action with a recorded token is
`consumed=true` and `pollable=true`. Run `deep-pending` to confirm the token,
then use a **new** `deep-poll` action ID. Never retry the failed or uncertain
poll action itself. Raw provider bytes remain in `provider_spool/` when a
response was received; validate the session after recovery.
