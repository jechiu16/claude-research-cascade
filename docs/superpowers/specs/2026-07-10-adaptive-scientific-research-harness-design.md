# Adaptive Scientific Research Harness v2

Status: Proposed

Date: 2026-07-10

Scope: Redesign `/deep` as a bounded, evidence-gated research harness for development decisions.

## 1. Executive Decision

`/deep` v2 will optimize for decision quality under a user-approved call budget, not for report volume or model consensus.

The host model selected for the current session is always the Organizer. It frames the problem, chooses the epistemic posture, designs discriminating checks, reconciles evidence, judges inference quality, and translates findings into development actions. External workers produce candidate evidence or independent analysis; no worker supplies the final verdict.

The design has two independent dimensions:

1. **Epistemic posture** determines how the problem should be reasoned about: `lookup`, `synthesis`, `scientific`, or `decision`.
2. **Cost tier** determines the maximum adaptive cycles and external physical calls: `low`, `medium`, or `high`.

Every `/deep` must show one contract card and wait for explicit user confirmation before any external spend. The card displays the inferred posture, recommended tier, physical-call ceilings, reserved reinforcement capacity, intended first wave, local experiment plan, estimated latency, and estimated spend range.

The harness cannot guarantee truth or complete discovery of every relevant premise. It guarantees a fail-closed process over claims that survive an explicit coverage audit: unresolved load-bearing claims cannot be presented as a passing conclusion, and unknown-unknown risk must remain visible. A run ends as `PASS`, `PARTIAL`, or `BLOCKED`.

The release is not considered successful merely because structural transcript tests pass. It must beat or tie a direct built-in Deep Research baseline on paired development-research evaluations while producing fewer false `PASS` outcomes.

## 2. Problem Statement

The current harness has valuable primitives: explicit activation, user-confirmed research contracts, multi-provider workers, source tiers, resumable async jobs, a spend ledger, claim statuses, blind checks, and an artifact validator.

Its current design still has four limitations:

1. The three-axis contract describes depth, independence, and strictness, but it does not mechanically cap paid submissions.
2. Structural validation proves that sections and status words exist, not that claims are entailed by sources, independent by origin, current, or applicable to the user's project.
3. A fixed worker framing can spend calls without maximizing discrimination between plausible explanations.
4. The delivery format is report-oriented, while the primary use case is in-session development: architecture, implementation, tests, reversibility, and research-debt decisions.

Calling more Deep Research engines does not solve these limitations. Multiple engines can repeat the same upstream source, amplify one framing error, and create false confidence through apparent agreement.

## 3. Goals

The v2 harness must:

- produce more reliable development decisions than a direct one-shot Deep Research call;
- bound external-spend exposure using physical-call quotas that the user approves before execution, while reporting that variable provider pricing prevents an exact dollar ceiling;
- use host WebSearch/fetch and local experiments as first-class, low-marginal-cost research instruments;
- preserve adaptive scientific reasoning for ambiguous, difficult, causal, or contested questions;
- use the simplest adequate posture for determinate source-of-record questions;
- verify the most load-bearing claims and inference joints before delivery;
- distinguish source-origin, retrieval-index, analyst-model, and context independence;
- preserve raw worker outputs while maintaining exactly one semantic source of truth;
- generate a readable static HTML report without another model call;
- deliver engineering constraints, reversible assumptions, tests, and resume triggers;
- fail honestly when evidence cannot satisfy the selected tier;
- demonstrate improvement through paired baseline evaluations.

## 4. Non-Goals

The v2 harness will not:

- guarantee that every conclusion is factually correct;
- spend external calls before user confirmation;
- force every problem into competing hypotheses;
- require Deep Research calls merely because a tier permits them;
- treat agreement between models as source independence;
- treat search-result snippets as evidence;
- treat Semantic Scholar TLDRs or citation counts as paper findings;
- use DeepSeek as a retrieval source or final judge;
- create several persisted semantic summaries that can drift;
- make unrelated production code changes during research;
- optimize HTML before quota enforcement, evidence lineage, and quality evaluation work.

## 5. First-Principles Quality Model

For every load-bearing claim, research quality is the conjunction of six dimensions:

1. **Coverage**: all premises that could flip the recommendation are represented.
2. **Source authority**: evidence uses the strongest available source for the claim type.
3. **Entailment**: the cited material directly supports the atomic claim and its qualifiers.
4. **Origin independence**: empirical corroboration traces to independent upstream origins.
5. **Project applicability**: versions, environment, constraints, and use case match the current project.
6. **Calibration**: confidence and status reflect residual uncertainty and contradictory evidence.

A load-bearing claim fails its gate when any required dimension fails. More citations cannot compensate for failed entailment. More model families cannot compensate for one shared upstream source. An official source cannot establish project applicability when the installed version or runtime differs.

## 6. Epistemic Postures

The Organizer infers one primary posture before presenting the contract card. It records the reason for that classification. The user confirms the posture together with the tier.

### 6.1 Lookup

Use for source-of-record facts such as official limits, versions, prices, license terms, standards text, or documented API behavior.

Required behavior:

- fetch the defining primary source directly;
- record version, publication date, or retrieval date when volatile;
- avoid artificial competing hypotheses;
- use a local check when the question concerns the installed environment;
- stop early when one authoritative source defines the fact and scope is clear.

### 6.2 Synthesis

Use for landscapes, literature maps, market scans, and multi-option technical comparisons.

Required behavior:

- define the coverage dimensions before retrieval;
- separate primary findings from secondary summaries;
- record important omissions and selection effects;
- avoid turning popularity, citation count, or repeated summaries into truth;
- distinguish consensus from shared-source repetition.

### 6.3 Scientific

Use when mechanisms are unclear, evidence conflicts, outcomes are surprising, or multiple explanations plausibly fit the observations.

Required behavior:

- define the observable question and scope;
- maintain only genuinely plausible competing hypotheses, including a null hypothesis when meaningful;
- write expected observations and falsifiers before targeted retrieval;
- choose the next check by its ability to discriminate between hypotheses;
- update each hypothesis as `strengthened`, `weakened`, `rejected`, or `reframed`;
- treat unexpected observations as a reason to revise the problem model, not patch the favored answer;
- perform replication or adjudication when the tier permits another cycle.

### 6.4 Decision

Use for architecture choices, migrations, vendor adoption, security decisions, or other recommendations with meaningful implementation consequences.

Decision is an overlay on the applicable lookup, synthesis, or scientific method, not a nested posture with additive quotas. All underlying checks share the one confirmed stage-capacity and physical-call envelope.

Required behavior:

- run the applicable lookup, synthesis, or scientific reasoning underneath the decision;
- identify the recommendation's load-bearing premises and inference joints;
- consider reversibility, cost of error, and option value;
- verify project applicability with a local experiment when feasible;
- separate evidence from Organizer judgment;
- map uncertainty to an engineering posture: invariant, reversible abstraction, experiment, or research debt.

## 7. Cost Tiers

Quotas are ceilings, not spending targets. A tier limits stage capacity; it does not allocate independent quotas that invite the Organizer to run every available tool. The contract card converts the selected route into exact physical-call ceilings before the user confirms spend.

