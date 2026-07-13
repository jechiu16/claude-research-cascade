# /deep Organizer Harness

Internal runtime bridge for the public flow in [SKILL.md](SKILL.md). Read it
only after the user selects `light`, `standard`, or `heavy`.

## Product Contract

- The selected host is the Organizer and sole conclusion author.
- D1/D2 are untrusted discovery memos, never evidence or verdicts.
- Re-verification corrects or annotates; it never suppresses delivery.
- Counts, not token-price guesses, stop external calls.
- Deliver one machine truth (`state.json`) and one human projection
  (`report.html`), plus their journal and raw evidence.

An epistemically `BLOCKED` package is still delivered. Only integrity failure
means the report is unsafe to act on.
Evidence gaps render as `證據不足 / EVIDENCE_INSUFFICIENT`; incomplete handoff
fields render as `交付不完整 / DELIVERY_INCOMPLETE`.

## Runtime Bridge

`ROOT` is the absolute directory containing the canonical `SKILL.md`:

```bash
ROOT="/absolute/path/to/the/canonical-skill"
CLI="$ROOT/.venv/bin/deep-research-state"
SESSION="/absolute/path/to/this-run-package"
```

Before confirmation, the only permitted command is local and read-only:

```bash
"$CLI" card --question '<question>' --posture decision
```

After confirmation, bind and start one contract:

```bash
"$CLI" draft --question '<question>' --posture decision \
  --profile standard --json
"$CLI" prepare --contract "/absolute/path/to/draft-contract.json" --json
"$CLI" confirm --prepared "/absolute/path/to/prepared.json" \
  --card-sha256 '<hash>' --registry-sha256 '<hash>' \
  --referenced-records-sha256 '<hash>' --confirmed-at '<timestamp>' \
  --confirmed-by user --json
"$CLI" init "$SESSION" --contract "/absolute/path/to/confirmed-contract.json" --json
```

The choice on the public card is the only user confirmation. `prepare` and
`confirm` are internal hash-binding steps, not a second prompt.

## Contract Shape

New runs use the compatibility tier `custom` and these authoritative fields:

```json
{
  "research_workflow": "host_led_v1",
  "conclusion_author": "host",
  "provider_reports_role": "discovery_only",
  "durability": "canonical_package",
  "resource_envelope": {
    "cost_budget": {
      "profile": "standard",
      "deep": 1,
      "search": 15,
      "free": "unlimited"
    }
  }
}
```

Copy the chosen vector from `budget_profiles.json`; a user-controlled override
may change numbers but never names tools. Exact routes remain in
`stage_permit_map`, and physical/time/storage limits remain defense-in-depth.
Require one reserved `verification` mapping and one
`final_inference_review/organizer_pass/host` mapping.

## Provider Routing

`provider_registry.json` is the only tool registry. Each route declares
`cost_class: deep|search|free`; deep routes also declare `cost_rank`. New tools
enter a class, never a profile.

A present credential is not execution readiness. The adapter, storage policy,
request boundary, and required environment must all pass local preflight.

1. Prefer direct source-of-record or local routes.
2. For D1, choose the lowest-rank ready provider unless source fit or privacy
   justifies another card-disclosed candidate.
3. Use D2 only for a material challenge, new angle, or expansion selected by
   the host after seeing D1 and current evidence.
4. Never call a bundle merely because budget remains.

The request boundary reserves before sending. Failed or uncertain calls remain
consumed. Transport polls are physically bounded but are not another `deep`
submit.

## Research Loop

1. Frame the decision, assumptions, exclusions, and flip conditions.
2. Run D1 when `deep > 0`; pass its useful hypotheses, contradictions,
   citations, and bounded session context to the Organizer.
3. Let the Organizer choose the smallest targeted checks. Paid search routes
   consume `search`; host/local/direct free routes consume `free`.
4. Capture qualifying source bytes and reconcile every load-bearing claim:
   `claim -> evidence -> source + source_origin -> raw artifact`.
5. Correct claims disproved by direct evidence. Mark unresolved claims and
   their revisit trigger; do not convert model agreement into corroboration.
6. Add a `targeted_reverification` record covering the final load-bearing claim
   IDs, with corrected and unverifiable IDs plus a concise disposition.
7. The host writes the bounded decision and development handoff, then validates
   and renders.

Minimal re-verification record:

```json
{
  "id": "VR1",
  "kind": "targeted_reverification",
  "completed": true,
  "checked_claim_ids": ["C1"],
  "corrected_claim_ids": [],
  "unverifiable_claim_ids": [],
  "disposition": "直接來源支持 C1；未採用 D1 的兩個未驗證延伸。"
}
```

## Execution And Delivery

Use boundary-owned calls; do not send a separate paid permit:

```bash
"$CLI" execute "$SESSION" --action-id A1 --stage verification \
  --route openalex --query '<targeted query>' --json
"$CLI" deep-submit "$SESSION" --action-id D1 --stage investigation \
  --route perplexity --query '<bounded brief plus context>' --json
"$CLI" host-capture "$SESSION" --payload "/absolute/path/to/capture-file" \
  --artifact-id HC1 --source-url '<url>' --source-title '<title>' \
  --upstream-key '<upstream>' --fidelity host_rendered \
  --marginal-purpose '<claim or uncertainty checked>' --json
"$CLI" patch "$SESSION" --patch "/absolute/path/to/state-patch.json" --json
"$CLI" validate "$SESSION" --json
"$CLI" render "$SESSION" --json
```

If a call would exceed `deep` or `search`, the boundary sends nothing and
journals `budget_exhausted`. `render` adds the unresolved budget gap to
`state.json`, stops external work, and still writes `report.html`.

Human narrative fields, handoff, limitations, and recommendations are
Traditional Chinese. Preserve exact excerpts, titles, URLs, IDs, hashes,
provider names, and diagnostics. Acceptance tests use
`檢查方式 => 預期結果`.

## Recovery

```bash
"$CLI" status "$SESSION" --json
"$CLI" deep-pending "$SESSION" --json
"$CLI" recover "$SESSION" --json
"$CLI" render "$SESSION" --json
```

No token means a deep attempt is consumed and not pollable. A recorded token
may be polled with a new poll action ID; never resubmit the same deep action.
