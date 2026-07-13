# Agent Deep Research Trigger

[![CI](https://github.com/jechiu16/agent-deep-research-trigger/actions/workflows/ci.yml/badge.svg)](https://github.com/jechiu16/agent-deep-research-trigger/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/jechiu16/agent-deep-research-trigger?include_prereleases&style=flat-square)](https://github.com/jechiu16/agent-deep-research-trigger/releases)
[![License: MIT](https://img.shields.io/github/license/jechiu16/agent-deep-research-trigger?style=flat-square)](LICENSE)

**A portable `/deep` research skill for Claude Code and OpenAI Codex.** It turns
a question into a bounded answer with links or an evidence-backed package.

[繁體中文](README.zh-TW.md) · [Releases](https://github.com/jechiu16/agent-deep-research-trigger/releases)

## Quickstart

1. **Install the tagged skill and runtime.**

```bash
git clone https://github.com/jechiu16/agent-deep-research-trigger.git \
  "$HOME/.agent-deep-research-trigger"
cd "$HOME/.agent-deep-research-trigger"
git checkout v2.0.0b6
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

2. **Link it to one host.**

```bash
# Claude Code
mkdir -p "$HOME/.claude/skills"
ln -s "$PWD" "$HOME/.claude/skills/deep"

# Or OpenAI Codex
mkdir -p "$HOME/.agents/skills"
ln -s "$PWD" "$HOME/.agents/skills/deep"
```

3. **Start a fresh session** so the host discovers the linked skill.

4. **Type `/deep` with a research question, then choose a tier.**

```text
/deep Compare SQLite and DuckDB as the default local analytics engine.
```

## Tiers

| Tier | Result |
|---|---|
| Low | Chat answer with links; no runtime package. |
| Medium | Direct evidence for a named gap plus a package. |
| High | At least two qualifying captures plus a package. |

Host-native work is the default. Optional external provider calls are used only
when disclosed on the card.

## Outputs

Medium and High deliver:

| Output | Purpose |
|---|---|
| Canonical JSON | Machine-readable research state and evidence links. |
| `zh-Hant-TW` HTML | Traditional Chinese conclusion, limitations, and status. |

Evidence or delivery gaps still produce a blocked package, never `PASS`. The
HTML identifies `EVIDENCE_INSUFFICIENT` or `DELIVERY_INCOMPLETE` as applicable.

## Project Links

- [SKILL.md](SKILL.md): public `/deep` protocol
- [HARNESS.md](HARNESS.md): Medium/High internal runtime bridge and gates
- [examples/v2](examples/v2): runtime fixture
- [CONTRIBUTING.md](CONTRIBUTING.md): development and release checks
- [SECURITY.md](SECURITY.md): private security reporting

## License

[MIT](LICENSE)