| Tier | Primary scout routes | Deep Research calls | Challenge capacity | Verification separation | Processor calls |
|---|---:|---:|---:|---|---:|
| `low` | 1 | 0 | 1 narrow check | Organizer review | 0 |
| `medium` | 1 | at most 1 | 1 reserved challenge | independent pass; fresh context preferred | 0 by default |
| `high` | 1 | at most 2 | 2 challenge or adjudication actions | context-separated verifier required | optional 1 |

A primary scout route is one bounded orientation path selected from host WebSearch/fetch, Sonar, Scholar, or local inspection. The run does not execute several scout routes merely because they are individually cheap. Local inspection may accompany another scout only when it tests project applicability rather than duplicating web discovery.

The contract card records two separate resource envelopes:

- **external envelope**: exact physical ceilings for all provider probes, Deep Research submissions, and processor calls, with the metered subset identified separately;
- **host envelope**: `lean`, `standard`, or `extended` context class plus an explicit admitted-evidence ceiling in characters and estimated tokens. The numeric ceiling is selected for the current host and shown on the card; class names alone are not enforcement.

All external requests are logged, including free or keyless retrieval, but only metered requests consume the user-approved spend envelope. Host actions do not consume external-call quota; they still record search count, fetch count, admitted characters or estimated tokens, wall time, target claims, and realized state change. Harness-managed views and extracted evidence must refuse to exceed the admitted-evidence ceiling. Host-native tool output that bypasses this mechanism is recorded as an observability limitation, so the harness does not claim a hard bound on total platform context usage.

The Organizer may recommend a custom card when the intended route cannot fit a preset. For example, the existing `cascade` action requires four probe permits and therefore is never implicit in a default scout route. The user must explicitly approve those four physical calls before it runs.

### 7.1 Stage and Permit Accounting

A **logical stage** is a required epistemic function. A **physical action** is one tool invocation, provider request, local experiment command group, or context-separated audit pass. Stages do not create quota by themselves. Every harness-requested physical action is declared on the contract card and accounted as one of:

- `host_retrieval`: one requested host-native search or fetch action; tracked against a declared host-action ceiling but not claimed as mechanically intercepted;
- `local`: one bounded inspection or experiment command group; no external spend, with wall time and admitted output bounded;
- `probe`: one Sonar, Scholar, or comparable non-Deep-Research provider request;
- `deep`: one Deep Research submission attempt, whether accepted, rejected after egress, or left uncertain;
- `processor`: one DeepSeek or other external analyst-model request;
- `network_experiment`: one user-approved request to a non-production external integration under a declared privacy and request-count ceiling;
- `transport`: one poll, resume, stream reconnect, or artifact-download request that harvests an already authorized job without initiating or expanding research;
- `organizer_pass`: an in-context transformation or review with no external request.

One physical action may contribute evidence to several later stages, but it has exactly one primary stage in the ledger. If a Deep Research submission is shaped as a challenge, for example, it consumes both one logical challenge slot and one physical `deep` permit; the logical label never hides the provider call. Separation requirements override reuse: an action that produced or materially shaped the provisional conclusion cannot also satisfy anti-lock-in or independent-verifier requirements.

The preset stage map is:

| Stage | Low | Medium | High | Permit mapping and combination rule |
|---|---|---|---|---|
| frame and predict | required | required | required | `organizer_pass`; no provider permit |
| primary scout | exactly 1 route | exactly 1 route | exactly 1 route | host request=`host_retrieval`; Sonar/Scholar=`probe`; project inspection=`local` |
| investigation | none | optional, at most 1 | optional, at most 2 | each accepted submission=`deep` |
| anti-lock-in challenge | not separate | required after a provisional conclusion in scientific or decision posture | required after a provisional conclusion in scientific or decision posture | consumes one challenge slot plus the physical permit of the selected route; cannot be combined with candidate production or final verification |
| additional adjudication | none | none beyond the reserved challenge | optional, at most 1 | consumes the second High challenge slot plus its physical route permit |
| direct verification | one narrow check before `PASS` | required separate pass | required context-separated pass | exact host/local/probe actions are listed on the card; candidate-producing actions cannot count |
| premise-coverage audit | not required | required for scientific or decision posture | required for scientific or decision posture | may combine with the final verification pass only when it emits separately labeled claim-verification and omission-audit results |
| final inference review | required | required | required | `organizer_pass`; no provider permit |

For Medium, verification and coverage audit may share one fresh pass, but anti-lock-in remains a prior separate action. For High, the context-separated verifier may also perform the blind premise-coverage audit, but it cannot have participated in scouting, investigation, candidate production, or anti-lock-in. An external verifier or auditor consumes a `processor` permit; a host-native fresh-context agent consumes the declared host-action and context envelopes instead.

The contract card contains a `stage_permit_map` that expands every planned stage into exact physical ceilings. Presets constrain this map; they do not infer hidden free actions. Runtime validation rejects a route whose expanded probe, deep, processor, network-experiment, transport, local-output, or requested host-action count exceeds the confirmed card.

### 7.2 Low

Use for narrow facts, quick orientation, or one decisive scientific check.

Select one scout route, then spend the challenge capacity on direct verification rather than a second broad scout. The run may pass only when the conclusion is narrow enough for one cycle. It must not claim decision-grade coverage for an ambiguous, multi-premise question.

### 7.3 Medium

Use for reversible implementation, prototypes, technical design, and ordinary literature or product research.

The intended allocation is:

- one primary scout route selected for the problem shape;
- at most one sharpened Deep Research call when the scout leaves meaningful coverage gaps;
- direct source and local applicability checks;
- one reserved challenge action for replication, adjudication, reframing, or an alternate retrieval index;
- an independent verification pass and final inference-joint review.

If Sonar is the scout, the card may reserve one additional probe for challenge. If host retrieval is the scout, the same challenge slot may remain a zero-dollar host check or authorize one alternate-index probe. Unused capacity remains unspent.

### 7.4 High

Use for costly, difficult-to-reverse, contested, or high-consequence decisions.

The intended allocation is:

- one primary scout route plus local applicability inspection when relevant;
- one Deep Research branch for broad evidence coverage when needed;
- direct verification of load-bearing claims;
- a second Deep Research branch from another retrieval family only when shaped by the first branch's weakest hypothesis or inference joint;
- up to two targeted challenge or adjudication actions;
- a context-separated verifier that did not produce the candidate conclusion;
- optional DeepSeek analyst audit only when it adds analyst-model independence or relieves context pressure without duplicating host normalization.

The second Deep Research call must not repeat the first broad query. If no unresolved empirical or coverage gap justifies it, it remains unused. If no fresh host context or approved independent auditor is available, a High run cannot return `PASS`.

## 8. Contract Card and User Trigger

Every `/deep` follows this interaction boundary:

1. Infer the research target from session context.
2. Ask framing questions only when an answer changes posture, tier, privacy, cost, or recommendation.
3. Preflight host capabilities, provider availability, pending resume tokens, reusable artifacts, and historical call costs.
4. Present one contract card.
5. Wait for explicit user confirmation.
6. Execute within the confirmed ceilings without asking again unless privacy scope changes or new external spend is required.

The contract card must show:

