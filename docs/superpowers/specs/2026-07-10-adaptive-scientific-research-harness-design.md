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

The harness cannot guarantee truth. It guarantees a fail-closed process: unresolved load-bearing claims cannot be presented as a passing conclusion. A run ends as `PASS`, `PARTIAL`, or `BLOCKED`.

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
- cap external spend using physical-call quotas that the user approves before execution;
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

Required behavior:

- run the applicable lookup, synthesis, or scientific reasoning underneath the decision;
- identify the recommendation's load-bearing premises and inference joints;
- consider reversibility, cost of error, and option value;
- verify project applicability with a local experiment when feasible;
- separate evidence from Organizer judgment;
- map uncertainty to an engineering posture: invariant, reversible abstraction, experiment, or research debt.

## 7. Cost Tiers

Quotas are ceilings, not spending targets. The Organizer must stop early when the evidence gate is satisfied. The initial defaults below are release candidates and may change only through documented evaluation results.

| Tier | Adaptive cycles | Host retrieval waves | External probes | Deep Research calls | Processor calls |
|---|---:|---:|---:|---:|---:|
| `low` | 1 | 1 | 2 | 0 | 0 |
| `medium` | 2 | 2 | 3 | 1 | 0 by default |
| `high` | up to 3 | 3 | 4 | 2 | optional 1 |

A host retrieval wave is one bounded batch aimed at one to three load-bearing claims. It may contain host-native searches and direct fetches. Host actions do not consume external-call quota, but the state records search count, fetch count, wall time, target claims, and outcome.

The Organizer may recommend a custom card when the default quota cannot execute the intended action. For example, the existing `cascade` action requires four probe permits and therefore does not fit the default `low` or `medium` tier. The user must explicitly approve a custom probe ceiling before it runs.

### 7.1 Low

Use for narrow facts, quick orientation, or one decisive scientific check.

The run may pass only when the conclusion is narrow enough for one cycle. It must not claim decision-grade coverage for an ambiguous, multi-premise question.

### 7.2 Medium

Use for reversible implementation, prototypes, technical design, and ordinary literature or product research.

The intended allocation is:

- host framing and a bounded discovery wave;
- at most one sharpened Deep Research call when cheap evidence leaves meaningful gaps;
- direct source and local applicability checks;
- a reserved second adaptive cycle for replication, adjudication, or reframing;
- a final inference-joint review.

The exact three-probe allocation is selected by the Organizer, but it must preserve at least one probe permit after the first synthesis unless the run has already passed and stops early.

### 7.3 High

Use for costly, difficult-to-reverse, contested, or high-consequence decisions.

The intended allocation is:

- host framing, primary-source retrieval, and local inspection;
- one Deep Research branch for broad evidence coverage when needed;
- direct verification of load-bearing claims;
- a second Deep Research branch from another retrieval family, shaped by the first branch's weakest hypothesis or inference joint;
- targeted final adjudication;
- a context-blind adversarial review when the host can provide a fresh context;
- optional DeepSeek analyst audit when it adds real analyst-model independence or relieves context pressure.

The second Deep Research call must not repeat the first broad query. If no unresolved empirical or coverage gap justifies it, it remains unused.

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
Host retrieval waves: <=<n>
External quota: probes<=<n>, deep<=<n>, processor<=<n>
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

Choose the observation with the highest expected decision value under the remaining quota. Prefer, in order:

1. free reasoning over existing evidence;
2. direct local inspection or experiment;
3. host WebSearch and direct fetch;
4. specialized free retrieval such as Semantic Scholar;
5. narrow external probe for a specific gap or alternate index;
6. Deep Research for broad unresolved coverage;
7. optional processor for context offload or analyst diversity.

This is a preference order, not a mandatory ladder. The Organizer may skip directly to the cheapest decisive action.

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
- attach exact or normalized excerpts for load-bearing evidence;
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

### 9.8 Verify and Terminate

Run the posture- and tier-specific quality gates. Stop when all load-bearing claims pass, when quota is exhausted, when the missing evidence is unavailable, or when another call has negligible expected decision value.

Return `PASS` only when every required gate passes. Return `PARTIAL` when some useful conclusions survive but at least one non-fatal load-bearing gap remains. Return `BLOCKED` when a critical claim cannot be established or the available evidence does not support a responsible recommendation.

## 10. Host WebSearch and Fetch

Host retrieval is the default precision instrument when available.

Discovery and verification are separate passes:

- **Discovery pass** identifies candidate answers, vocabulary, sources, and plausible alternatives.
- **Verification pass** receives the exact claim and its falsifier, not the Organizer's confidence language, and searches for primary evidence, counterexamples, limitations, and shared upstream origins.

Search snippets are discovery metadata. They never clear an evidence gate. The Organizer must fetch and inspect the underlying source.

Host search may share an index family with an external worker. Independence is judged by final source origin, not by tool name.

If host retrieval is unavailable, the contract card discloses the substitution and may recommend more external probe permits.

## 11. Local Experiments

Local experiments are a core differentiator from standalone Deep Research.

Use them when a claim concerns the current codebase, dependency version, operating system, runtime, API behavior, data shape, performance, or compatibility. Examples include:

- inspecting installed versions and lockfiles;
- reading actual dependency source or generated types;
- running a minimal reproducer in a temporary or project-sanctioned location;
- executing a focused benchmark;
- checking a live response schema against current code;
- testing an integration against non-production fixtures.

Local experiments must be read-only or safely reversible unless the user separately authorizes broader changes. They must not mutate production systems or send local files externally without approval.

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

The budget unit is an outbound physical research or processor request, not a logical CLI command.

Rules:

- acquire a permit before every paid or externally metered POST attempt;
- a Sonar retry consumes another probe permit;
- `cascade` atomically reserves four probe permits before launching;
- no retry may exceed the remaining quota;
- a Deep Research submit attempt consumes one deep permit before the POST;
- a DeepSeek request consumes one processor permit before the POST;
- async polling and `--resume` do not consume a new research permit;
- local validation failures consume no permit because no outbound request occurs;
- no automatic quota refund occurs after an outbound attempt, even when acceptance is uncertain;
- list prices and actual dollars are recorded but never substitute for physical-call enforcement.

Ledger events distinguish `attempted`, `accepted`, `completed`, `failed`, `interrupted`, and `uncertain`. The contract report shows both logical actions and physical attempts.

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

Evidence records contain artifact ID, source ID, source tier, origin ID, retrieved-at or published-at date, exact or normalized excerpt, entailment status, and applicability notes.

Source tiers remain:

- `T1`: source of record or primary evidence;
- `T2`: quality secondary source tied to primaries;
- `T3`: aggregator, UGC, SEO content, or uncited model prose.

Claim statuses remain compatible with the current vocabulary: `corroborated`, `single-source`, `corroborated-same-family`, `disputed`, `retired`, and `unverified`.

Entailment is recorded separately as `entailed`, `partially-entailed`, `contradicted`, or `not-checked`.

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

## 17. Quality Gates

### 17.1 Universal Gates

Before `PASS`:

- every load-bearing claim has a recognized status;
- every load-bearing claim traces to evidence and raw artifacts;
- exact excerpts or direct local observations support each load-bearing claim;
- volatile facts carry an evidence date;
- unresolved contradictions are either adjudicated or reflected in status;
- recommendation and evidence are separate;
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
- project applicability is checked locally when feasible;
- reversibility and cost of error influence the recommendation;
- unresolved critical claims force `PARTIAL` or `BLOCKED`.

### 17.6 Tier Gate

- Low passes only a narrow conclusion supported by one cycle.
- Medium may support reversible implementation when all load-bearing claims for that action pass.
- High may support difficult-to-reverse decisions only after independent replication or equivalent primary/local evidence and adversarial joint review.

## 18. Delivery Status

### PASS

All posture- and tier-specific gates pass. The recommendation may still include bounded uncertainty, but no unresolved issue can plausibly flip the stated action within its scope.

### PARTIAL

The research produced useful, traceable findings, but at least one load-bearing gap remains. Delivery must state which development actions are safe, which must remain reversible, and what would close the gap.

### BLOCKED

