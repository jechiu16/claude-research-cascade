# V2 Research Harness Session Decisions

This file is the alignment ledger for the design session that produced the v2 harness specification. It summarizes user-confirmed decisions, rejected alternatives, unresolved proof obligations, and the current implementation boundary. It is not a substitute for the normative design spec.

## North Star

Build one explicit-trigger research skill that supports architecture and other difficult development decisions inside the current session. It must offer user-controlled cost, sufficient depth, fail-closed reliability, scientific handling of ambiguous problems, efficient use of frontier model reasoning, and a simple host-neutral implementation suitable for a high-quality public repository.

## Confirmed Product Decisions

| Decision | Session conclusion | Alignment check |
|---|---|---|
| Trigger | Only explicit `/deep` activates the harness. Ordinary research requests do not. | Host bindings and examples must preserve explicit trigger semantics. |
| Spend authority | Every run presents a contract card and waits for user confirmation before research spend or external execution. The user pulls the trigger, and confirmation binds the normalized card, resolved registry, and referenced route records by hash. | Runtime refuses initialization or permits when confirmation or any bound hash differs. |
| Cost control | Control physical request counts, not nominal Deep Research dollar price. Price remains an estimate because one call has variable provider-side work. Logical route invocations are shown separately from physical requests so a composite route cannot hide fan-out. | Contract and ledger expose exact invocation/request ceilings and measured cost separately. |
| User-facing axes | Use `epistemic posture x cost tier`, not `depth x independence x strictness`. | Canonical contract and runtime docs use only the v2 axes. |
| Cost tiers | Preserve Low, Medium, and High. A tier limits stage capacity rather than granting unrelated maxima that invite every tool to run. | Stage permit map expands to exact route-specific ceilings. |
| Organizer | The current selected host model is the Organizer. Do not hardcode Sonnet, Luna, or another model. | Core runtime contains no Organizer model identifier requirement. |
| Scientific behavior | Ambiguous scientific and decision problems use hypotheses, falsifiers, discriminating checks, surprise-driven reframing, and inference-joint verification. Narrow lookup problems avoid artificial hypothesis theater. | Posture-specific gates and fixtures distinguish lookup from scientific/decision work. |
| Reinforcement | Medium and High both retain adaptive post-result reinforcement. Medium reserves one challenge; High adds another challenge/adjudication capacity and context-separated verification. | Tier gates and permit map prevent discovery from consuming reserved capacity. |
| Anti-lock-in | A provisional conclusion in Medium/High scientific or decision posture triggers an explicit disconfirming checkpoint. | `PASS` validation requires the checkpoint record when applicable. |
| Coverage audit | Medium/High scientific or decision work checks omitted premises and boundary conditions. This reduces omission risk but does not prove unknown-unknown completeness. | Delivery and report keep the limitation visible. |
| Tool palette | Existing APIs are the credential-verified baseline, not a product boundary. Current recommendation is direct source-of-record APIs by domain, Brave as the first independent general-index addition, OpenAlex/Crossref/Europe PMC for scholarly coverage, an Exa-versus-Mojeek query-class benchmark, and Jina/Firecrawl only after classified fetch failures. Other providers remain disabled candidates. Credential or legacy-CLI readiness is not v2 execution readiness. | Core runtime uses a capability registry rather than hard-coded provider pipelines; external routes stay disabled until adapter/version, common request boundary, preflight, policy, and adoption evidence all pass. |
| Scout choice | Choose exactly one primary scout route by problem shape. Prefer direct source-of-record access for canonical development facts, host retrieval for known targets, an enabled independent or semantic index for open discovery, scholarly routes for papers, and local inspection for project truth. | Contract records route, index family, one logical scout invocation, and exact physical request expansion; runtime rejects hidden multi-scout fan-out. |
| Deep Research | Deep Research is an optional investigation action, not the default scout and not a required call in every tier. | Unused deep capacity remains unspent. |
| DeepSeek | Optional cheap supplied-material processor or blind analyst audit. It adds analyst diversity, not source-origin independence, and is not default Medium retrieval. | Processor cannot write canonical state or clear empirical corroboration alone. |
| Branch output | Do not trust providers to emit canonical conclusions. Preserve raw output, build deterministic branch manifests, and accept only validated minimal evidence deltas. | Worker integration must validate IDs, excerpts, and lineage before promotion. |
| Canonical artifacts | Use canonical JSON plus deterministic human-readable HTML. Do not persist a second full Markdown report. A compact Markdown/JSON projection may be emitted to stdout for host consumption. Confirmed contract, capability snapshot, and session identity are immutable; generic patches and arbitrary reserved-event append are forbidden. | `state.json` is semantic truth; transition-kind allowlists and HTML state hash prevent silent drift. |
| Information preservation | Load-bearing evidence keeps exact excerpts and raw offsets. Normalized excerpts are allowed only for non-load-bearing convenience. | Validator rejects invented or missing load-bearing excerpts. |
| Independence | Multiple models or retrieval tools do not create source independence when they cite one upstream origin. | Promotion rules use source-origin IDs, not model votes. |
| Non-vacuous PASS | `PASS` requires a non-empty bounded answer, a non-empty exact load-bearing claim set, and the contract evidence floor. Universal quantification over an empty claim list is not success. | Validator has explicit empty-answer, empty-claim-set, ID-agreement, and evidence-floor failures. |
| High verifier | High cannot return `PASS` without a context-separated verifier that did not produce the candidate conclusion. | Hard validation gate. |
| Host context | Host search may be zero marginal API dollars but still costs tokens, latency, and attention. Track admitted context and acknowledge host-native observability limits. | Contract shows host context class and admitted-evidence ceiling. |
| Local experiments | Local project evidence is a first-class differentiator. Pure local actions have no network egress; live integration requests use explicit network-experiment permits. | Runtime accounting cannot hide external requests under `local`. |
| Async safety | Accepted-but-unconfirmed submissions consume permits and become `uncertain`; they are never automatically resubmitted. Poll/resume/download requests consume bounded transport slots. Event appends use recoverable byte-boundary transactions; only owned partial tails may be repaired. | Event state machine and recovery tests cover uncertainty, transport ceilings, partial writes, and unowned corruption. |
| Raw retention | Artifacts carry hash, size, media type, sensitivity, retention, availability, origin/provenance IDs, snapshotted storage-rights decision, and HTML policy. Purging load-bearing evidence invalidates `PASS`; a persisted pending transition is the only authorization for crash recovery, revalidation, and rerender. | Typed ingestion rejects origin-free or policy-incompatible provider payloads; purge is a resumable semantic transition, not filesystem-only deletion. |
| Delivery | Final research output is optimized for continuing development: safe invariants, reversible assumptions, disputes, experiments, acceptance tests, flip conditions, and research debt. | HTML and machine view expose engineering handoff fields. |