```text
Problem posture: <lookup|synthesis|scientific|decision>
Reason: <why this posture fits>

Tier: <low|medium|high|custom>
Adaptive cycles: <n>
Primary scout route: <host-web|sonar|scholar|local|custom>
Host context class: <lean|standard|extended>
Admitted evidence ceiling: <=<characters and estimated tokens>
Expected total context footprint: <estimate plus observability limits>
External quota: provider probes<=<n> (metered<=<n>), deep<=<n>, processor<=<n>
Transport and network experiments: transport requests<=<n> (metered<=<n>), external experiment requests<=<n>, max wall time=<duration>
Other external retrieval: <tracked but unmetered actions>
Stage permit map: <stage -> physical action type and ceiling>
Raw storage ceiling: <=<size>; sensitive retention=<policy>
Reserved capacity: <what cannot be consumed by discovery>
Local experiment: <required|planned|not feasible, with reason>
Expected first wave: <actions>
Evidence floor: <what PASS requires>
Estimated latency: <range>
Estimated spend: <historical or list-price range; not a hard ceiling>
Stop behavior: PASS, PARTIAL, or BLOCKED; no unapproved extra calls
Privacy: <external egress summary>
```

The current `depth x independence x strictness` user-facing contract is replaced by `epistemic posture x cost tier`. Independence and strictness remain internal quality-gate requirements derived from claim type, posture, and tier.

## 9. Organizer Loop

### 9.1 Inspect

- inspect overlapping state and raw artifacts;
- harvest pending async jobs before new submissions;
- reuse only artifacts whose scope and vintage still fit;
- detect host WebSearch/fetch, fresh-context agents, terminal access, and writable paths;
- identify privacy-sensitive local material.

### 9.2 Frame

- state the development decision or knowledge target;
- list exclusions and success criteria;
- identify load-bearing claims or competing hypotheses;
- select and explain the epistemic posture;
- write falsifiers before searching when the posture is scientific or decision-critical.

### 9.3 Choose

Choose actions with a declared lexicographic policy rather than an invented dollar-equivalent utility score.

At each cycle, enumerate only actions that fit the remaining stage and physical permits. An action is eligible only when the Organizer predicts at least one **material state change**:

- establish, weaken, dispute, or re-scope a load-bearing claim;
- discriminate between live hypotheses;
- test a recommendation inference joint or project-applicability assumption;
- add a genuinely independent primary origin or direct local observation;
- resolve an omission candidate raised by the coverage audit;
- change the safe action, verdict, or required uncertainty disclosure.

"More context," another model opinion, or a same-origin restatement is not a material state change.

For every eligible action, record this ordinal tuple:

1. `gate_urgency`: `3` for safety, legality, or go/no-go critical; `2` for another unresolved load-bearing gate; `1` for a non-load-bearing quality improvement; `0` for no gate;
2. `state_change`: `2` when the action directly tests the target; `1` when it plausibly exposes a missing candidate; `0` when no named canonical-state field is expected to change;
3. `independence_gain`: `2` for a new primary origin or direct experiment; `1` for a new secondary origin or retrieval index; `0` for the same upstream origin;
4. `cost`: ascending tuple of additional metered calls, expected admitted tokens, latency class, privacy/egress class, and anchoring risk.

Select the action with the lexicographically highest first three fields, then the lowest `cost`. Stable final ties prefer local direct observation, then a known primary-source host fetch, then the already-approved route requiring fewer new artifacts. The Organizer supplies the ordinal judgments and a one-sentence falsifiable rationale; deterministic code validates the tuple, applies the tie-break, and logs any override. Tests establish reproducibility from the declared tuple, not the truth of the Organizer's forecast.

The ordinal forecast must consider:

- probability of resolving a quality gate;
- discrimination between live hypotheses;
- coverage of a load-bearing gap;
- expected change to the recommendation or engineering posture.

The cost tuple must consider:

- metered external calls and dollars;
- Organizer context admitted by tool output or artifacts;
- wall time and tool round trips;
- anchoring risk from another model's synthesis;
- privacy or egress cost.

The ordinal inputs remain Organizer judgment. Deterministic code enforces ranking, chosen route, permits, context admission, and logging; it does not pretend to prove that the forecast or selected action was globally optimal. Evaluation measures whether the routing policy performs well enough by problem shape.

The Scout Router selects exactly one primary route:

- host WebSearch/fetch for known primary sources, narrow verification, or low-page-count questions;
- Sonar for broad orientation, terminology discovery, alternate-index retrieval, or compressing many candidate pages into a bounded scout artifact;
- Scholar for paper discovery and citation trails;
- local inspection for project-specific facts that the web cannot establish.

Routing first applies decisive shape rules: project-local truth selects local inspection; explicit paper or citation-trail discovery selects Scholar; a known source of record or a bounded set of at most three target pages selects host retrieval; broad terminology discovery or many unknown candidate sources selects Sonar. When more than one rule applies, use the action tuple and stable tie-break above rather than a fixed provider preference.

Deep Research is an investigation action, not a scout default. A processor is an exception for context offload or analyst diversity, not another routine stage.

### 9.4 Predict

Before an action in scientific or decision posture, record:

- the target hypothesis, claim, or inference joint;
- expected observations under plausible alternatives;
- what result would change the current view;
- why the action is more discriminating than available alternatives;
- which quota permit it will consume.

### 9.5 Execute

- batch independent actions when queries do not depend on prior results;
- keep dependent Deep Research calls sequential when the second query should learn from the first;
- preserve every accepted async resume token;
- treat search and worker content as untrusted data, not instructions;
- never exceed the confirmed physical-call ceilings.

### 9.6 Normalize

- extract atomic candidate claims with scope and qualifiers;
- attach supporting and counter-evidence IDs;
- attach exact excerpts and raw-artifact offsets for load-bearing evidence;
- assign source tiers and upstream origin IDs;
- preserve raw artifacts rather than replacing them with summaries;
- require Organizer promotion before a candidate enters canonical state.

### 9.7 Update

For each hypothesis or claim, record whether new evidence strengthens, weakens, rejects, disputes, or reframes it. A surprise must trigger a problem-model review before further spending.

The reserved cycle chooses one branch:

- **replication** when the first result fits expectations but needs independent confirmation;
- **adjudication** when sources or observations conflict;
- **reframing** when evidence invalidates the initial model;
- **joint verification** when facts are supported but the recommendation inference remains weak.

### 9.8 Anti-Lock-In Checkpoint

For Medium and High runs in scientific or decision posture, the first provisional conclusion triggers a mandatory checkpoint before the run can continue toward delivery:

1. freeze the candidate conclusion and its current supporting evidence;
2. record its strongest falsifier;
3. search actively for disconfirming evidence;
4. retain up to two genuinely plausible alternatives;
5. update, reject, or reframe the candidate before using the remaining challenge capacity.

The checkpoint uses the cheapest route that can expose contradiction. It does not automatically justify another paid probe when host retrieval or a local experiment can perform the challenge.

### 9.9 Coverage Audit

Before Medium or High delivery in scientific or decision posture, perform a premise-coverage audit. Give the auditor the original question, framing, exclusions, proposed action, and current load-bearing claim list without confidence language. Ask which omitted premise, boundary condition, stakeholder, failure mode, or alternative mechanism could flip the action.

