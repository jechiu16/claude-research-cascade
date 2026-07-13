# Agent Deep Research Trigger

[![CI](https://github.com/jechiu16/agent-deep-research-trigger/actions/workflows/ci.yml/badge.svg)](https://github.com/jechiu16/agent-deep-research-trigger/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/jechiu16/agent-deep-research-trigger?include_prereleases&style=flat-square)](https://github.com/jechiu16/agent-deep-research-trigger/releases)
[![License: MIT](https://img.shields.io/github/license/jechiu16/agent-deep-research-trigger?style=flat-square)](LICENSE)

**給 Claude Code 與 OpenAI Codex 共用的 `/deep` 研究 skill。** 它把研究問題
整理成有邊界的回答與連結，或交付有 evidence 的研究 package。

[English](README.md) · [Releases](https://github.com/jechiu16/agent-deep-research-trigger/releases)

## 快速開始

1. **安裝指定 tag 的完整 skill 與 runtime。**

```bash
git clone https://github.com/jechiu16/agent-deep-research-trigger.git \
  "$HOME/.agent-deep-research-trigger"
cd "$HOME/.agent-deep-research-trigger"
git checkout v2.0.0b6
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

2. **連結到一個 host。**

```bash
# Claude Code
mkdir -p "$HOME/.claude/skills"
ln -s "$PWD" "$HOME/.claude/skills/deep"

# 或 OpenAI Codex
mkdir -p "$HOME/.agents/skills"
ln -s "$PWD" "$HOME/.agents/skills/deep"
```

3. **開啟新的 session，** 讓 host 載入這個 skill。

4. **輸入 `/deep` 與研究問題，再選擇 tier。**

```text
/deep 比較 SQLite 與 DuckDB，哪個更適合當本機分析引擎預設值？
```

## Tiers

| Tier | 結果 |
|---|---|
| Low | 在對話中回答並附上連結；不建立研究套件。 |
| Medium | 為具名缺口補上直接證據，並交付研究套件。 |
| High | 取得至少兩份符合門檻的直接來源紀錄，並交付研究套件。 |

預設使用 host-native 路徑。只有卡片已揭露時，才使用 optional external provider。

## 輸出

Medium 與 High 交付：

| Output | 用途 |
|---|---|
| Canonical JSON | 可供機器讀取的研究狀態與證據連結。 |
| `zh-Hant-TW` HTML | 繁中結論、限制與 status。 |

證據或交付有缺口時仍會交付受阻的研究套件，絕不標為 `PASS`；HTML
會依情況標示 `EVIDENCE_INSUFFICIENT` 或 `DELIVERY_INCOMPLETE`。

## 專案連結

- [SKILL.md](SKILL.md)：公開 `/deep` protocol
- [HARNESS.md](HARNESS.md)：Medium/High internal runtime bridge 與 gates
- [examples/v2](examples/v2)：runtime fixture
- [CONTRIBUTING.md](CONTRIBUTING.md)：開發與 release checks
- [SECURITY.md](SECURITY.md)：private security reporting

## License

[MIT](LICENSE)
