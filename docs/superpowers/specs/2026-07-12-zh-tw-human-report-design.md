# Traditional Chinese Human Report Design

**Status:** Approved

**Date:** 2026-07-12

**Scope:** Make the deterministic `report.html` readable in Traditional Chinese without changing canonical research semantics, evidence, quotas, or provider behavior.

## Decision

The human report uses Traditional Chinese renderer chrome and declares `lang="zh-Hant-TW"`. The Organizer writes human-facing canonical narrative fields in Traditional Chinese when the user's working language is Traditional Chinese. The renderer displays all canonical values exactly as stored and never calls a model or translates state content.

Exact evidence excerpts, source titles, identifiers, URLs, hashes, provider names, status tokens, tier/posture values, validation codes, and validation machine messages remain unchanged. They are evidence or machine-contract material, not presentation copy.

No translation sidecar, locale field, schema revision, provider route, or presentation-model call is added.

## Rationale

The runtime's reliability rests on one canonical semantic source, deterministic HTML projection, and evidence excerpts whose bytes and offsets remain exact. A lower-cost model translation pass would add a second semantic projection, another invocation to budget, non-deterministic drift, cache invalidation, and a new failure mode that deterministic validation cannot judge.

The cheaper and safer path is to localize only renderer-owned strings and ask the existing Organizer to author the final human narrative in the user's language during synthesis. This adds no model call and preserves the current state-to-report hash binding.

## Goals

- Make every renderer-owned heading, label, empty state, yes/no marker, note, link label, and footer sentence Traditional Chinese.
- Set the document language to `zh-Hant-TW` and prefer Traditional Chinese serif fonts while retaining existing fallbacks.
- Keep report generation byte-deterministic for the same state and validation report.
- Keep all user/provider/source content escaped and byte-for-byte unchanged in the generated HTML.
- Preserve `PASS`, `PARTIAL`, `BLOCKED`, `INVALID`, IDs, hashes, issue codes, provider IDs, tier/posture values, and exact evidence offsets as machine tokens.
- Tell Claude Code and Codex Organizers to write human-facing canonical narrative fields in Traditional Chinese when the conversation language is Traditional Chinese.

## Non-Goals

- Translating evidence excerpts, source titles, citations, provider payloads, or validation machine messages.
- Detecting the language of canonical fields.
- Supporting a runtime locale switch or bilingual report in schema `1.0`.
- Adding a model invocation, subagent, API call, translation cache, or translation artifact.
- Changing validation outcomes or the meaning of any canonical field.

## Renderer Contract

`research_harness/rendering.py` owns presentation strings. Its output must:

1. contain `<html lang="zh-Hant-TW">`;
2. use Traditional Chinese labels for the report title, decision, contract, claims, evidence lineage, sources/origins, verification, engineering handoff, open questions, and deterministic gate result;
3. use Traditional Chinese empty-state and boolean display values;
4. include a footer stating that the report is generated deterministically from canonical JSON without a model-authored report layer, JavaScript, or remote assets;
5. preserve every dynamic canonical value after HTML escaping, without rewriting or translation;
6. preserve the current canonical-state hash metadata and report-event hash behavior.

The font stack should prefer `Noto Serif TC`, `PingFang TC`, and `Songti TC`, followed by the existing serif fallbacks. No remote font or asset may be introduced.

## Organizer Contract

`SKILL.md`, `AGENTS.md`, and `HARNESS.md` state one host-neutral rule:

> When the user's working language is Traditional Chinese, author human-facing canonical narrative fields in Traditional Chinese before validation and rendering. Preserve exact evidence excerpts, source titles, identifiers, URLs, hashes, provider IDs, status tokens, and machine diagnostics in their original form.

This is an authoring rule, not a translation stage. Workers may return any source language; the Organizer reconciles findings into the user's language while exact evidence remains original.

## Failure Behavior

The renderer has no translation dependency and therefore no translation failure mode. If the Organizer stores an English narrative field, the report displays that field unchanged inside otherwise Traditional Chinese chrome. Validation and verdict behavior remain unchanged.

## Tests

Add regression tests that prove:

- the HTML language is `zh-Hant-TW` and the major section labels are Traditional Chinese;
- renderer-owned empty states and boolean labels are Traditional Chinese;
- exact English evidence/source/user strings survive unchanged and escaped;
- canonical state hashes and identical-byte determinism still hold;
- invalid reports retain the machine token `INVALID` inside Traditional Chinese chrome;
- no script, remote asset, model call, or new dependency is introduced.

Run the focused rendering suite first, then all unit tests and the complete release gate.

## Release

The change lands on a branch from current `origin/master`, updates both English and Traditional Chinese documentation where the report-language contract is described, and is pushed to the GitHub repository. After verification, the same revision is synchronized to the Claude Code and Codex global skill installations.