New candidates are not automatically true. The Organizer must classify each as addressed, out of scope with reason, non-load-bearing, or a new load-bearing gap. High uses a context-separated auditor; Medium uses a separate pass with fresh context preferred.

This audit reduces omission risk but cannot prove that the claim universe is complete. Delivery must preserve that limitation instead of presenting gate completion as certainty about unknown unknowns.

### 9.10 Verify and Terminate

Run the posture- and tier-specific quality gates. Stop when all load-bearing claims pass, when quota is exhausted, when the missing evidence is unavailable, or when every remaining permitted action has `state_change=0`. `Negligible` is not an independent discretionary threshold.

Return `PASS` only when every required gate passes. Return `PARTIAL` when some useful conclusions survive but at least one non-fatal load-bearing gap remains. Return `BLOCKED` when a critical claim cannot be established or the available evidence does not support a responsible recommendation.

## 10. Host WebSearch and Fetch

Host retrieval is the default precision instrument when available.

Discovery and verification are separate passes:

- **Discovery pass** identifies candidate answers, vocabulary, sources, and plausible alternatives.
- **Verification pass** receives the exact claim and its falsifier, not the Organizer's confidence language, and searches for primary evidence, counterexamples, limitations, and shared upstream origins.

Search snippets are discovery metadata. They never clear an evidence gate. The Organizer must fetch and inspect the underlying source.

Host search may share an index family with an external worker. Independence is judged by final source origin, not by tool name.

If host retrieval is unavailable, the contract card discloses the substitution and may recommend more external probe permits.

Host retrieval and Sonar are routing alternatives, not a fixed sequence:

| Problem shape | Preferred scout | Typical verification |
|---|---|---|
| known official or source-of-record target | host search/fetch | direct primary read; no Sonar by default |
| broad or poorly named landscape | Sonar | host fetch of the strongest T1/T2 candidates |
| academic literature | Scholar or Sonar | host fetch of primary papers |
| high-risk decision | route with best scope fit | host primary fetch plus local experiment |
| host retrieval misses terminology or regional sources | Sonar | host inspection of returned sources |
| alternate retrieval index needed | whichever route ran first | the other route as a targeted challenge |

Search and fetch output admitted to Organizer context is a resource. The harness records returned characters or tokens when available, content actually admitted to state, primary-source hit rate, and realized state change. Raw pages remain artifacts and are not automatically copied into the working context.

## 11. Local Experiments

Local experiments are a core differentiator from standalone Deep Research.

Use them when a claim concerns the current codebase, dependency version, operating system, runtime, API behavior, data shape, performance, or compatibility. Examples include:

- inspecting installed versions and lockfiles;
- reading actual dependency source or generated types;
- running a minimal reproducer in a temporary or project-sanctioned location;
- executing a focused benchmark;
- checking a live response schema against current code;
- testing an integration against non-production fixtures.

Local experiments must be read-only or safely reversible unless the user separately authorizes broader changes. A `local` action runs with network egress disabled or otherwise verified absent. A live API, response-schema, or integration check is a `network_experiment`, not `local`; the contract must identify its endpoint class, privacy scope, possible billing, exact request ceiling, and non-production safety boundary. Experiments must not mutate production systems or send local files externally without approval.

An experiment record includes environment, command or procedure, observed result, artifact path, limitations, and the claim or hypothesis it updates.

When a relevant local experiment is feasible but omitted, Medium and High runs must explain why. A High decision cannot `PASS` project-applicability gates solely from generic web evidence when a decisive local check is readily available.

## 12. Worker Routing

| Worker | v2 role | Evidence contribution |
|---|---|---|
| host reasoning | framing, hypotheses, synthesis, inference audit, engineering translation | judgment, not external evidence |
| host WebSearch/fetch | primary-source discovery and direct verification | evidence from fetched source origin |
| `sonar` | narrow gap, alternate retrieval index, dispute adjudication | cited candidate evidence |
| `cascade` | custom broad orientation when the problem is too vague for targeted probes | four physical probe calls; candidate evidence only |
| `scholar` | paper discovery, terminology, citation trail | paper metadata; paper claims require primary inspection |
| `perplexity` | optional long retrieval/synthesis branch | candidate evidence from its cited sources |
| `openai` | optional long retrieval/synthesis branch | candidate evidence from its cited sources |
| `gemini` | optional long retrieval/synthesis branch | candidate evidence from its cited sources |
| `deepseek` | optional supplied-material processor or blind analyst audit | derived analysis only; no retrieval evidence |
| `demo` | local contract test | never evidence |

Provider selection uses task fit, available keys, source or index diversity, historical completion rate, latency, actual ledger cost, and the current weakest load-bearing uncertainty. No provider has a permanently privileged order.

## 13. DeepSeek Boundary

DeepSeek is not part of the default Medium route. It is optional because the current host model already performs normalization without an extra API charge, while another processor introduces privacy, compression loss, and another hallucination surface.

Allow one processor call only when at least one condition holds:

- the evidence packet creates material host-context pressure;
- an independent analyst-model audit has meaningful decision value;
- bulk contradiction mining would free the Organizer to verify rather than summarize.

Supported modes:

1. **Evidence extractor**: produce candidate atomic claims with artifact IDs and exact excerpts.
2. **Contradiction miner**: pair conflicting excerpts and identify missing assumptions without adding outside facts.
3. **Blind evidence auditor**: receive exact claims and evidence packets without the Organizer's verdict, confidence, or recommendation; return `entailed`, `contradicted`, or `insufficient` candidates.

DeepSeek adds analyst-model independence and, when the verdict is withheld, context independence. It does not add retrieval-index or source-origin independence.

DeepSeek output cannot modify canonical state. A deterministic validator must confirm schema, artifact IDs, source IDs, output completeness, and exact excerpt presence. The Organizer reviews all load-bearing candidates before promotion. Invalid or truncated output is discarded rather than reconstructed by guesswork.

Any call that sends local or user-provided files externally requires explicit privacy approval. Public worker reports may be processed under the original confirmed contract when the contract card states that egress.

## 14. Physical-Call Quota

The accounting unit is an outbound physical network request, not an HTTP method or logical CLI command. Requests that initiate or expand retrieval, reasoning, processing, or an external experiment consume their corresponding research permit. Requests that only harvest an already authorized async job consume the separate transport ceiling. The user-approved spend envelope applies to metered categories; keyless, transport, or host-native actions are still counted and reported so apparent zero-dollar routes cannot hide billing uncertainty, latency, or context cost.

This mechanism bounds call-count exposure, not exact dollars. Provider-side search depth, reasoning tokens, and output size can vary inside one accepted call, so the card must show historical or list-price ranges and preserve that uncertainty.

Rules:

- acquire the matching physical permit before every harness-managed outbound request that can initiate or expand work, including `GET`, `POST`, streaming, SDK, and external experiment calls;
- a Sonar retry consumes another probe permit;
- `cascade` atomically reserves four probe permits before launching;
- no retry may exceed the remaining quota;
- a Deep Research submit attempt consumes one deep permit before the POST;
- a DeepSeek request consumes one processor permit before the POST;
- each live integration request consumes one `network_experiment` permit;
- async polling, stream reconnects, artifact downloads, and `--resume` do not consume a new research permit, but every outbound request consumes one predeclared `transport` slot and remains subject to the wall-time ceiling;
- if a provider can bill polling, resume, streaming, or download separately, the card identifies that metered transport subset and the request consumes both one transport slot and the applicable metered ceiling;
- local validation failures consume no permit only when network egress did not occur;
- no automatic quota refund occurs after an outbound attempt, even when acceptance is uncertain;
- list prices and actual dollars are recorded but never substitute for physical-call enforcement;
- each contract records the exact physical ceiling implied by its selected scout and challenge routes rather than inheriting every tool maximum in the tier.

Ledger events distinguish `attempted`, `accepted`, `completed`, `failed`, `interrupted`, and `uncertain`. The contract report shows logical actions, physical attempts, admitted host-context size, wall time, and realized information gain.

## 15. Evidence and Claim Model

Every canonical claim is atomic and contains:

```json
{
  "id": "C3",
  "text": "One falsifiable claim",
  "scope": "Versions, population, environment, and conditions",
  "qualifiers": ["Important limitation"],
  "load_bearing": true,
  "status": "corroborated",
  "supporting_evidence_ids": ["E2", "E7"],
  "counter_evidence_ids": ["E9"],
  "source_origin_ids": ["O1", "O4"],
  "applicability": "checked",
  "would_change_if": "Observation that would flip the claim",
  "engineering_implication_ids": ["I4"],
  "notes": "Nuance not captured by controlled fields"
}
```

Evidence records contain artifact ID, source ID, source tier, origin ID, retrieved-at or published-at date, exact excerpt, raw-artifact offsets, entailment status, and applicability notes. Normalized excerpts may be used only for non-load-bearing discovery notes and cannot clear a quality gate.

Source tiers remain:

- `T1`: source of record or primary evidence;
- `T2`: quality secondary source tied to primaries;
- `T3`: aggregator, UGC, SEO content, or uncited model prose.

Claim statuses remain compatible with the current vocabulary: `corroborated`, `single-source`, `corroborated-same-family`, `disputed`, `retired`, and `unverified`.

Entailment is recorded separately as `entailed`, `partially-entailed`, `contradicted`, or `not-checked`.

Hypothesis updates such as `strengthened`, `weakened`, `rejected`, and `reframed` are transition events, not claim statuses. Events record why canonical claim status changed without creating a second status vocabulary.

### 15.1 Branch Manifest and Evidence Delta

A paid Deep Research branch is never required to generate canonical state directly. Its raw output remains immutable. Before branch content can affect aggregation, it passes through two bounded artifacts.

The deterministic branch manifest contains transport and provenance data:

```json
{
  "branch_id": "B2",
  "provider": "openai",
  "query": "...",
  "artifact_path": "raw/action_004.json",
  "artifact_sha256": "...",
  "source_urls": [],
  "usage": {},
  "cost": {}
}
```

The Organizer then produces a minimal semantic delta only for verdict-relevant content:

```json
{
  "branch_id": "B2",
  "scope": "...",
  "claim_deltas": [
    {
      "claim_id": "C3",
      "effect": "strengthen",
      "evidence_refs": ["E7"],
      "counter_evidence_refs": ["E9"]
    }
  ],
  "new_source_origin_ids": ["O4"],
  "contradictions": [],
  "unresolved_gaps": []
}
```

The delta does not contain a branch-level final recommendation. Candidate decisions are formed only after the Organizer reconciles all accepted deltas, direct sources, and local observations.

A deterministic validator checks schema, IDs, artifact hashes, source existence, quota records, and exact excerpt presence for load-bearing evidence. It cannot certify that an excerpt semantically entails a claim or that two origins are genuinely independent; those remain Organizer and Verifier judgments.

An invalid delta cannot update canonical state. The paid raw artifact remains available, and the Organizer may inspect it directly and produce a corrected delta without repurchasing research.

## 16. Independence Model

The state records four independent dimensions:

| Dimension | Meaning |
|---|---|
| source-origin independence | evidence originates from independent primary observations or authorities |
| retrieval-index independence | evidence was discovered through different retrieval systems |
| analyst-model independence | analysis came from a different model family |
| context independence | the analyst did not receive the current verdict or hypothesis state |

Only source-origin independence can satisfy empirical corroboration by itself. Retrieval and analyst diversity are useful discovery and bias-reduction signals, but they cannot promote duplicated upstream evidence.

For a source-of-record fact, one directly fetched T1 source may clear the gate. For empirical claims, no single origin clears a two-source requirement, including a primary paper reporting its own result.

Promotion rules are explicit:

| Claim type and evidence | Maximum promotable status |
|---|---|
| source-of-record claim with directly fetched, applicable, entailing T1 | `corroborated` for that defined fact |
| empirical claim with one origin, including one primary study | `single-source` |
| empirical claim with several retrieval tools but one upstream origin | `corroborated-same-family` |
| empirical claim with at least two applicable, entailing, independent origins | `corroborated` |
| materially conflicting evidence without adjudication | `disputed` |
| missing entailment or applicability check | `unverified` |

`single-source`, `corroborated-same-family`, `disputed`, and `unverified` cannot clear an empirical load-bearing gate. A local experiment may count as an independent origin only when its procedure, environment, and observation are recorded and it measures the relevant claim rather than merely reproducing another source's assertion.

## 17. Quality Gates

### 17.1 Universal Gates

Before `PASS`:

- every load-bearing claim has a recognized status;
- every load-bearing claim traces to evidence and raw artifacts;
- exact excerpts or direct local observations support each load-bearing claim;
- volatile facts carry an evidence date;
- unresolved contradictions are either adjudicated or reflected in status;
- recommendation and evidence are separate;
- Medium and High scientific or decision runs completed the anti-lock-in checkpoint;
- Medium and High scientific or decision runs completed the premise-coverage audit and dispositioned every candidate omission;
- physical-call quota reconciles with the ledger;
- no paid async job remains silently unharvested;
- when an HTML report exists, its embedded hash matches canonical state.

### 17.2 Lookup Gate

- the defining primary source is fetched directly;
- scope, version, and date match the question;
- local applicability is checked when relevant.

### 17.3 Synthesis Gate

- coverage dimensions are explicit;
- major categories and omissions are represented;
- primary findings are distinct from summaries;
- agreement is checked for shared upstream origins.

### 17.4 Scientific Gate

- plausible alternatives are represented without artificial padding;
- at least one discriminating check is recorded;
- expected observations were written before the check;
- surprising or contradictory evidence caused an explicit update or reframe;
- residual uncertainty is tied to observations that could resolve it.

### 17.5 Decision Gate

- load-bearing premises and inference joints are explicit;
- the weakest joint receives adversarial review;
- a High run's verifier is context-separated from the reasoner that produced the provisional conclusion;
- project applicability is checked locally when feasible;
- reversibility and cost of error influence the recommendation;
- unresolved critical claims force `PARTIAL` or `BLOCKED`.

### 17.6 Tier Gate

