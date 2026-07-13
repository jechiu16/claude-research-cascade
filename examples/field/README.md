# Parallax Field Acceptance

2026-07-13 以 Parallax commit `a8c4284e73156ac62e61d5e70a273781342c55fb`
連續跑三個真實問題。三次都在確認卡選 Light，因為答案可由 repository
source-of-record 直接複驗；為用而用 D1 或 Search 只會增加成本與噪音。

| 題目 | 結果 | Deep | Search | 關鍵判斷 |
|---|---|---:|---:|---|
| SQLite 或 DuckDB | PASS | 0 | 0 | 正式 ADR 已決定 DuckDB，不重開選型。 |
| Regime staleness boundary | PASS | 0 | 0 | 修正 cache framing；採 transaction 後 health check。 |
| Long-job acceptance test | PASS | 0 | 0 | 採 temp-root carrier failure-path test。 |

每個資料夾保留一張 `confirmation-card.txt` 與完整 canonical package：
`state.json`、`events.jsonl`、`raw/`、`report.html`。`report.html` 是繁體中文
人讀視圖；後續 coding session 應優先讀 `state.json`。

重跑 validation：

```bash
deep-research-state validate examples/field/01-duckdb-source-of-truth/session --json
deep-research-state validate examples/field/02-regime-staleness-boundary/session --json
deep-research-state validate examples/field/03-long-job-acceptance-test/session --json
```