## Evaluation Decisions

| Decision | Session conclusion | Alignment check |
|---|---|---|
| Fixed suite | Do not hardcode a 16-task suite or `12/16` gate without variance or power evidence. | Evaluation uses a coverage matrix and predeclared sequential stopping. |
| Paired baseline | Compare direct Deep Research against `/deep` Medium and applicable High tasks under comparable inputs. | Baseline stays blind to v2 state and local results. |
| Statistical unit | Independent task is the paired unit; repeated runs estimate within-task variance and are not independent samples. | Evaluation code must avoid pseudoreplication. |
| Utility | Score factual reliability together with useful safe action, false `PASS`, and avoidable abstention. | Primary utility and secondary diagnostics are both retained. |
| Tier claims | Medium superiority and High release have separate ledgers and stopping rules. Medium evidence cannot validate High. | Release labels are tier-specific. |
| Prospective evidence | Keep a small prospective lane for unresolved predictions or hidden local outcomes. Only resolved outcomes may update reusable guidance. | Self-improvement never trains on unresolved self-judgment. |
| Paid tests | No paid paired run occurs without an explicit evaluation call budget. | Current deterministic implementation slice makes zero paid calls. |
| Provider adoption | A new route is enabled only for declared query strata after hard lifecycle/privacy/retention/provenance gates and sequential evidence of material marginal value. | Registry defaults new candidates to disabled and snapshots historical route meaning. |

## Provider-Portfolio Decision

The official-source landscape study found no universal provider stack. The optimal architecture is a capability portfolio with one primary route, source-of-record shortcuts, and conditional escalation by index family. Generic Google-plus-Brave concurrency is not the default: Google Custom Search is closed to new customers and sunsetting, Gemini grounding and SERP wrappers are Google-origin model/wrapper routes rather than a second independent family, and ordinary Medium work benefits from sequential query sharpening. High may pre-authorize two-family parallelism only when latency and expected unique-origin gain justify both request counts.