- Low passes only a narrow conclusion supported by one cycle.
- Medium may support reversible implementation when all load-bearing claims for that action pass and an independent verification pass is recorded; fresh context is preferred but an honest shared-context downgrade is allowed.
- High may support difficult-to-reverse decisions only after independent replication or equivalent primary/local evidence, adversarial joint review, and a context-separated verifier. Without verifier separation, the maximum status is `PARTIAL`.

## 18. Delivery Status

A **critical load-bearing claim** is a premise whose falsity or unresolved status could change the recommended action, safety boundary, or go/no-go decision within the stated scope. A **non-fatal gap** may change nuance, implementation detail, or confidence but cannot change the safe action being recommended.

### PASS

All posture- and tier-specific gates pass, the coverage audit found no unresolved candidate omission that could flip the action, and no identified load-bearing claim remains unresolved. The recommendation may still include bounded unknown-unknown risk, which must be stated explicitly.

### PARTIAL

The research produced useful, traceable findings, but at least one load-bearing gap remains. `PARTIAL` is allowed only when a safe reversible action exists whose validity does not depend on resolving that gap. Delivery must state which actions are safe, which must remain reversible, and what would close the gap.

### BLOCKED

A critical source, local condition, vendor artifact, or observation is unavailable, or an unresolved critical load-bearing claim prevents any safe recommendation. Delivery must state why the decision is blocked and why more generic model calls are unlikely to help.

## 19. Engineering Handoff

The canonical state and final chat include:

- executive decision and status;
- safe facts that may become constraints or invariants;
- supported but reversible assumptions;
- disputed claims that must not become hard-coded premises;
- rejected hypotheses and why they were rejected;
- architecture and implementation implications;
- recommended local experiments or acceptance tests;
- what evidence would flip the decision;
- research debt and explicit resume triggers;
- artifact paths, quota use, wall time, and actual spend when available.

Evidence maps to engineering posture:

| Evidence state | Engineering posture |
|---|---|
| primary, entailed, applicable, independently replicated when required | invariant or hard constraint |
| supported with bounded residual uncertainty | reversible abstraction, configuration, or feature flag |
| disputed or applicability not checked | spike, instrumentation, or no-go for hard dependency |
| unknown and load-bearing | research debt or blocked decision |

## 20. Artifact Architecture

Use one semantic source of truth and three non-competing artifact classes:

```text
reports/deep_<yyyymmdd>_<slug>/
├── state.json
├── events.jsonl
├── report.html
└── raw/
    ├── action_001.json
    ├── action_002.json
    └── ...
```

### 20.1 state.json

The only canonical semantic state. Top-level sections are:

```text
schema_version
session
contract
framing
summary
hypotheses
planned_checks
observations
claims
evidence
sources
source_origins
branch_manifests
evidence_deltas
action_metrics
inference_joints
engineering_handoff
open_questions
verification
artifact_index
```

State updates use validated patches and atomic replacement. The Organizer never regenerates the entire file from prose when a small patch is sufficient.

### 20.2 events.jsonl

Append-only operational history only: contract confirmation, quota permits, worker attempts, submit IDs, resume tokens, completion, failure, cost, wall time, state revision, and report generation. It must not hold a competing prose summary.

Each completed action records expected and realized information gain: target claims, expected state delta, actual claims changed, hypotheses rejected or reframed, decision change, admitted context size, and a `zero_gain` marker. These measurements support later routing calibration but never rewrite policy automatically.

### 20.3 raw/

Immutable provider responses, fetched-source snapshots when permitted, local experiment outputs, and processor outputs. Every artifact has a SHA-256, size, media type, sensitivity class, retention policy, and `include_in_html` flag recorded in `state.json`.

Public web artifacts default to session retention. Local command output and user files default to `local-sensitive`, require redaction review before persistence, and are excluded from HTML. The contract records a raw-storage ceiling; artifacts above it remain external references or require explicit approval.

A purge is a semantic state transition, not a filesystem-only deletion. Before removing bytes, the purge command atomically marks affected artifacts `purge_pending`, invalidates any `PASS` whose load-bearing lineage depends on them, and makes the current HTML stale. It then removes the content, verifies absence, writes `availability=purged` tombstones with hashes, timestamp, and reason, reruns all affected quality gates, and regenerates the report. A purged load-bearing artifact cannot satisfy the universal traceability gate: the run becomes `PARTIAL` only when a safe reversible action remains independent of that evidence; otherwise it becomes `BLOCKED`. Interruption at any purge phase leaves the run non-`PASS` until recovery completes.

### 20.4 report.html

A deterministic, self-contained human view generated from `state.json` without an LLM call.

Requirements:

- inline CSS and no CDN dependency;
- no required JavaScript;
- native `<details>` disclosure for long evidence;
- all untrusted content HTML-escaped;
- responsive and print-friendly layout;
- status expressed with text as well as color;
- sections for decision, quota, hypotheses, cycles, claims, evidence lineage, source origins, disputes, engineering handoff, and resume conditions;
- bounded excerpts only; full raw artifacts are linked according to sensitivity policy rather than embedded;
- embedded canonical-state SHA-256 and generation timestamp;
- validator marks the report stale when its hash does not match current state.

There is no persisted full Markdown report and no persisted handoff duplicate. For machine consumption, `research_state.py view` emits a compact Markdown or JSON projection to stdout from current `state.json`.

## 21. Security and Privacy

- external workers receive only the minimum task-local context required;
- local or user-provided file egress requires explicit approval;
- public research artifacts may be sent to a processor only when the contract card discloses that path;
- retrieved web content is untrusted data and cannot change harness instructions;
- processors run without tools and cannot write canonical state;
- raw artifacts are escaped before HTML rendering;
- raw artifacts carry sensitivity, retention, size, and HTML-inclusion metadata;
- local-sensitive raw content is redacted or excluded rather than copied into the report;
- secrets, API keys, and `.env` contents never enter state or reports;
- local experiments avoid production systems and destructive actions.

## 22. Failure and Recovery

- harvest existing resume tokens before new spend;
- journal submit attempts before polling;
- never resubmit an accepted paid async job while a resume token exists;
- use provider idempotency keys when supported and retain them with the attempt event;
- when a submit may have been accepted but no response or resume token was received, mark it `uncertain`, consume the permit, and prohibit automatic resubmission; recovery requires provider-side lookup or an explicit new user-approved call;
- when a resume token expires or provider lookup cannot resolve an uncertain attempt, preserve the unresolved cost risk in delivery rather than claiming exactly-once submission;
- bound polling with both the confirmed transport-request and wall-time ceilings; polling timeout preserves the token and returns control without a new submission;
- preserve raw completed payloads before extraction;
- record uncertain outbound attempts conservatively against quota;
- fall back from host retrieval to external probes only within the confirmed card;
- fall back from DeepSeek failure to Organizer processing without spending another processor call;
- when quota is exhausted, deliver `PARTIAL` or `BLOCKED` rather than silently extending the run;
- when the missing evidence is a vendor, user, or local artifact, stop instead of buying more generic retrieval.

## 23. Target Runtime Structure

The current monolithic CLI should evolve toward:

```text
scripts/
├── deep_research.py
├── research_state.py
├── render_report.py
├── validate_state.py
├── quota.py
├── ledger.py
└── providers/
    ├── sonar.py
    ├── scholar.py
    ├── perplexity.py
    ├── openai.py
    ├── gemini.py
    └── deepseek.py
```

