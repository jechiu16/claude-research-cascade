# claude-research-cascade

[English](README.md) | [繁體中文](README.zh-TW.md)

[![License: MIT](https://img.shields.io/github/license/jechiu16/claude-research-cascade?style=flat-square)](LICENSE)
[![Host neutral](https://img.shields.io/badge/host-neutral-24292f?style=flat-square)](HARNESS.md)
[![Research harness](https://img.shields.io/badge/type-research%20harness-0969da?style=flat-square)](HARNESS.md)

`/deep` 是給可使用工具的 LLM Agent 使用的 **meta-research trigger**。

它不是固定流程的「深度研究」工具。它會把宿主 Agent，例如 Claude Code、Codex，或其他具備工具能力的 Agent，變成研究流程的 **Organizer**，在一次有邊界、有狀態、可稽核的研究工作中調度多種 worker：低成本查證、學術搜尋、深度研究 API，以及只處理既有檔案的整理器。

核心目標很直接：**用每一美元換到最多有用資訊**，同時讓主張可追溯、衝突可見，並把昂貴呼叫留給真正能降低不確定性的地方。

## 為什麼需要它

常見的 deep research 工作流多半是單一引擎、一次性輸出，而且難以稽核。這個 harness 把研究視為反覆迭代的證據循環：

| 原則 | 意義 |
|---|---|
| 先定契約 | 花錢前先定義深度、獨立性門檻與嚴格程度。 |
| 狀態落盤 | 證據、花費、爭議與決策都寫進 Research State 檔案。 |
| Worker affordances | 先選足夠便宜的工具；只有證據需要時才升級昂貴 worker。 |
| 主張層級對帳 | 逐條標記主張為已佐證、單一來源、有爭議或已淘汰。 |
| 驗證底線 | 交付前獨立抽查最關鍵、最承重的主張。 |
| 宿主中立 | 核心規格在 `HARNESS.md`；不同宿主只需要薄薄一層 binding。 |

## Repo 結構

| 檔案 | 用途 |
|---|---|
| [HARNESS.md](HARNESS.md) | 宿主中立的 Organizer protocol：工具 affordances、狀態紀律、循環、hook、preset 與 recovery playbook。 |
| [SKILL.md](SKILL.md) | Claude Code binding。註冊 `/deep` 並把 harness primitive 對應到 Claude Code 工具。 |
| [AGENTS.md](AGENTS.md) | Codex binding。說明 discovery、安裝接線方式與 Codex 的操作規則。 |
| [scripts/deep_research.py](scripts/deep_research.py) | 內建 worker CLI。一次呼叫就是一次 action；支援可恢復任務；stdout 輸出 JSON。 |
| [.env.example](.env.example) | Worker provider 的 API key 範本。 |

## 運作方式

```mermaid
flowchart TD
    A["/deep &lt;question&gt;"] --> B["Organizer<br/>釐清問題 + 設定研究契約"]
    B --> S["Research State scratchpad<br/>暫定假說 / 主張 / 花費 / 爭議"]
    S --> L{"檢查狀態<br/>選擇每美元資訊量最高的下一批 action"}
    L -- "shared branch" --> W["Optional workers<br/>cascade / scholar / perplexity / openai / gemini / deepseek"]
    L -- "isolated blind check" --> W
    L -- "targeted lookup" --> P["sonar / host search"]
    W --> N["正規化主張"]
    P --> N
    N --> R["對帳<br/>已佐證 / 單一來源 / 有爭議"]
    R --> S
    R --> T{"達到契約門檻<br/>或邊際收益下降?"}
    T -- "否" --> L
    T -- "是" --> V["驗證底線<br/>抽查承重主張"]
    V --> D["最終結論<br/>附證據狀態、花費與產物"]
```

## 研究契約

每次研究都由三個獨立軸線驅動。Preset 是組合捷徑，不是硬編碼預算。

| 軸線 | 選項 |
|---|---|
| 深度 | `shallow`：一波 probe 或快速回答 / `medium`：probe 加上一兩份標準 report / `deep`：多個深度引擎並反覆迭代 |
| 獨立性門檻 | 單一來源可接受 / 承重主張需要 2+ 來源 / 2+ index family 加上一輪盲驗 |
| 嚴格程度 | 第一個滿意答案即可 / 補齊明顯缺口 / 追爭議直到解決或證明不可解 |

Harness 使用的 preset：

| Preset | 組成 | 適合情境 |
|---|---|---|
| `快查` | shallow + 單一來源可接受 + 第一個滿意答案即可 | 低成本 fact-check 或快速建立方向感。 |
| `日常` | medium + 2-source bar + 補齊明顯缺口 | 一般研究、帶引用摘要、日常判斷。 |
| `拍板` | deep + 跨 index family 盲驗 + 追爭議 | 高風險或會影響決策的研究。 |

Repo 裡的美元數字只代表當前清單價格下的概略估算。程式會記錄 provider 回傳的成本資訊，但不會強制執行預算上限。

## Worker Affordances

Workers 是 Organizer 可選用的工具，不是固定 pipeline 階段。

| Provider | 角色 | Index family | 典型成本 | 典型時間 |
|---|---|---|---|---|
| `cascade` | Scout wave：4 個平行 `sonar-pro` framing：direct、counter、landscape、falsifier | Perplexity | ~$0.10-0.15 | ~30 秒 |
| `sonar` | 快速 grounded lookup，用於小缺口或 spot check | Perplexity | ~$0.01 | 數秒 |
| `scholar` | Semantic Scholar 文獻搜尋 | Semantic Scholar | 免費 | 數秒 |
| `perplexity` | 長篇、有引用的 deep-research report | Perplexity | ~$0.5-1 | 2-5 分鐘 |
| `openai` | 使用 OpenAI deep-research models 的長篇、有引用 report | OpenAI | ~$0.4-8 | 5-25 分鐘 |
| `gemini` | Gemini Deep Research report | Google | 視 provider 而定 | 3-10 分鐘 |
| `deepseek` | 只處理檔案：合併、抽取、比較既有 artifacts | 無 | 近乎免費 | 1-5 分鐘 |

重要：`deepseek` 在這個 harness 裡不是 retrieval worker。它只應處理已經抓回來的材料，不應用來憑空產生新證據。

## 安裝

### Claude Code

把 repo clone 到 Claude Code 的 skills 目錄。之後 `/deep` 會被當成 skill 探測到。

```bash
git clone https://github.com/jechiu16/claude-research-cascade ~/.claude/skills/deep
```

### Codex

把 repo clone 到任意位置，然後讓你的專案能發現它。Codex 會從 session working directory 往上尋找 `AGENTS.md`；它不會掃描 `~/.claude/skills/`。

```bash
git clone https://github.com/jechiu16/claude-research-cascade ~/tools/research-cascade
export DEEP_HARNESS_DIR=~/tools/research-cascade
```

接著在你的專案根目錄加一個短版 `AGENTS.md` stub：

```md
For `/deep` research, read `<absolute path>/HARNESS.md` and `<absolute path>/AGENTS.md`.
Workers live at `<absolute path>/scripts/deep_research.py`.
```

完整的 Codex 安裝與操作注意事項請見 [AGENTS.md](AGENTS.md)。

### 其他宿主

把 repo clone 到任意位置。宿主 Agent 只需要讀取 [HARNESS.md](HARNESS.md)，並用絕對路徑呼叫 [scripts/deep_research.py](scripts/deep_research.py)。

## Worker 依賴

安裝共用依賴：

```bash
pip install requests python-dotenv
```

Gemini 支援另外需要：

```bash
pip install google-genai
```

從範本建立本機 `.env`：

```bash
cp .env.example .env
```

API key 解析順序：

1. Process environment
2. 從目前 working directory 往上找到的最近 `.env`
3. Harness checkout 旁邊的 `.env`

支援的 key：

| Key | 用途 |
|---|---|
| `PERPLEXITY_API_KEY` | `sonar`、`cascade`、`perplexity` |
| `OPENAI_API_KEY` | `openai` |
| `GEMINI_API_KEY` | `gemini` |
| `DEEPSEEK_API_KEY` | `deepseek` |
| `S2_API_KEY` | `scholar`，選填；不填也能用，但會受更嚴格的 shared limit 影響 |

## Worker CLI

先選擇已安裝依賴的 Python interpreter：

```bash
# Windows
PY=.venv/Scripts/python.exe

# POSIX
PY=.venv/bin/python

# 沒有 virtualenv
PY=python3
```

直接執行 worker：

```bash
"$PY" scripts/deep_research.py --provider sonar "quick question"
"$PY" scripts/deep_research.py --provider cascade "scout this research question"
"$PY" scripts/deep_research.py --provider scholar "dynamic factor model nowcasting"
"$PY" scripts/deep_research.py "standard research question"
"$PY" scripts/deep_research.py --provider openai --effort high "decision-critical question"
"$PY" scripts/deep_research.py --provider deepseek --files a.md --files b.md "merge into a claims table"
"$PY" scripts/deep_research.py --resume "openai:resp_abc123"
```

輸出契約：

| Stream | 契約 |
|---|---|
| stdout | 單一 JSON 物件。成功時包含 `report`、`report_path`、`usage`、`cost_estimate_usd`、`wall_time_s`。 |
| stderr | 只放進度訊息，包含 async resume token。 |
| files | Report 會存到 `<cwd>/reports/deep_<timestamp>_<slug>.md`。 |

中等深度以上的研究，建議傳入 ledger 路徑，讓 worker 追加機器可讀的花費紀錄：

```bash
"$PY" scripts/deep_research.py \
  --provider cascade \
  --ledger reports/deep_state_topic.ledger.jsonl \
  "research question"
```

## 實務筆記

- 在這個 workflow 裡，Perplexity `reasoning_effort=minimal` 視為 ungrounded：它可能計費搜尋，卻不回傳引用。真正研究請用 `medium` 或更高。
- Perplexity 會回傳官方 `usage.cost.total_cost`；worker 會照實報告。
- OpenAI 這裡目前不回傳 provider cost field；worker 會用 token 數和 web-search call 數估算。
- Semantic Scholar 應該收到 keyword phrases，而不是自然語言問題；也不要平行呼叫。
- OpenAI deep-research models 需要 verified organization。
- Gemini 使用 worker 目標支援的 Interactions API `steps` schema，並需要 `google-genai`。
- Async poll 失敗時會回傳含有 `error` 與 `resume` 的 JSON；Organizer 應該 resume，而不是重新付費提交。
- Report 檔名包含 `query + pid` 的短 hash，避免平行 probe 或純 CJK query 互相覆蓋。

## 狀態

這是一個 harness 與 host binding，不是打包好的 Python library。核心行為寫在 Markdown 規格裡，並由擔任 Organizer 的宿主 Agent 執行。

## License

[MIT](LICENSE)
