# Traditional Chinese Human Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the deterministic human report with Traditional Chinese interface copy while preserving canonical values, exact evidence, hashes, and validation semantics.

**Architecture:** Localize only renderer-owned static strings in `research_harness/rendering.py`. The Organizer authors human-facing canonical narrative in the user's Traditional Chinese working language; the renderer never translates state data and introduces no model call, locale field, sidecar, or dependency.

**Tech Stack:** Python 3.9+, standard-library `unittest`, deterministic escaped HTML, Markdown host bindings.

## Global Constraints

- Keep schema version `1.0`; do not add state or contract fields.
- Keep `render_html(state, report) -> str` and `RenderedReport` unchanged.
- Preserve dynamic canonical values byte-for-byte after existing HTML escaping.
- Preserve exact evidence excerpts, source titles, IDs, URLs, hashes, provider names, status tokens, tier/posture values, validation codes, and validation messages.
- Add no model call, translation artifact, network request, JavaScript, remote asset, font download, or dependency.
- Use `/Users/jechiu/dev/parallax/.venv/bin/python`, never a bare Python executable.

---

### Task 1: Localize deterministic renderer chrome

**Files:**
- Modify: `tests/test_rendering.py`
- Modify: `research_harness/rendering.py`

**Interfaces:**
- Consumes: existing `render_html(state: dict[str, Any], report: ValidationReport) -> str`.
- Produces: the same interface, with `zh-Hant-TW` renderer-owned copy and unchanged dynamic values.

- [ ] **Step 1: Write failing language and preservation tests**

Add these tests to `RenderingTests`:

```python
def test_report_uses_traditional_chinese_chrome(self) -> None:
    document = render_html(self.state, self.report)
    self.assertIn('<html lang="zh-Hant-TW">', document)
    for label in (
        "有界研究 / 正式狀態投影",
        "有界結論",
        "研究工作階段",
        "成本層級",
        "研究模式",
        "初始搜尋路由",
        "實體請求上限",
        "正式主張",
        "證據紀錄",
        "資料檔",
        "來源層級",
        "上下文分離",
        "來源與起源",
        "驗證",
        "工程交接",
        "待釐清問題",
        "決定性檢查結果",
    ):
        with self.subTest(label=label):
            self.assertIn(label, document)

def test_report_preserves_dynamic_values_in_their_original_language(self) -> None:
    state = copy.deepcopy(self.state)
    state["framing"]["question"] = "Should cache remain enabled?"
    state["summary"]["decision"] = "Keep 42 workers <unchanged>."
    state["claims"][0]["text"] = "Original claim 42 <verbatim>"
    state["sources"][0]["title"] = "Original Source Title"
    state["evidence"][0]["excerpt"] = "Exact evidence 42 <verbatim>"
    document = render_html(state, self.report)
    self.assertIn("Should cache remain enabled?", document)
    self.assertIn("Keep 42 workers &lt;unchanged&gt;.", document)
    self.assertIn("Original claim 42 &lt;verbatim&gt;", document)
    self.assertIn("Original Source Title", document)
    self.assertIn("Exact evidence 42 &lt;verbatim&gt;", document)

def test_empty_states_and_boolean_labels_are_traditional_chinese(self) -> None:
    state = copy.deepcopy(self.state)
    state["claims"] = []
    state["evidence"] = []
    state["sources"] = []
    state["verification"] = []
    state["engineering_handoff"]["safe_actions"] = []
    state["engineering_handoff"]["constraints"] = []
    state["engineering_handoff"]["acceptance_tests"] = []
    state["open_questions"] = []
    document = render_html(state, self.report)
    for label in (
        "尚未記錄正式主張",
        "尚未納入證據紀錄",
        "尚未記錄",
    ):
        with self.subTest(label=label):
            self.assertIn(label, document)

Add direct true and false assertions for `<td>是/否</td>`, `已完成：是/否`,
`上下文分離：是/否`, and `可逆：是/否`.
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=. /Users/jechiu/dev/parallax/.venv/bin/python -m unittest \
  tests.test_rendering.RenderingTests.test_report_uses_traditional_chinese_chrome \
  tests.test_rendering.RenderingTests.test_report_preserves_dynamic_values_in_their_original_language \
  tests.test_rendering.RenderingTests.test_empty_states_and_boolean_labels_are_traditional_chinese -v
```