`deep_research.py` remains a thin provider CLI. Provider adapters own submit, poll, resume, extract, and raw-payload preservation. The host model owns the Organizer loop; Python enforces state, quota, provenance, validation, rendering, and recovery.

The split is justified by independent testability, not abstraction for its own sake. Shared code is extracted only where quota, ledger, or provider contracts require it.

## 24. Validation and Tests

### 24.1 Unit Tests

- permits are acquired before outbound attempts;
- retries consume additional permits;
- `cascade` reserves four permits atomically;
- local actions with attempted network egress are rejected or reclassified as `network_experiment`;
- every poll, resume, reconnect, and download consumes a transport slot even though it does not consume a new research permit;
- GET, streaming, SDK, and integration-test paths cannot bypass outbound request accounting;
- accepted-without-response, missing-token, expired-token, and uncertain-submit paths never auto-resubmit;
- polling obeys wall-time bounds and preserves recoverable tokens;
- quota exhaustion fails closed;
- ledger events survive interruption and malformed trailing lines;
- state patches are atomic and schema-valid;
- branch manifests are deterministic and evidence deltas cannot reference missing IDs;
- invalid or invented excerpts cannot update canonical state;
- one selected scout route cannot silently expand into several routes;
- host-context accounting excludes raw artifacts that were not admitted;
- artifact hashes detect mutation;
- purging a load-bearing raw artifact invalidates `PASS`, revalidates affected claims, and makes stale HTML fail validation;
- HTML escaping prevents artifact injection;
- report hash detects stale output.

### 24.2 Provider Contract Tests

Use fixtures for success, timeout, terminal failure, schema drift, empty output, truncated output, missing citation lists, and raw-payload recovery. CI does not call paid providers.

### 24.3 Epistemic Scenario Tests

Fixtures must test:

- one claim repeated by many sources with one upstream origin;
- a citation that does not entail the claim;
- an omitted load-bearing premise that the coverage audit must surface;
- stale official documentation;
- conflicting primary sources;
- a locally installed version that contradicts generic web guidance;
- a Deep Research report with confident unsupported prose;
- a surprising observation that should trigger reframing;
- a missing vendor artifact that should produce `BLOCKED`;
- a processor-invented excerpt that must be rejected;
- Host WebSearch and Sonar routes that differ in context footprint and primary-source yield;
- a zero-information action that must not justify route escalation;
- a provisional conclusion that must trigger the anti-lock-in checkpoint;
- a High run without context-separated verification that must not produce `PASS`;
- an over-conservative run that abuses `BLOCKED` to avoid false `PASS` and must lose utility score;
- quota exhaustion that must not produce false `PASS`.

### 24.4 Golden Transcripts

Keep structural transcripts, but update them to demonstrate posture selection, contract confirmation, quota permits, adaptive cycles, local experiments, quality gates, and engineering handoff. Structural transcript validation remains necessary but is not sufficient evidence of research quality.

## 25. Comparative Evaluation

Evaluation uses a coverage matrix and sequential stopping, not a fixed task count. A fixed count without observed variance or power analysis is not a valid proof of improvement.

The coverage matrix includes:

- source-of-record and volatile-fact lookup;
- broad synthesis and terminology discovery;
- ambiguous scientific or conflicting-evidence questions;
- development decisions with decisive local applicability checks;
- adversarial traps involving source echoes, stale evidence, missing artifacts, false confidence, and prompt injection;
- transport, provider, resume, and quota failures;
- prospective questions whose answers or local observations are not yet revealed.

Evaluation has three lanes.

### 25.1 Deterministic Regression Lane

Run fixture-based tests for quota, state lineage, source echoes, entailment failures, stale evidence, invalid excerpts, provider recovery, false `PASS`, and artifact integrity. This lane makes no paid calls and grows whenever a new failure mode is discovered.

### 25.2 Paid Paired Lane

Before revealing any arm output, each task receives an adjudication sheet containing the target, applicable strata, critical claims, acceptable source-of-record or experiment, safe actions, known fatal errors, and whether sufficient evidence exists to make abstention avoidable. The sheet is immutable for that confirmatory evaluation version once any arm output is revealed.

If a sheet is demonstrably wrong after reveal, an independent adjudicator who has not seen arm identities or aggregate comparisons must open a versioned protocol amendment. The affected task and runs are excluded from the current confirmatory sequence, the correction and reason remain in the audit record, and all affected outputs are re-adjudicated blind under the frozen new sheet. When the target, admissible evidence, fatal-error rule, or safe-action set changes, all arms for that task must be rerun; old results remain exploratory only. Retroactive winner-aware rescoring is prohibited.

Blinded adjudicators assign each run one primary **task utility grade**:

| Grade | Operational meaning |
|---:|---|
| `4` | correct decision-grade answer or recommendation; every critical claim is accurate and traceable, and any action is safe for the task |
| `3` | correct useful reversible action or bounded answer; non-fatal gaps are disclosed and no critical unsupported claim is passed |
| `2` | responsible `PARTIAL` or `BLOCKED` with no unsafe claim, but no useful action or complete answer |
| `1` | avoidable abstention, materially misleading synthesis, or a wrong but readily reversible recommendation |
| `0` | unsafe or costly wrong recommendation, fabricated decisive evidence, or false `PASS` while a critical claim is false or unsupported |

For lookup tasks without an action recommendation, "action" means the delivered bounded answer and its permitted downstream use. Avoidable abstention is scored only when the predeclared sheet and adjudicated evidence show that a grade `3` or `4` result was achievable within the arm's permitted inputs.

The independent task is the paired statistical unit. Repeated runs estimate within-task variance and are averaged within each task and arm; they are not counted as independent tasks. The primary comparison is the stratified paired difference in mean task utility. A predeclared anytime-valid confidence sequence or group-sequential alpha-spending procedure supplies a two-sided 95% interval, so checking after each batch does not silently inflate the false-positive rate. Pilot runs used to choose the method or estimate variance are excluded from confirmatory evidence unless the protocol was frozen before their outcomes were revealed.

Secondary diagnostics do not replace the primary utility contract:

- critical-claim accuracy and claim-source entailment are task-level proportions;
- false `PASS` is any grade `0` caused by a passed critical claim and remains a hard gate;
- safe-action coverage is the proportion of runs graded `3` or `4`;
- avoidable abstention is the proportion graded `1` specifically for unnecessary `PARTIAL` or `BLOCKED`;
- verdict calibration reports observed critical-claim correctness separately for `PASS`, `PARTIAL`, and `BLOCKED`; the harness does not invent numeric confidence merely to compute a score.

Each sampled task runs under comparable arms:

1. direct Deep Research baseline;
2. `/deep` Medium;
3. `/deep` High when the task justifies High posture and the evaluation budget allows it.

Tasks are sampled in stratified batches across the coverage matrix. Before confirmatory runs, the evaluation plan fixes the applicable strata, batch order, repeat policy, maximum spend, and a minimum independent-task requirement derived from pilot variance or a conservative precision analysis. Every applicable stratum must be represented before a claim may stop; no aggregate result may substitute for a missing stratum.