The current adoption order is: implement the registry and common occurrence schema; add high-use direct authoritative adapters; add Brave; add OpenAlex/Crossref/Europe PMC; benchmark Exa against Mojeek by query class; add Jina or Firecrawl only after measured host-fetch failures. Search occurrences, canonical documents, and exact claim support remain separate identities. Retrieval agreement, duplicate URLs, shared press releases, and model agreement do not become source corroboration. No new key is requested until its adapter fixtures and named benchmark budget are ready.

## Discoverative Intelligence Comparison

The Apodex/FutureFlow comparison contributed five ideas worth retaining: explicit anti-lock-in after a provisional candidate, trajectory evidence rather than model voting, structural verifier separation, prospective/live evaluation, and realized information gain. The design intentionally rejects 150-agent scale, automatic self-evolution from unresolved outcomes, generic numeric confidence theater, and literal verification of every step.

## Rejected Architectures

- Fixed provider pipelines per tier.
- Treating the currently installed APIs as a permanent boundary.
- Concurrent Google-origin plus Brave search on every query.
- Counting wrappers, provider brands, or fetch services as independent source origins.
- Generic search when a recognized source-of-record API can answer the canonical fact directly.
- Always using Host WebSearch before Sonar or always using both.
- Independent Host/probe/deep maxima that encourage spending every allowance.
- Routine `cascade` first wave.
- Default DeepSeek processing in Medium or two standard DeepSeek calls in High.
- Worker/model agreement as empirical corroboration.
- Mandatory competing hypotheses for source-of-record lookup.
- Provider-generated canonical branch conclusions.
- Full persisted Markdown plus HTML plus JSON duplicates.
- Dollar estimates presented as enforceable hard caps.
- Fixed 16-task release proof.

## Credential and Runtime Readiness

- Global Codex and Claude skill installations share the same user-protected credential file.
- Current credential doctor reports demo, Scholar/S2, Sonar, cascade, Perplexity, OpenAI, Gemini, and DeepSeek ready; this does not enable those external routes in v2 before request-boundary integration.
- No additional provider key is needed for the deterministic foundation, and no paid provider call has been made during portfolio design.
- The credential itself must never appear in state, reports, tests, diffs, or command output.
- One unrelated pre-existing OpenAI async job exists in the `parallax` reports ledger; v2 work must not resume or resubmit it accidentally.

## Current Implementation Boundary

The historical branch baseline was v1: Markdown state, legacy three-axis contracts, advisory rather than mechanical quota, and Markdown worker reports. Commits through `bd54525` implement the deterministic v2 foundation and its CLI.

The first implementation slice covers hash-bound confirmed contracts, a versioned capability registry and immutable snapshot, secret-free preflight, canonical JSON, validated atomic state/events with owned-tail recovery, exact stage-scoped permit enforcement, provenance/storage-rights-gated raw ingestion, resumable purge plus validation/rerender, fail-closed lineage validation with positive PASS fixtures, stale-report detection, deterministic HTML, host-neutral CLI, and runtime documentation. All external network routes remain disabled in this slice. New/bound provider adapters, result fusion, worker transport enforcement, full Organizer adaptive protocol, comparative/provider adoption evaluation, installer polish, CI, and public release remain named follow-on plans and must not be claimed complete after the first slice.

## Task 8 Alignment Audit

Status vocabulary: `implemented` means code, deterministic tests, and runtime-facing docs agree in this slice. `deferred` means the current slice does not claim the property and names its follow-on. `contradicted` would block the slice. This audit found no `contradicted` row.

### Product Decisions