Expected: the chrome and empty-state tests fail because the current renderer uses `lang="en"` and English copy; the preservation test passes.

- [ ] **Step 3: Implement the minimal renderer localization**

In `research_harness/rendering.py`, replace renderer-owned English strings with these Traditional Chinese equivalents:

```text
None recorded -> 尚未記錄
raw artifact -> 原始資料
No canonical claims recorded -> 尚未記錄正式主張
LOAD-BEARING -> 關鍵主張
No qualifiers -> 無限定條件
none -> 無
Untitled claim -> 未命名主張
Scope -> 範圍
Applicability -> 適用性
Supporting evidence -> 支持證據
Qualifiers and flip condition -> 限定條件與翻轉條件
Would change if -> 重新評估條件
not recorded -> 未記錄
not checked -> 未檢查
No evidence records admitted -> 尚未納入證據紀錄
Excerpt truncated for display. -> 摘錄過長，顯示內容已截斷。
Source -> 來源
Origin -> 起源
Artifact -> 資料檔
Exact bytes -> 原文位元組範圍
No sources recorded -> 尚未記錄來源
Untitled source -> 未命名來源
Origin kind -> 起源類型
Direct fetch -> 直接擷取
yes/no -> 是/否
No verification records -> 尚未記錄驗證
Completed -> 已完成
Context separated -> 上下文分離
All deterministic gates passed. -> 所有決定性檢查均已通過。
No safe action recorded -> 尚未記錄安全行動
Safe action -> 安全行動
Reversible -> 可逆
Depends on claims -> 依賴主張
Research Session -> 研究工作階段
Bounded Research / Canonical Projection -> 有界研究 / 正式狀態投影
Research result -> 研究結果
Bounded answer -> 有界結論
Decision -> 結論
No decision recorded -> 尚未記錄結論
Updated -> 更新時間
Contract -> 研究契約
Tier -> 成本層級
Posture -> 研究模式
Scout route -> 初始搜尋路由
Load-bearing floor -> 關鍵主張下限
Physical request ceilings -> 實體請求上限
Canonical Claims -> 正式主張
Evidence Lineage -> 證據紀錄
Source title column -> 來源標題
Source tier -> 來源層級
Sources and Origins -> 來源與起源
Verification -> 驗證
Engineering Handoff -> 工程交接
Constraints -> 限制條件
Acceptance tests -> 驗收測試
Open Questions -> 待釐清問題
Deterministic Gate Result -> 決定性檢查結果
```

Set `<html lang="zh-Hant-TW">`. Prepend the local font stack with:

```css
"Noto Serif TC","PingFang TC","Songti TC"
```

Use this footer verbatim:

```text
本報告只從唯一正式 JSON 狀態決定性產生，不含模型撰寫的第二層報告、JavaScript 或遠端資產。
```

Do not translate `issue.level`, `issue.code`, `issue.message`, `issue.path`, status values, tier/posture values, source titles, or evidence excerpts.

- [ ] **Step 4: Run rendering tests and verify GREEN**

Run:

```bash
PYTHONPATH=. /Users/jechiu/dev/parallax/.venv/bin/python -m unittest tests.test_rendering -v
```

Expected: all rendering tests pass, including existing determinism, escaping, hash binding, stale-report, invalid-label, and no-external-assets tests.

- [ ] **Step 5: Commit the renderer behavior**

```bash
git add research_harness/rendering.py tests/test_rendering.py
git commit -m "feat(report): render human report in Traditional Chinese"
```

### Task 2: Bind Organizer language behavior in host-neutral docs

**Files:**
- Modify: `tests/test_docs.py`
- Modify: `SKILL.md`
- Modify: `AGENTS.md`
- Modify: `HARNESS.md`
- Modify: `README.md`
- Modify: `README.zh-TW.md`

**Interfaces:**
- Consumes: the existing Organizer protocol and canonical artifact contract.
- Produces: one explicit language rule shared by Claude Code and Codex.

- [ ] **Step 1: Write the failing documentation contract test**

Add to `DocumentationTests`:

```python
def test_organizer_docs_define_traditional_chinese_report_boundary(self) -> None:
    for relative in ("SKILL.md", "AGENTS.md", "HARNESS.md"):
        with self.subTest(path=relative):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("Traditional Chinese", text)
            self.assertIn("exact evidence excerpts", text)
            self.assertIn("source titles", text)
    for relative in ("README.md", "README.zh-TW.md"):
        with self.subTest(path=relative):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("zh-Hant-TW", text)
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```bash
PYTHONPATH=. /Users/jechiu/dev/parallax/.venv/bin/python -m unittest \
  tests.test_docs.DocumentationTests.test_organizer_docs_define_traditional_chinese_report_boundary -v
```

Expected: FAIL because the host-neutral language boundary is not yet documented.

- [ ] **Step 3: Add the exact host-neutral language rule**

Add this paragraph to `SKILL.md`, `AGENTS.md`, and `HARNESS.md` near their delivery/render instructions:

```text
When the user's working language is Traditional Chinese, author human-facing canonical narrative fields in Traditional Chinese before validation and rendering. Preserve exact evidence excerpts, source titles, identifiers, URLs, hashes, provider IDs, status tokens, and machine diagnostics in their original form. The deterministic renderer does not call a translation model.
```

Update the existing `report.html` artifact-table row in each README to state that the report declares `zh-Hant-TW`, uses Traditional Chinese interface copy, and preserves source/evidence text in its original language. Keep `README.md` at or below its enforced 260-line ceiling; do not add a translation route or model recommendation.

- [ ] **Step 4: Run documentation and rendering suites**

Run:

```bash
PYTHONPATH=. /Users/jechiu/dev/parallax/.venv/bin/python -m unittest \
  tests.test_docs tests.test_rendering -v
```

Expected: all documentation and rendering tests pass.

- [ ] **Step 5: Commit the Organizer contract**

```bash
git add SKILL.md AGENTS.md HARNESS.md README.md README.zh-TW.md tests/test_docs.py
git commit -m "docs(report): bind Traditional Chinese presentation contract"
```

### Task 3: Verify, publish, and synchronize the skill

**Files:**
- Verify all tracked files; no new production interface.
- Synchronize after push: `$HOME/.claude/skills/deep` and `$HOME/.codex/skills/claude-research-cascade`.

**Interfaces:**
- Consumes: Tasks 1-2 commits.
- Produces: a verified GitHub branch and identical global installations.

- [ ] **Step 1: Run the complete unit suite**

```bash
PYTHONPATH=. /Users/jechiu/dev/parallax/.venv/bin/python -m unittest discover -s tests -q
```

Expected: all tests pass; report the exact count from stdout.

- [ ] **Step 2: Install dev dependencies in an isolated project venv and run the release gate**

```bash
/Users/jechiu/dev/parallax/.venv/bin/python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/deep-research-release-gate
```

Expected: JSON `{"ok": true, ...}` after diff, clean-worktree, coverage >=80%, Ruff, installed CLI demo, build, Twine, and dependency-audit checks pass. If the gate rejects the feature worktree as dirty before the final commit, commit verified Tasks 1-2 first and rerun from the clean branch.

- [ ] **Step 3: Render and inspect the no-network demo report**

```bash
session=$(mktemp -d)/session
.venv/bin/deep-research-state demo "$session" --json
grep -F '<html lang="zh-Hant-TW">' "$session/report.html"
grep -F '決定性檢查結果' "$session/report.html"
```

Expected: demo returns `validation_ok: true`; both report checks find the Traditional Chinese output.

- [ ] **Step 4: Push the branch**

```bash
git push -u origin codex/zh-tw-html-report
```

Expected: GitHub accepts the branch with no force push.

- [ ] **Step 5: Synchronize global installations without secrets or caches**

After the branch is integrated into `master`, dry-run then synchronize the verified checkout into both global skill locations. Exclude `.git/`, `.worktrees/`, `.venv/`, `.env`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `build/`, and `dist/`. Preserve each existing ignored `.env` or symlink.

- [ ] **Step 6: Verify synchronized copies**

Run the full unit suite and skill validator from each global installation, compare checksums for `SKILL.md`, `HARNESS.md`, `AGENTS.md`, `research_harness/rendering.py`, and `tests/test_rendering.py`, and report exact counts.
