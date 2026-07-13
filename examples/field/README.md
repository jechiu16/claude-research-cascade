# Parallax Field Acceptance

2026-07-13 至 2026-07-14 以 Parallax commit
`a8c4284e73156ac62e61d5e70a273781342c55fb` 跑四個真實問題。前三次選
Light；第四次刻意選 Standard，實際運動 D1、targeted Search、direct capture、
host disposition 與 HTML projection 的完整循環。

| 題目 | 結果 | Deep | Search | 關鍵判斷 |
|---|---|---:|---:|---|
| SQLite 或 DuckDB | PASS | 0 | 0 | 正式 ADR 已決定 DuckDB，不重開選型。 |
| Regime staleness boundary | PASS | 0 | 0 | 修正 cache framing；採 transaction 後 health check。 |
| Long-job acceptance test | PASS | 0 | 0 | 採 temp-root carrier failure-path test。 |
| DuckDB concurrency boundary | PASS | 1 | 1 | 維持 single owner；修正 Quack framing。 |

每個資料夾保留一張 `confirmation-card.txt` 與完整 canonical package：
`state.json`、`events.jsonl`、`raw/`、`report.html`。`report.html` 是繁體中文
人讀視圖；後續 coding session 應優先讀 `state.json`。

完成條件不是只有三次 `PASS`：驗收集合中至少一題必須實際消耗
`deep >= 1`、`search >= 1`，保留外部 direct bytes，讓 D1 hypothesis 驅動
targeted re-verification，並在 HTML 顯示每個承重 claim 的 disposition。第四跑
達成 `deep=1`、`search=1`、17,274 raw bytes，且 `C2` 被修正。

[第四跑 decision delta](04-duckdb-concurrency-boundary/decision-delta.md) 顯示
production decision 未變，但 tier calibration 改變：單一官方 source-of-record
題目未來應先選 Light。

重跑 validation：

```bash
deep-research-state validate examples/field/01-duckdb-source-of-truth/session --json
deep-research-state validate examples/field/02-regime-staleness-boundary/session --json
deep-research-state validate examples/field/03-long-job-acceptance-test/session --json
deep-research-state validate examples/field/04-duckdb-concurrency-boundary/session --json
```
