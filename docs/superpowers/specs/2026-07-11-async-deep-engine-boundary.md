# Async Deep-Engine Boundary (DRAFT — implement after adapter wave 2 lands)

Status: locked v1 2026-07-11

Deep research engines (perplexity sonar-deep-research, openai deep-research,
gemini deep research) are asynchronous: submit, poll for minutes, harvest.
This spec extends the v2 request boundary to async routes without weakening
any invariant the sync path enforces.

## Non-negotiable inheritances

- One permit, one physical request: the submission consumes the `deep`
  permit; every poll consumes a `transport` permit. Nothing refunds.
- The provider job token is journaled at acceptance time in the event
  journal (`attempt_status` details) — a killed session never loses a paid
  submission. This is the v1 ledger-at-submission lesson, upgraded: the
  journal is hash-chained.
- Raw terminal payloads are spooled before extraction; extraction failure
  leaves the job harvestable at zero marginal cost.
- Submissions are NEVER auto-resubmitted. Timeout or crash → `uncertain`,
  and recovery goes through resume, not re-pay (v2 decisions ledger).

## Lifecycle

Both the `deep` and `transport` categories below share a single contract
stage, `investigation` — not separate `deep_investigation` / `deep_transport`
stages. This matches §7.1 of
docs/superpowers/specs/2026-07-10-adaptive-scientific-research-harness-design.md
("investigation | ... | each accepted submission=`deep`", with `transport`
defined there as "one poll, resume, stream reconnect, or artifact-download
request that harvests an already authorized job without initiating or
expanding research") and the pre-existing openai/gemini candidate registry
records, which already carry `stage_capabilities: ["investigation",
"anti_lock_in"]` and `request_multiplicity: {"deep": 1, "transport": 1}`. The
perplexity route follows the same convention.

```
acquire(deep)      permit_acquired            (deep permit consumed)
submit             attempted -> accepted      details: {job: "provider:id"}
poll xN            transport permits, backoff 15s -> 30s -> 60s -> 120s cap
terminal:
  completed        occurrence written by code; raw payload spooled;
                   optional ingest_provider_artifact under storage rights
  failed           provider-terminal state; permit stays consumed
  uncertain        wall-time exhausted or poll transport died;
                   job token remains harvestable via a later deep-poll
                   (which auto-resumes it — see Resume below)
```

Poll accounting is honest: every poll GET is a physical transport request.
A 20-minute engine at the backoff schedule costs ~14 transport requests;
contract templates for deep tiers budget `transport` ceilings accordingly
(rule of thumb: 20 transport per reserved deep invocation).

## Adapter protocol extension

Sync adapters export `build/parse`. Async adapters export:

- `submit(query, env) -> RequestSpec` — the paid POST; never retried.
- `job_token(payload) -> str` — extract the BARE provider-native job id from
  the accept body (no prefix). The boundary composes `"provider:id"` itself
  at the journaling site, in `execute_deep_submit`, when it writes the
  `accepted` attempt-status details — adapters never see or produce the
  prefixed form.
- `poll(token, env) -> RequestSpec` — one status GET.
- `extract(payload) -> ParsedResult | None` — None means still running;
  raises AdapterParseError on terminal-but-malformed (payload already
  spooled by the boundary before extract is called).

The registry drives dispatch: `transport.mode: "async"` routes require the
async quadruple; `"sync"` routes require the pair. `_bound_route` refuses
mismatches.

## Resume

There is no separate `deep-resume` verb. Resume is folded into `deep-poll`:
calling `deep-poll` against an `uncertain` deep action first auto-journals
the `uncertain -> accepted` transition (details `{"resume": true}`), then
performs the one physical poll under the freshly acquired `transport`
permit — same command, same attempt chain as any other poll.
`uncertain -> accepted` is the only transition out of `uncertain` in
`quota.ATTEMPT_TRANSITIONS`.

- `research_state.py deep-pending <session>`: scan the event journal for
  accepted-without-terminal (`accepted` or `uncertain`) deep actions; print
  job tokens. Free, no network.
- `research_state.py deep-poll <session> --action-id D --poll-action-id T`:
  the only way to advance an `uncertain` action — see above. `--action-id`
  is the deep action being polled; `--poll-action-id` is a freshly acquired
  `transport` permit action.
- `research_state.py deep-timeout <session> --action-id D`: free, no-network
  wall-clock check that moves a stuck `accepted` action to `uncertain` once
  `external.max_wall_time_seconds` has elapsed since the ORIGINAL
  submission. Stays its own operation, separate from `deep-poll`
  (idempotent, side-effect-free no-op when there's nothing to do).

## Deliberately out of scope

- Provider-side cancellation (money is already spent; harvesting beats
  cancelling).
- Streaming partials (deep engines do not stream usefully today).
- Any cross-session learning (user verdict: closed).

## Acceptance

- Fixture-replay tests for submit/poll/extract per async adapter, including
  terminal-failure, still-running, malformed-terminal, and wall-timeout →
  uncertain → resume → completed.
- One live perplexity deep run (~$0.5, needs explicit budget nod) as the
  first async adoption evidence; openai/gemini follow the same pattern.
