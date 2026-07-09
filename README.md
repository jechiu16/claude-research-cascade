# claude-research-cascade

[English](README.md) | [繁體中文](README.zh-TW.md)

[![License: MIT](https://img.shields.io/github/license/jechiu16/claude-research-cascade?style=flat-square)](LICENSE)
[![Host neutral](https://img.shields.io/badge/host-neutral-24292f?style=flat-square)](HARNESS.md)
[![Research harness](https://img.shields.io/badge/type-research%20harness-0969da?style=flat-square)](HARNESS.md)

`/deep` is a **meta-research trigger** for tool-using LLM agents.

It does not run a fixed "deep research" pipeline. Instead, it turns the host agent, whether Claude Code, Codex, or another tool-using agent, into the **Organizer** of a bounded, stateful research session over a portfolio of workers: cheap lookups, academic search, deep-research APIs, and file-only processors.

The goal is simple: **maximize information gain per dollar** while keeping claims traceable, conflicts visible, and expensive calls reserved for the places where they actually reduce uncertainty.

## Why This Exists

Most deep-research workflows are single-engine, one-shot, and hard to audit. This harness treats research as an iterative evidence loop:

| Principle | What it means |
|---|---|
| Contract first | Define depth, independence, and strictness before spending. |
| State on disk | Evidence, spend, disputes, and decisions live in a Research State file. |
| Worker affordances | Choose the cheapest adequate tool first; escalate only when the evidence needs it. |
| Claim-level reconciliation | Track specific claims as corroborated, single-source, disputed, or retired. |
| Verification floor | Spot-check the most load-bearing claims before delivery. |
| Host-neutral core | The spec is in `HARNESS.md`; host bindings stay thin. |

## Repository Map

| File | Purpose |
|---|---|
| [HARNESS.md](HARNESS.md) | Host-neutral Organizer protocol: tool affordances, state discipline, loop, hooks, presets, and recovery playbook. |
| [SKILL.md](SKILL.md) | Claude Code binding. Registers `/deep` and maps harness primitives to Claude Code tools. |
| [AGENTS.md](AGENTS.md) | Codex binding. Explains discovery, install wiring, and Codex-native operating rules. |
| [scripts/deep_research.py](scripts/deep_research.py) | Bundled worker CLI. One call, one action, resumable where supported, JSON on stdout. |
| [.env.example](.env.example) | API key template for worker providers. |

## How It Works

```mermaid
flowchart TD
    A["/deep &lt;question&gt;"] --> B["Organizer<br/>frame question + set research contract"]
    B --> S["Research State scratchpad<br/>hypothesis / claims / spend / disputes"]
    S --> L{"Inspect state<br/>choose highest info-gain per dollar"}
    L -- "shared branch" --> W["Optional workers<br/>cascade / scholar / perplexity / openai / gemini / deepseek"]
    L -- "isolated blind check" --> W
    L -- "targeted lookup" --> P["sonar / host search"]
    W --> N["Normalize claims"]
    P --> N
    N --> R["Reconcile<br/>corroborated / single-source / disputed"]
    R --> S
    R --> T{"Contract satisfied<br/>or diminishing returns?"}
    T -- "no" --> L
    T -- "yes" --> V["Verification floor<br/>spot-check load-bearing claims"]
    V --> D["Final verdict<br/>with evidence status, spend, and artifacts"]
```

## Research Contract

Each session is steered by three independent axes. Presets are shortcuts, not hard-coded budgets.

| Axis | Options |
|---|---|
| Depth | `shallow`: one probe wave or quick answer / `medium`: probes plus one or two standard reports / `deep`: multiple deep engines, iterated |
| Independence bar | single source OK / load-bearing claims need 2+ sources / 2+ index families plus one blind isolated pass |
| Strictness | first satisfactory answer / close obvious gaps / chase disputes until resolved or provably unresolvable |

Preset names used by the harness:

| Preset | Composition | Typical use |
|---|---|---|
| `快查` | shallow + single source OK + first satisfactory answer | Cheap fact-checks and quick orientation. |
| `日常` | medium + 2-source bar + close obvious gaps | Normal research and cited summaries. |
| `拍板` | deep + cross-family blind verification + chase disputes | Decision-critical work. |

Dollar figures in this repository are indicative at list prices. The code records cost where providers expose it, but it does not enforce a budget ceiling.

## Worker Affordances

Workers are tools the Organizer may choose from, not pipeline stages.

| Provider | Role | Index family | Typical cost | Typical time |
|---|---|---|---|---|
| `cascade` | Scout wave: 4 parallel `sonar-pro` framings: direct, counter, landscape, falsifier | Perplexity | ~$0.10-0.15 | ~30 s |
| `sonar` | Fast grounded lookup for small gaps or spot checks | Perplexity | ~$0.01 | Seconds |
| `scholar` | Semantic Scholar literature search | Semantic Scholar | Free | Seconds |
| `perplexity` | Long cited deep-research report | Perplexity | ~$0.5-1 | 2-5 min |
| `openai` | Long cited deep-research report using OpenAI deep-research models | OpenAI | ~$0.4-8 | 5-25 min |
| `gemini` | Gemini Deep Research report | Google | Varies | 3-10 min |
| `deepseek` | File-only processor for merging, extracting, and comparing existing artifacts | None | ~free | 1-5 min |

Important: `deepseek` is intentionally not a retrieval worker. It should process already-fetched material, not invent new evidence.

## Install

### Claude Code

Clone the repository into the Claude Code skills directory. `/deep` is then discovered as a skill.

```bash
git clone https://github.com/jechiu16/claude-research-cascade ~/.claude/skills/deep
```

### Codex

Clone the repository anywhere, then make it discoverable from your project. Codex reads `AGENTS.md` by walking upward from the session working directory; it does not scan `~/.claude/skills/`.

```bash
git clone https://github.com/jechiu16/claude-research-cascade ~/tools/research-cascade
export DEEP_HARNESS_DIR=~/tools/research-cascade
```

Then add a short `AGENTS.md` stub in your project root:

```md
For `/deep` research, read `<absolute path>/HARNESS.md` and `<absolute path>/AGENTS.md`.
Workers live at `<absolute path>/scripts/deep_research.py`.
```

See [AGENTS.md](AGENTS.md) for the full Codex-specific install notes.

### Any Other Host

Clone the repository anywhere. The host agent only needs to read [HARNESS.md](HARNESS.md) and invoke [scripts/deep_research.py](scripts/deep_research.py) by absolute path.

## Worker Dependencies

Install the common dependencies:

```bash
pip install requests python-dotenv
```

Gemini support also needs:

```bash
pip install google-genai
```

Create a local `.env` from the template:

```bash
cp .env.example .env
```

Key resolution order:

1. Process environment
2. Nearest `.env` found from the current working directory upward
3. `.env` beside the harness checkout

Supported keys:

| Key | Used by |
|---|---|
| `PERPLEXITY_API_KEY` | `sonar`, `cascade`, `perplexity` |
| `OPENAI_API_KEY` | `openai` |
| `GEMINI_API_KEY` | `gemini` |
| `DEEPSEEK_API_KEY` | `deepseek` |
| `S2_API_KEY` | `scholar` (optional; keyless works with stricter shared limits) |

## Worker CLI

Pick the Python interpreter that has the dependencies installed:

```bash
# Windows
PY=.venv/Scripts/python.exe

# POSIX
PY=.venv/bin/python

# No virtualenv
PY=python3
```

Run workers directly:

```bash
"$PY" scripts/deep_research.py --provider sonar "quick question"
"$PY" scripts/deep_research.py --provider cascade "scout this research question"
"$PY" scripts/deep_research.py --provider scholar "dynamic factor model nowcasting"
"$PY" scripts/deep_research.py "standard research question"
"$PY" scripts/deep_research.py --provider openai --effort high "decision-critical question"
"$PY" scripts/deep_research.py --provider deepseek --files a.md --files b.md "merge into a claims table"
"$PY" scripts/deep_research.py --resume "openai:resp_abc123"
```

Output contract:

| Stream | Contract |
|---|---|
| stdout | One JSON object. Success includes `report`, `report_path`, `usage`, `cost_estimate_usd`, and `wall_time_s`. |
| stderr | Progress only, including async resume tokens. |
| files | Reports are saved under `<cwd>/reports/deep_<timestamp>_<slug>.md`. |

For medium-depth and deeper sessions, pass a ledger path so the worker appends machine-readable spend records:

```bash
"$PY" scripts/deep_research.py \
  --provider cascade \
  --ledger reports/deep_state_topic.ledger.jsonl \
  "research question"
```

## Field Notes

- Perplexity `reasoning_effort=minimal` is ungrounded in this workflow: it can bill searches while returning no citations. Use `medium` or higher for real research.
- Perplexity returns official `usage.cost.total_cost`; the worker reports it verbatim.
- OpenAI currently does not return a provider cost field here; the worker estimates from token counts and web-search call count.
- Semantic Scholar should receive keyword phrases, not natural-language questions, and should not be called in parallel.
- OpenAI deep-research models require a verified organization.
- Gemini uses the Interactions API `steps` schema targeted by the worker and requires `google-genai`.
- Failed async polls return JSON with `error` and `resume`; organizers should resume rather than re-pay for submitted work.
- Report filenames include a short hash of `query + pid` so parallel probes and CJK-only queries do not overwrite one another.

## Status

This is a harness and host binding, not a packaged Python library. The core behavior is specified in Markdown and executed by whichever host agent is acting as Organizer.

## License

[MIT](LICENSE)