A critical source, local condition, vendor artifact, or observation is unavailable, or available evidence cannot support a responsible recommendation. Delivery must state why more generic model calls are unlikely to help.

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
inference_joints
engineering_handoff
open_questions
verification
artifact_index
```

State updates use validated patches and atomic replacement. The Organizer never regenerates the entire file from prose when a small patch is sufficient.

### 20.2 events.jsonl

Append-only operational history only: contract confirmation, quota permits, worker attempts, submit IDs, resume tokens, completion, failure, cost, wall time, state revision, and report generation. It must not hold a competing prose summary.

### 20.3 raw/

Immutable provider responses, fetched-source snapshots when permitted, local experiment outputs, and processor outputs. Every artifact has a SHA-256 recorded in `state.json`.

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
- secrets, API keys, and `.env` contents never enter state or reports;
- local experiments avoid production systems and destructive actions.

## 22. Failure and Recovery

- harvest existing resume tokens before new spend;
- journal submit attempts before polling;
- never resubmit an accepted paid async job while a resume token exists;
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
- resume and poll do not consume new research permits;
- quota exhaustion fails closed;
- ledger events survive interruption and malformed trailing lines;
- state patches are atomic and schema-valid;
- artifact hashes detect mutation;
- HTML escaping prevents artifact injection;
- report hash detects stale output.

### 24.2 Provider Contract Tests

Use fixtures for success, timeout, terminal failure, schema drift, empty output, truncated output, missing citation lists, and raw-payload recovery. CI does not call paid providers.

### 24.3 Epistemic Scenario Tests

Fixtures must test:

- one claim repeated by many sources with one upstream origin;
- a citation that does not entail the claim;
- stale official documentation;
- conflicting primary sources;
- a locally installed version that contradicts generic web guidance;
- a Deep Research report with confident unsupported prose;
- a surprising observation that should trigger reframing;
- a missing vendor artifact that should produce `BLOCKED`;
- a processor-invented excerpt that must be rejected;
- quota exhaustion that must not produce false `PASS`.

### 24.4 Golden Transcripts

Keep structural transcripts, but update them to demonstrate posture selection, contract confirmation, quota permits, adaptive cycles, local experiments, quality gates, and engineering handoff. Structural transcript validation remains necessary but is not sufficient evidence of research quality.

## 25. Comparative Evaluation

The initial evaluation suite contains 16 paired tasks:

- 4 source-of-record or volatile-fact tasks;
- 4 ambiguous scientific or conflicting-evidence tasks;
- 4 development tasks with decisive local applicability checks;
- 4 adversarial trap tasks involving source echoes, stale evidence, missing artifacts, or false confidence.

Each task runs on the same date under three arms:

1. direct built-in Deep Research baseline;
2. `/deep` Medium;
3. `/deep` High.

### 25.1 Baseline Protocol

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
- external physical calls;
- host search/fetch actions;
- wall time;
- actual reported API spend.

Use deterministic answer keys and local experiments where possible. For qualitative judgments, use blinded prompts that omit the expected winner and intended design, with at least two independent model families or a human adjudicator for disagreements.

Release gates:

- zero quota violations across the suite;
- zero untraceable load-bearing claims in Medium and High outputs;
- zero false `PASS` outcomes on the four adversarial trap tasks;
- Medium wins or ties the direct baseline on at least 12 of 16 paired quality verdicts;
- Medium has a strictly lower false-confidence count than baseline;
- High wins or ties Medium on at least 12 of 16 paired quality verdicts;
- no task category shows a systematic regression hidden by the aggregate result;
- all evaluation artifacts and adjudication prompts are retained for review.

If these gates fail, the harness must not claim that it is more reliable than direct Deep Research. Revise the protocol, routing, or quotas and rerun the affected suite.

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
- 16-task paired baseline evaluation;
- quota and routing calibration based on retained evidence;
- forward tests on real development research prompts.

### Phase 5: Human View

- deterministic HTML renderer;
- stale-hash validation;
- compact machine-view command;
- re-run artifact and end-to-end evaluation gates after integration.

## 27. Success Criteria

The design is implemented successfully when:

1. Every external call is pre-authorized and mechanically quota-bound.
2. The current host model can complete a run without a hard-coded provider pipeline.
3. Ambiguous difficult problems execute an adaptive scientific loop rather than a citation-collection routine.
4. Narrow source-of-record problems avoid artificial hypotheses and unnecessary calls.
5. Local experiments affect project-applicability status and recommendations.
6. No worker or processor can directly establish the final verdict.
7. Canonical state has complete claim-to-evidence-to-artifact lineage.
8. Human HTML is reproducible from state and cannot become silently stale.
9. Medium and High fail closed when load-bearing gates do not pass.
10. The comparative evaluation release gates are satisfied.

## 28. Superseded Design Ideas

The following discussed ideas are intentionally not adopted:

- fixed multi-provider pipelines for each tier;
- model agreement as corroboration;
- mandatory competing hypotheses for lookup questions;
- default DeepSeek processing in Medium;
- two DeepSeek calls as a standard High requirement;
- `cascade` as a routine first wave;
- persisted `handoff.json` alongside another semantic state;
- full generated Markdown reports in addition to HTML;
- dollar estimates as enforceable hard caps;
- running every permitted call even when the gate already passes.

These choices may be revisited only when retained evaluation evidence demonstrates a measurable quality or cost benefit.
