---
name: deep
description: Portable /deep research trigger for Claude Code and OpenAI Codex. Use only when the user explicitly types /deep to start a bounded, evidence-gated research session.
---

# Agent Deep Research Trigger

This is the complete default protocol shared by
Claude Code and OpenAI Codex.
It makes `/deep` one host-native research trigger, not a visible orchestration
platform. The runtime is used only after the user explicitly types `/deep`.

<!-- PURE_TRIGGER_CARD_START -->
問題：{正規化後的問題}
建議：{層級}，因為{一個理由}
Low：只在對話中回答，附上連結。
Medium：為具名缺口補上直接取得的來源，並交付套件。
High：直接取得至少兩個不同來源，並交付套件。
額外付費請求：{精確數量}；本機資料外送：{是／否}。
開始：Low｜Medium｜High｜調整
<!-- PURE_TRIGGER_CARD_END -->

Choosing a tier is the only confirmation. `Adjust` changes the scope and shows
a new card; it does not start research. Do not expose kernel diagnostics in
the card or the normal happy path.

Any internal epistemic posture is Organizer bookkeeping, not a user-facing
choice; the card exposes only Low, Medium, and High.

## Default Flow

1. Normalize the question and recommend Low, Medium, or High with one reason.
2. Show the seven-line card above, including exact extra paid-request count
   and local-data egress. Ask only questions that change scope or cost.
3. Wait for exactly one choice. Host-native search, fetch, browser, local
   inspection, model reasoning, and subagents are the default actions.
4. Report phase-only progress: `frame` -> `gather` -> `check` -> `conclude` ->
   `deliver`. Do not narrate internal routing or accounting.
5. Low returns a bounded Traditional Chinese chat answer and links. It creates
   no package by default.
6. Medium adds a source only for a named gap, conflict, or decision risk. It
   always delivers canonical JSON and `zh-Hant-TW` HTML, including partial or
   blocked results.
7. High directly obtains at least two different sources, discloses shared
   upstreams, and applies the same package delivery rule. The machine proves
   lineage and diversity, never independence or truth.

External paid requests and local-data egress are semantic changes. Disclose
their exact enforceable counts before selection; an unapproved change starts a
new run rather than a second confirmation.

## Evidence And Delivery

Medium load-bearing claims require a directly captured source and a named
marginal purpose. High requires two qualifying captures with immutable bytes,
distinct canonical source keys and hashes, and exact supporting excerpts. If
the floor is not met, still render the package with human status `evidence
insufficient`.

Keep `integrity_ok`, `tier_contract_met`, and the Organizer recommendation as
separate facts. End Medium and High with one bounded conclusion, human status,
HTML link, limitations or flip conditions, and one reversible next step.

When the user's working language is Traditional Chinese, write human-facing
canonical narrative fields in Traditional Chinese. Preserve exact evidence excerpts,
source titles, identifiers, URLs, and machine diagnostics in their
original form. Confirm, validate, and render are runtime operations, not user
facing ceremony.

The optional [HARNESS.md](HARNESS.md) reference explains the canonical state,
recovery, and delivery gates. It is not required to execute this default flow.
