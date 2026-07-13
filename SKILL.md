---
name: deep
description: Portable /deep research trigger for Claude Code and OpenAI Codex. Use only when the user explicitly types /deep to start a bounded, evidence-gated research session.
---

<!-- PURE_TRIGGER_CARD_START -->
問題：{正規化後的問題}
建議：{層級}，因為{一個理由}
Low：只在對話中回答，附上連結。
Medium：為具名缺口補上直接取得的來源，並交付套件。
High：直接取得至少兩個不同來源，並交付套件。
額外付費請求：{精確數量}；本機資料外送：{是／否}。
開始：Low｜Medium｜High｜調整
<!-- PURE_TRIGGER_CARD_END -->

# Agent Deep Research Trigger

SKILL.md is the sole human protocol shared by Claude Code and OpenAI Codex.
The first `/deep` response is exactly the seven card lines above, with no prose
before or after. Normalize and recommend from conversation text only.
If no research question is recognizable, still show the card with
`問題：尚未提供研究問題` and `建議：調整，因為需要先提供研究問題`; do not ask first.
額外付費請求只計 provider/API paid calls；host-native retrieval、local、Organizer 不計，無計畫 external paid route 時預設為 0。

## Before Selection

Host discovery may read the wrapper and canonical SKILL.md to load this
instruction; that is not a research action. Before selection, do not call tools
or inspect research, project, runtime, or source material; do not search the web,
run scripts, or start workers. Low never reads or invokes the runtime. The tier
choice is the only confirmation; `調整` shows a new card and starts no research.

## After Selection

After Medium or High is selected, read [HARNESS.md](HARNESS.md) beside this
canonical skill and follow its internal runtime bridge. Do not expose bridge
commands as user steps. Report only: 界定問題 -> 蒐集資料 -> 交叉檢查 -> 形成結論
-> 交付結果.

Low returns a bounded Traditional Chinese chat answer and links. Medium adds a
direct source for a named gap, conflict, or decision risk. High directly gets at
least two different sources. Medium and High always deliver canonical JSON and
`zh-Hant-TW` HTML, including blocked results.

## Evidence And Delivery

Medium load-bearing claims require a directly captured source and a named
marginal purpose. High requires two qualifying captures with distinct canonical
source keys and content hashes, exact excerpts, and shared-upstream disclosure;
agreement never proves independence or truth.

Fail closed: an evidence-floor gap yields canonical `BLOCKED`/`證據不足` and HTML
`EVIDENCE_INSUFFICIENT`; a terminal/handoff/completeness gap yields canonical
`BLOCKED`/`交付不完整` and HTML `DELIVERY_INCOMPLETE`.

Write human-facing canonical narrative fields in Traditional Chinese when it is
the user's working language. Preserve exact excerpts, source titles, identifiers,
URLs, and machine diagnostics in their original form.
