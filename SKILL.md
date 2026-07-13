---
name: deep
description: Portable /deep research trigger for Claude Code and OpenAI Codex. Use only when the user explicitly types /deep to start one bounded, host-led research session.
---

<!-- PURE_TRIGGER_CARD_START -->
問題：{正規化後的問題}
Query Brief：{決策、範圍、成功條件各一句}
建議：{light/standard/heavy}，因為{一個理由}
Light：deep {a}｜search {b}｜free unlimited
Standard：deep {a}｜search {b}｜free unlimited
Heavy：deep {a}｜search {b}｜free unlimited
D1：{最低成本 ready provider；候選與資料外送範圍}
共通：背景執行；host 複驗並寫結論；交付 JSON + 繁體中文 HTML；超限即停並標註缺口
開始：light｜standard｜heavy｜調整｜取消
<!-- PURE_TRIGGER_CARD_END -->

# /deep

`SKILL.md` is the sole public protocol shared by Claude Code and Codex. On
explicit `/deep`, normalize the question from conversation context, run only
the local `deep-research-state card` command, and show exactly one completed
card with no prose around it. If the question is missing, set the recommendation
to `調整`; do not start research.

## Before Confirmation

Do not search, inspect the project, call a provider, or start a worker. Local
profile/registry reads for the card are allowed and make no external request.
The user's `light`, `standard`, or `heavy` reply confirms that printed count
vector and disclosed provider/egress set for one run. `調整` and `取消` spend
nothing. Re-card only when the vector, provider set, or egress scope changes.

## After Confirmation

Read [HARNESS.md](HARNESS.md), create the canonical package, and run in the
background. The selected host is the Organizer and sole conclusion author.
Provider reports, including D1/D2, buy breadth and structure only; they cannot
support a canonical claim.

Use the cheapest ready D1 provider unless source fit or privacy gives a named
reason to choose another disclosed candidate. After each provider report, feed
its useful hypotheses, contradictions, citations, and prior session context to
the host. The host chooses targeted re-verification, consuming `search`; `free`
routes remain unlimited within physical/time safety bounds. Fix disproved
claims, mark unverifiable claims, and never withhold delivery for uncertainty.

Stop external calls at the confirmed count limit. Finish from existing
materials and name the unresolved gap. Heavy may use a second deep call only
when the host expects a material new angle, challenge, or expansion; no hard
gate and no automatic provider bundle.

## Delivery

Always deliver canonical `state.json`, `events.jsonl`, `raw/`, and
`report.html`. Human-facing narrative fields and HTML are Traditional Chinese;
exact excerpts, titles, URLs, IDs, hashes, and diagnostics stay unchanged.
Integrity failure remains unsafe; evidence insufficiency remains an annotated
epistemic status. Neither prevents producing the package.
