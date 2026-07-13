# Decision Delta

## Baseline

維持一個 process 擁有 Parallax 的 DuckDB read-write lifecycle；跨 process
consumer 不直接與 writer 共用 database file。

## Standard Result

工程決定不變，但邊界更精確：

- 官方文件確認 direct file access 仍是單一 read-write process，或全員 read-only。
- 同 process 的 appends 不衝突；same-row update/delete 應以 transaction
  conflict 進入 bounded retry。
- D1 的絕對 framing 被修正：Quack 已提供 multi-process write 的
  client-server 路徑，但 DuckDB v1.5.3 仍標示為 beta。
- Parallax 已 pin `duckdb~=1.5`，且 production code 已因 mixed
  `read_only` configuration 明確排序 connection lifecycle。

因此新增的是可執行的 failure-path test boundary 與 Quack revisit 條件，不是
改變 production architecture。

## Tier Calibration

這一題的主要新事實由一發 Exa（$0.007）與官方原始文件找到；Perplexity D1
花費 $0.5469，提供廣度與測試候選，但漏掉當前 Quack beta 更新。對單一
source-of-record、可用官方文件直接回答的技術題，未來應先選 Light。只有當
問題跨多個來源、替代架構或未知角度，D1 breadth 預期會改變搜尋策略時，才選
Standard。