| Decision | Status | Evidence or named follow-on |
|---|---|---|
| Trigger | implemented | `SKILL.md`, `AGENTS.md`, and docs tests retain explicit `/deep` activation. |
| Spend authority | implemented | Triple-hash contract confirmation, init/pre-permit rejection, and CLI tamper tests. |
| Cost control | implemented | Exact physical ceilings, route multiplicity, atomic reservation, and uncertain-attempt consumption. |
| User-facing axes | implemented | Contract schema and runtime docs use posture and tier. |
| Cost tiers | deferred | Exact stage maps work, but canonical Low/Medium/High template construction and minimum tier semantics belong to the Organizer-protocol follow-on. |
| Organizer | implemented | Runtime stores no hard-coded Organizer model; host binding uses the selected model. |
| Scientific behavior | deferred | State sections and some gates exist; prediction packets, surprise-driven transition checks, and full posture fixtures belong to the Organizer-protocol follow-on. |
| Reinforcement | implemented | Medium/High require reserved post-result capacity; High additionally requires a distinct context-separated verifier stage and completed permit-bound verifier record. |
| Anti-lock-in | implemented | Medium/High scientific or decision `PASS` requires a completed checkpoint record. |
| Coverage audit | implemented | Applicable `PASS` requires a completed audit with omission dispositions. |
| Tool palette | deferred | Registry and candidate policy are implemented; direct-source, Brave, scholarly, and fetch-fallback worker adapters remain in the provider-portfolio follow-on. |
| Scout choice | implemented | Contract requires exactly one logical primary scout and provider-declared physical multiplicity. |
| Deep Research | deferred | Optional route semantics are designed, but external Deep Research worker adapters remain disabled pending the request boundary. |
| DeepSeek | deferred | Processor policy is designed, but typed processor operation and adapter remain disabled. |
| Branch output | deferred | Canonical sections exist; deterministic branch-manifest and evidence-delta validators remain in the Organizer/worker follow-on. |
| Canonical artifacts | implemented | Canonical JSON, immutable contract/capabilities, typed patches, events, and deterministic HTML are tested. |
| Information preservation | implemented | Available evidence requires exact raw byte offsets and matching excerpts; invented/missing excerpts fail. |
| Independence | implemented | Load-bearing claim type is explicit; empirical `PASS` requires two independent evidence origins, while source-of-record claims require direct T1 evidence. |
| Non-vacuous PASS | implemented | Empty answer, empty/mismatched load-bearing set, and evidence-floor failures are tested. |
| High verifier | deferred | High now requires distinct reserved capacity and a completed permit-bound verifier record; trusted verifier-packet provenance and non-self-attestation remain in the worker/Organizer follow-on, so High is not release-validated. |
| Host context | deferred | Contract ceilings exist; adapter/Organizer admitted-character measurement remains in the request-boundary follow-on. |
| Local experiments | deferred | Local permits and no-egress envelope exist; typed experiment records and live integration request boundary remain in the Organizer follow-on. |
| Async safety | deferred | Attempt consumption and owned-tail WAL recovery are implemented; bounded polling/resume/download enforcement awaits external worker adapters. |
| Raw retention | implemented | Typed immutable ingest, secret floor, storage-rights gate, pending purge authorization, tombstones, recovery, validation, and rerender are tested. |
| Delivery | implemented | Canonical engineering handoff fields and deterministic HTML projection are available; quality of populated handoff content remains an Organizer responsibility. |

### Evaluation Decisions

| Decision | Status | Evidence or named follow-on |
|---|---|---|
| Fixed suite | deferred | Comparative evaluation runner will use a coverage matrix and sequential stopping, not a hard-coded 16-task proof. |
| Paired baseline | deferred | Blinded direct-baseline runner and comparable-input packets belong to the comparative-evaluation follow-on. |
| Statistical unit | deferred | Paired task-level aggregation and repeat handling belong to the comparative-evaluation follow-on. |
| Utility | deferred | Blinded adjudication and safe-action/false-PASS/avoidable-abstention scoring remain unimplemented. |
| Tier claims | deferred | Separate Medium and High evidence ledgers remain unimplemented; no superiority or High release claim is made. |
| Prospective evidence | deferred | Prospective prediction lane remains in the comparative-evaluation follow-on. |
| Paid tests | implemented | This slice makes zero paid provider calls; no future paid evaluation may run without an explicit call budget. |
| Provider adoption | deferred | Candidates default disabled and snapshot correctly; query-class benchmarks and sequential adoption ledgers remain in the provider-portfolio follow-on. |

## Alignment Checkpoint

At every task boundary:

1. Compare the diff against this ledger and the normative design spec.
2. Identify any confirmed decision the code contradicts.
3. Identify any behavior the current tests do not prove.
4. Mark scope outside the current slice as deferred by name, not silently omitted.
5. Re-run the relevant deterministic tests before committing.
6. Ask a blind reviewer for concrete Critical/High bypass, data-loss, privacy, and contract-drift findings before slice completion.