Medium superiority and High release are separate sequential claims with separate evidence ledgers and stopping decisions:

- **Medium superiority** stops positive only when the 95% lower confidence bound for `Medium - baseline` task utility is greater than `0`, all applicable strata have entered the sequence, and the hard gates pass. It stops for harm when the 95% upper bound is below `0` or a hard safety gate fails.
- **High release** stops positive only when the 95% lower bound for `High - baseline` is greater than `0`, the lower bound for `High - Medium` is greater than `-0.25`, all High-applicable strata have entered the sequence, and the hard gates pass. The `0.25` non-inferiority margin is one quarter of a single operational utility grade; changing it requires a new predeclared evaluation version.
- Either claim stops `INCONCLUSIVE` when its approved budget is exhausted without crossing a boundary.

Medium evidence cannot stop the High ledger. Medium may be released with a Medium-only reliability claim while High remains disabled or explicitly experimental; High cannot be presented as validated until its own boundary clears. Budget exhaustion without a clear result never permits a reliability claim for the affected tier.

### 25.3 Prospective Lane

Maintain a small rolling set of unresolved questions or hidden local experiments. Record the prediction, candidate alternatives, evidence, uncertainty, and timestamp before the outcome or experiment is revealed. After resolution, score accuracy, calibration, missed factors, and belief updates. Only resolved outcomes may justify reusable harness guidance.

Prospective tasks supplement the regression and paired lanes; they do not block every release on calendar time.

### 25.4 Baseline Protocol

The baseline is a single direct Deep Research submission using the original research target, framing assumptions, exclusions, and requested output language. It receives no v2 state, hypotheses, verification plan, local experiment results, or expected-answer information. It runs in a fresh context.

When Medium uses a Deep Research provider, the primary baseline uses that same provider and effort level so the comparison measures Organizer value rather than provider choice. When the host exposes a distinct built-in Deep Research product, record it as an additional baseline arm rather than silently substituting it. If a task is resolved by Medium without a Deep Research call, compare it with the least expensive direct Deep Research option that would ordinarily be used for that task and report the asymmetry explicitly.

All arms receive the same task-local public inputs. Local project inspection is intentionally available only to the harness arms because project applicability is one of the proposed system's product advantages; evaluation reports must separate general factual quality from project-applicability quality so this advantage does not hide regressions in either dimension.

Record:

- load-bearing claim accuracy;
- claim-source entailment;
- primary-source use;
- true source-origin independence;
- project applicability;
- recommendation correctness;
- calibration and false `PASS` rate;
- `PARTIAL` and `BLOCKED` rate, including the opportunity cost of avoidable abstention;
- safe-action coverage: how often the system identifies a useful reversible action without overstating evidence;
- external physical calls;
- host search/fetch actions;
- Organizer context characters or tokens admitted;
- primary-source hit rate by scout route;
- realized state changes and `zero_gain` actions;
- wall time;
- actual reported API spend.

Use deterministic answer keys and local experiments where possible. For qualitative judgments, use blinded prompts that omit the expected winner and intended design, with at least two independent model families or a human adjudicator for disagreements. Report task-level utility distributions and every secondary diagnostic by arm and stratum; do not collapse them into an undocumented composite score.

Release gates:

- zero quota violations across every lane;
- zero untraceable load-bearing claims in Medium and High outputs;
- zero false `PASS` outcomes on adversarial trap tasks;
- paired evidence that Medium clears the task-utility superiority boundary over the direct baseline without exceeding its call envelope;
- paired evidence that improvement is not explained solely by excessive `PARTIAL` or `BLOCKED` outcomes;
- when High is enabled as validated, paired evidence that it clears both the baseline-superiority and Medium-non-inferiority boundaries in High-applicable strata;
- no coverage-matrix category shows a regression hidden by the aggregate result;
- Scout Router decisions report both external spend and host-context cost;
- all evaluation artifacts and adjudication prompts are retained for review.

If a hard gate fails, the harness must not claim that it is more reliable than direct Deep Research. If the paid paired result is inconclusive, retain that status, revise the evaluation design or budget through review, and do not convert uncertainty into a positive claim.

## 26. Rollout Sequence

### Phase 1: Deterministic Foundation

- physical-call quota and attempt ledger;
- session directory and canonical JSON state;
- raw artifact preservation and hashes;
- state schema and universal validator gates.

### Phase 2: Organizer Protocol

- posture classification and contract card;
- host retrieval and local experiment bindings;
- adaptive cycle and reserved-capacity rules;
- evidence, independence, and inference-joint model;
- `PASS`, `PARTIAL`, and `BLOCKED` delivery.

### Phase 3: Worker and Processor Boundaries

- provider adapter split where required;
- `cascade` physical-call enforcement;
- optional DeepSeek JSON audit mode and excerpt validation;
- fresh-context capability detection and honest downgrade labels.

### Phase 4: Evaluation and Calibration

- updated transcripts and epistemic fixtures;
- coverage-matrix regression, paid paired, and prospective evaluation lanes;
- predeclared sequential stopping rule and evaluation budget;
- Scout Router comparison for Host WebSearch versus Sonar by problem shape;
- quota and routing calibration based on retained evidence;
- forward tests on real development research prompts.

### Phase 5: Human View

- deterministic HTML renderer;
- stale-hash validation;
- compact machine-view command;
- re-run artifact and end-to-end evaluation gates after integration.

## 27. Success Criteria

The design is implemented successfully when:

1. Every harness-managed outbound network request is pre-authorized and mechanically bounded by a research, network-experiment, or transport ceiling; requested host-native retrieval is predeclared and logged within the stated observability limitation.
2. The current host model can complete a run without a hard-coded provider pipeline.
3. Ambiguous difficult problems execute an adaptive scientific loop rather than a citation-collection routine.
4. Narrow source-of-record problems avoid artificial hypotheses and unnecessary calls.
5. Local experiments affect project-applicability status and recommendations.
6. No worker or processor can directly establish the final verdict.
7. Canonical state has complete claim-to-evidence-to-artifact lineage.
8. Human HTML is reproducible from state and cannot become silently stale.
9. Medium and High fail closed when load-bearing gates do not pass.
10. The comparative evaluation release gates are satisfied without a fixed-count or aggregate-only shortcut.

## 28. Superseded Design Ideas

The following discussed ideas are intentionally not adopted:

- fixed multi-provider pipelines for each tier;
- model agreement as corroboration;
- mandatory competing hypotheses for lookup questions;
- default DeepSeek processing in Medium;
- two DeepSeek calls as a standard High requirement;
- `cascade` as a routine first wave;
- a fixed tool preference order that always uses Host WebSearch before Sonar;
- independent Host, probe, and Deep quotas that encourage every maximum to be spent in one run;
- a fixed 16-task suite and `12/16` release threshold without variance or power analysis;
- requiring providers to emit canonical branch-level conclusions instead of retaining raw output and validating minimal evidence deltas;
- persisted `handoff.json` alongside another semantic state;
- full generated Markdown reports in addition to HTML;
- dollar estimates as enforceable hard caps;
- running every permitted call even when the gate already passes.

These choices may be revisited only when retained evaluation evidence demonstrates a measurable quality or cost benefit.
