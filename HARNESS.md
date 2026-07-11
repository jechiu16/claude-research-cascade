# /deep V2 Organizer Harness

This is the host-neutral executable protocol. Claude Code uses [SKILL.md](SKILL.md); Codex uses [AGENTS.md](AGENTS.md). The design rationale lives under `docs/superpowers/specs/`.

## Purpose

`/deep` is an explicit trigger for one bounded research session. The selected host model is always the **Organizer**. It frames the problem, chooses checks, reconciles evidence, judges inference quality, and turns the result into a development handoff. Workers may supply evidence or independent analysis; they never own the final verdict.

The runtime improves reliability by making unsupported success mechanically difficult. It does not guarantee truth or complete unknown-unknown discovery. A run ends as `PASS`, `PARTIAL`, or `BLOCKED`.

## Current Boundary

The foundation runtime enables host-native retrieval, local inspection, Organizer passes, and deterministic no-network test routes. Every external network worker and processor route is **disabled** in `provider_registry.json` until its adapter:

1. uses the common v2 request boundary for every outbound request;
2. has deterministic request, error, recovery, provenance, and storage-rights fixtures;
3. has a named adoption status and evidence budget.

Credential doctor readiness is not v2 execution readiness. Do not call the legacy worker CLI to bypass a disabled route. No new provider key should be requested before its adapter fixtures and benchmark budget exist.

## Non-Negotiables

- Activate only on explicit `/deep`.
- The user pulls the trigger after seeing the contract card and exact physical call counts.
- Choose exactly one primary scout route.
- Acquire an exact permit before every action; uncertain attempts remain consumed.
- Keep one semantic source of truth: canonical `state.json`.
- Treat model or retrieval agreement as discovery signal, not source-origin independence.
- Preserve exact raw evidence and offsets for load-bearing claims.
- Never let deterministic demo output support a canonical claim.
- Validate before `PASS`; render HTML only as a deterministic projection.
- Prefer a safe `PARTIAL` or `BLOCKED` over an unsupported conclusion, but do not use abstention to avoid a reachable answer.

## Contract Card

The contract has two scientific axes plus explicit resources.

### Posture

| Posture | Use when | Required spirit |
|---|---|---|
| `lookup` | A source of record defines a bounded fact | Fetch the defining primary source directly; avoid artificial hypotheses |
| `synthesis` | The task needs a landscape or literature map | Declare coverage dimensions, omissions, shared origins, and dates |
| `scientific` | Mechanisms are unclear or evidence conflicts | Write alternatives and expected observations before discriminating checks |
| `decision` | Research will drive architecture or costly action | Expose premises, weakest inference joints, reversibility, and cost of error |

### Tier

| Tier | Default intent | Reinforcement |
|---|---|---|
| `low` | Narrow, reversible, one-cycle answer | Targeted verification only when a load-bearing claim needs it |
| `medium` | Development-grade evidence with bounded challenge capacity | One reserved anti-lock-in or verification action when posture requires it |
| `high` | Difficult, ambiguous, or hard-to-reverse decision | Additional challenge capacity plus context-separated verifier |
| `custom` | User-selected exact envelope | Every stage, route, logical invocation, and physical request is explicit |

Tiers do not encode provider dollar prices. The contract controls **counts**: logical invocations, provider-declared physical multiplicity, and category ceilings. Display estimated cost ranges as uncertain information, never as an enforceable dollar cap.

The card also records:

- one `scout_route`;
- the exact `(stage, category, route)` permit map;
- reserved versus discovery capacity;
- external, host-context, and local resource envelopes;
- raw-storage ceiling and artifact policy;
- evidence floor;
- card, resolved-registry, and referenced-provider-record hashes.

## Trigger and Confirmation

1. Infer the target from conversation context. Ask only questions whose answers change scope, posture, tier, route, or cost.
2. Inspect secret-free capabilities:

```bash
"$PY" scripts/research_state.py providers --json
```

3. Draft the card and run:

```bash
"$PY" scripts/research_state.py prepare --contract draft.json --json
```

4. Show the user the recommended posture/tier, one scout route, physical counts by stage, reserved calls, host-context class, local/network boundaries, and estimated spend uncertainty. Wait for an explicit choice.
5. After the user confirms the displayed card, bind it and initialize:

```bash
"$PY" scripts/research_state.py confirm \
  --prepared prepared.json \
  --card-sha256 <displayed-card-hash> \
  --registry-sha256 <displayed-registry-hash> \
  --referenced-records-sha256 <displayed-route-records-hash> \
  --confirmed-at <timestamp> \
  --confirmed-by user \
  --json

"$PY" scripts/research_state.py init <session-dir> \
  --question "<research target>" \
  --contract confirmed.json \
  --json
```

Changing the card, registry, route meaning, or confirmation creates a new session. It is not an in-place patch.

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

### 4. Permit, Execute, Preserve

Acquire the exact permit before the action:

```bash
"$PY" scripts/research_state.py permit <session-dir> \
  --action-id A1 --stage primary_scout \
  --category host_retrieval --route host-web \
  --count 1 --fingerprint sha256:<request> --json
```

One composite invocation reserves its full physical multiplicity atomically. A failed or uncertain outbound attempt consumes the permit. Retry only with another predeclared permit.

Persist source or local bytes through typed ingestion. `artifact-add` accepts only `local_output`, `user_file`, or `fetched_source`. Provider and processor payloads require a bound adapter operation and cannot be relabelled through the generic CLI.

### 5. Reconcile

Patch only the affected canonical sections with the expected revision. Every load-bearing claim must trace through:

`claim -> evidence -> source + source_origin -> immutable raw artifact`

Use exact excerpts and byte offsets. Distinguish:

- source-origin independence;
- retrieval-index diversity;
- analyst-model diversity;
- context independence.

Only source origins establish empirical corroboration. One directly fetched T1 source may settle a source-of-record fact; one empirical study remains single-source.

### 6. Reinforce After a Candidate Appears

Medium/High scientific or decision runs perform:

- **anti-lock-in:** seek evidence that would overturn the provisional candidate;
- **coverage audit:** inspect omitted premises, boundary conditions, and candidate omissions;
- **local applicability:** test project versions, environment, and constraints when feasible.

High additionally requires a verifier with fresh context that receives the exact claim or argument packet, did not produce the candidate, and records `context_separated=true` and `produced_candidate=false`.

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

Secret-classified data never enters raw storage. Local-sensitive artifacts require redaction review and never enter HTML. Provider payload retention and HTML inclusion must fit the session's immutable storage-rights snapshot.

Purge is a semantic transition: downgrade affected claims and verdict first, persist authorization, remove bytes, leave a tombstone, validate, and rerender. Recovery only resumes that persisted authorization.

## Gates

`PASS` requires:

- non-empty bounded decision and non-empty exact load-bearing claim set;
- confirmed evidence floor;
- passing claim status, source origin, entailing exact excerpt, available raw artifact, and applicability for every load-bearing claim;
- quota/event/state hash reconciliation;
- posture-specific checks;
- Medium/High anti-lock-in and coverage audit when required;
- context-separated High verifier;
- current HTML state hash when a report exists.

`PARTIAL` requires a named reversible safe action whose validity does not depend on unresolved or purged-evidence claims. Otherwise use `BLOCKED`.

Run:

```bash
"$PY" scripts/research_state.py validate <session-dir> --json
"$PY" scripts/research_state.py render <session-dir> --json
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
"$PY" scripts/research_state.py status <session-dir> --json
"$PY" scripts/research_state.py recover <session-dir> --json
"$PY" scripts/research_state.py artifact-purge <session-dir> \
  --artifact-id A1 --reason "retention expired" \
  --requested-status BLOCKED --json
```

Unowned malformed event bytes, conflicting purge metadata, unexpected paths, or missing hashes fail closed. Recovery never invents a deletion target or a research action.
