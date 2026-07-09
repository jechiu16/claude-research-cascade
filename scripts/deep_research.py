#!/usr/bin/env python3
"""Deep Research CLI — multi-provider research engine.

Providers:
  demo        local no-network smoke test        — validates JSON/report/ledger contract (free)
  sonar       Perplexity sonar-pro             — quick grounded answer (seconds, ~$0.01)
  cascade     4 parallel sonar probes           — scout: direct/counter/landscape/falsifier (~$0.10-0.15)
  scholar     Semantic Scholar paper search     — academic literature list (seconds, free)
  perplexity  Perplexity sonar-deep-research   — async deep research (2-5 min, ~$0.5-1)
  openai      OpenAI o3 / o4-mini deep research — async deep research (5-30 min, ~$0.4-8)
  gemini      Gemini Deep Research agent        — background interaction (2-10 min)
  deepseek    DeepSeek v4 processor             — merge/extract/rewrite over --files (~free)

Usage:
  python deep_research.py [--provider P] [--effort E] [--model M] [--timeout-min N] [--ledger FILE] "question"
  python deep_research.py --provider deepseek --files r1.md --files r2.md "merge these into a claims table"
  python deep_research.py --provider openai --submit-only "question"   # fire-and-return; harvest later
  python deep_research.py --resume "openai:resp_abc123"
  python deep_research.py --list-pending [--ledger FILE]               # unharvested async jobs

Output: single JSON object on stdout:
  {query, provider, model, effort, report_path, report, usage, cost_estimate_usd, wall_time_s}
Progress and the resume token go to stderr. Reports are saved to <cwd>/reports/.

Durability contract:
  - With --ledger, async submissions are journaled at submission time (event=submitted),
    so a killed process never loses a paid resume token.
  - If extraction of a completed job fails, the raw provider payload is saved to
    reports/deep_raw_*.json before the error is raised.
  - Ctrl-C / SIGINT during a poll still emits {"error": "interrupted", "resume": token}.

API keys (first hit wins): process env > nearest .env from cwd upward > <skill>/.env
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

def _fix_console_encoding():
    """Windows cp950 等 console 的 UTF-8 包裝 — 只在 CLI 模式呼叫，import 無副作用。
    line_buffering=True：stderr 被 redirect 到檔案（背景執行）時，進度與 resume token
    仍即時落盤，不滯留 buffer。"""
    for name in ("stdout", "stderr"):
        s = getattr(sys, name)
        if s and hasattr(s, "buffer"):
            setattr(sys, name, io.TextIOWrapper(s.buffer, encoding="utf-8", errors="replace",
                                                line_buffering=True))


SKILL_DIR = Path(__file__).resolve().parents[1]
PPLX_BASE = "https://api.perplexity.ai"
OPENAI_BASE = "https://api.openai.com"

# 跨層共享的 run 狀態：ledger 路徑（main 設定）與當前 async job 的 resume token
# （submit/resume 時設定）。放模組層是為了讓 KeyboardInterrupt handler 與
# submitted-event journaling 在任何深度都拿得到 token — 錢已付，token 不能丟。
_LEDGER_PATH = None
_CURRENT_RESUME = None

# USD per 1M tokens (input, output); web search $10 per 1k calls. OpenAI returns no
# cost field, so this is an estimate — Perplexity responses carry their own total_cost.
OPENAI_PRICE = {"o3-deep-research": (10.0, 40.0), "o4-mini-deep-research": (2.0, 8.0)}
OPENAI_SEARCH_PER_1K = 10.0
OPENAI_TOOL_CAP = {"minimal": 10, "low": 20, "medium": 40, "high": None}
RETRY_GET_STATUSES = {429, 500, 502, 503, 504}


def _load_env():
    try:
        from dotenv import load_dotenv, find_dotenv
    except ImportError:
        _log("python-dotenv not installed; skipping .env loading")
        return

    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(SKILL_DIR / ".env")


def _require_key(name: str) -> str:
    key = os.getenv(name)
    if not key:
        raise RuntimeError(f"{name} 未設定 — 放在專案 .env 或 {SKILL_DIR / '.env'}")
    return key


def _log(msg: str):
    print(f"[deep] {msg}", file=sys.stderr)


def _retry_delay(headers: dict, attempt: int, base_delay: float) -> float:
    retry_after = (headers or {}).get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), 30.0)
        except ValueError:
            pass
    return min(base_delay * (2 ** (attempt - 1)), 30.0)


def _get_with_retries(url: str, *, headers=None, params=None, timeout=30,
                      attempts=3, base_delay=1.0, label="GET"):
    """Retry safe GETs only. Paid submit POSTs intentionally do not use this."""
    import requests

    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
        except requests.RequestException as e:
            if attempt == attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
            _log(f"{label} transport error: {e}; retry in {delay:.1f}s ({attempt}/{attempts})")
            time.sleep(delay)
            continue
        if r.status_code not in RETRY_GET_STATUSES or attempt == attempts:
            return r
        delay = _retry_delay(r.headers, attempt, base_delay)
        _log(f"{label} HTTP {r.status_code}; retry in {delay:.1f}s ({attempt}/{attempts})")
        time.sleep(delay)
    raise RuntimeError(f"{label} retry loop exhausted")


def _post_with_retries(url: str, *, headers=None, json_body=None, timeout=120,
                       attempts=3, base_delay=1.0, label="POST"):
    """僅限低價同步呼叫（sonar ~$0.01）：transport / 429 / 5xx 重試的重複計費風險以
    美分計，換不丟內容划算。深度引擎的 submit POST 不走這裡 — 重複提交 = 重複整筆研究費。"""
    import requests

    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(url, headers=headers, json=json_body, timeout=timeout)
        except requests.RequestException as e:
            if attempt == attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
            _log(f"{label} transport error: {e}; retry in {delay:.1f}s ({attempt}/{attempts})")
            time.sleep(delay)
            continue
        if r.status_code not in RETRY_GET_STATUSES or attempt == attempts:
            return r
        delay = _retry_delay(r.headers, attempt, base_delay)
        _log(f"{label} HTTP {r.status_code}; retry in {delay:.1f}s ({attempt}/{attempts})")
        time.sleep(delay)
    raise RuntimeError(f"{label} retry loop exhausted")


class JobError(RuntimeError):
    """已提交、可續跑的 job 出錯 — resume token 隨錯誤結構化帶出，避免重付。
    terminal=True 表示 provider 端已終局（failed/cancelled/incomplete），resume 只供診斷；
    terminal=False（timeout / transport / 抽取失敗）表示 job 仍可收割。"""

    def __init__(self, message: str, resume: str = None, terminal: bool = False):
        super().__init__(message)
        self.resume = resume
        self.terminal = terminal


def _ledger_event(record: dict):
    """journaling 便門：main 設好 _LEDGER_PATH 後，任何深度都能落一筆事件。"""
    if _LEDGER_PATH:
        _append_ledger(_LEDGER_PATH, record)


def _mark_submitted(provider: str, rid: str, query: str = None, model: str = None,
                    effort: str = None) -> str:
    """async 提交成功的當下就落帳（event=submitted）— process 之後被殺，token 仍在帳本。"""
    global _CURRENT_RESUME
    token = f"{provider}:{rid}"
    _CURRENT_RESUME = token
    _log(f"resume token: {token}")
    rec = {"event": "submitted", "provider": provider, "resume": token}
    if model:
        rec["model"] = model
    if effort:
        rec["effort"] = effort
    if query:
        rec["query"] = query[:200]
    _ledger_event(rec)
    return token


def _save_raw(provider: str, rid: str, payload) -> Path:
    """已付費 payload 的最後防線：extract 崩掉前先把原始回應落盤。"""
    reports_dir = Path.cwd() / "reports"
    reports_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_rid = re.sub(r"[^A-Za-z0-9_-]+", "-", rid)[:32]
    path = reports_dir / f"deep_raw_{provider}_{ts}_{safe_rid}.json"
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        dump = getattr(payload, "model_dump", None) or getattr(payload, "to_dict", None)
        try:
            text = json.dumps(dump(), ensure_ascii=False, indent=2, default=str) if dump else repr(payload)
        except Exception:
            text = repr(payload)
    path.write_text(text, encoding="utf-8")
    _log(f"原始 payload 已存：{path}")
    return path


def _extract_guard(extract, data, provider: str, rid: str):
    """completed job 的抽取失敗（schema 漂移等）≠ 內容損失：raw 落盤後帶 token 拋錯，
    修好 extract 後 --resume 重收割（completed job 重 poll 立即返回，零額外成本）。"""
    try:
        return extract(data)
    except Exception as e:
        raw = _save_raw(provider, rid, data)
        raise JobError(f"抽取失敗（原始 payload 已存 {raw}）：{e}",
                       resume=f"{provider}:{rid}")


# ── Perplexity ────────────────────────────────────────────────────────────────

def _pplx_headers():
    return {"Authorization": f"Bearer {_require_key('PERPLEXITY_API_KEY')}",
            "Content-Type": "application/json"}


def _pplx_extract(data: dict, model: str, effort) -> dict:
    resp = data["response"]
    usage = resp.get("usage") or {}
    cost = (usage.get("cost") or {}).get("total_cost")
    sources = resp.get("search_results") or [{"url": u} for u in (resp.get("citations") or [])]
    return {
        "model": model,
        "effort": effort,
        "report_text": resp["choices"][0]["message"]["content"],
        "usage": usage,
        "cost_estimate_usd": round(cost, 4) if cost is not None else None,
        "sources": sources,
    }


def _pplx_poll(request_id: str, timeout_min: float) -> dict:
    headers = _pplx_headers()
    token = f"perplexity:{request_id}"
    t0 = time.monotonic()
    while True:
        elapsed = time.monotonic() - t0
        if elapsed > timeout_min * 60:
            raise JobError(f"輪詢超過 {timeout_min:.0f} 分鐘上限 — 稍後可 --resume \"{token}\"", resume=token)
        try:
            r = _get_with_retries(f"{PPLX_BASE}/v1/async/sonar/{request_id}",
                                  headers=headers, timeout=30, attempts=3,
                                  base_delay=1.0, label="perplexity poll")
        except Exception as e:
            raise JobError(f"poll transport 失敗：{e}", resume=token)
        if r.status_code != 200:
            raise JobError(f"poll 失敗 HTTP {r.status_code}: {r.text[:300]}", resume=token)
        data = r.json()
        status = data.get("status", "UNKNOWN")
        _log(f"狀態：{status}（{int(elapsed)}s）")
        if status == "COMPLETED":
            return data
        if status == "FAILED":
            raise JobError(f"研究失敗：{data.get('error_message', '（無錯誤訊息）')}",
                           resume=token, terminal=True)
        time.sleep(15)


def _pplx_submit(query: str, effort: str, model: str) -> str:
    import requests

    payload = {"request": {"model": model,
                           "messages": [{"role": "user", "content": query}],
                           "reasoning_effort": effort}}
    _log(f"啟動研究（perplexity/{model} effort={effort}）")
    r = requests.post(f"{PPLX_BASE}/v1/async/sonar", headers=_pplx_headers(), json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"submit 失敗 HTTP {r.status_code}: {r.text[:300]}")
    request_id = r.json()["id"]
    _mark_submitted("perplexity", request_id, query=query, model=model, effort=effort)
    return request_id


def call_perplexity(query: str, effort: str, model, timeout_min, files=None) -> dict:
    model = model or "sonar-deep-research"
    request_id = _pplx_submit(query, effort, model)
    data = _pplx_poll(request_id, timeout_min or 20)
    return _extract_guard(lambda d: _pplx_extract(d, model, effort), data, "perplexity", request_id)


def call_sonar(query: str, effort: str, model, timeout_min, files=None) -> dict:
    """Quick tier — synchronous grounded answer, no polling."""
    model = model or "sonar-pro"
    _log(f"快查（{model}）")
    r = _post_with_retries(f"{PPLX_BASE}/chat/completions", headers=_pplx_headers(),
                           json_body={"model": model, "messages": [{"role": "user", "content": query}]},
                           timeout=120, attempts=3, base_delay=1.0, label="sonar")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    usage = data.get("usage") or {}
    cost = (usage.get("cost") or {}).get("total_cost")
    sources = data.get("search_results") or [{"url": u} for u in (data.get("citations") or [])]
    return {
        "model": model,
        "effort": None,
        "report_text": data["choices"][0]["message"]["content"],
        "usage": usage,
        "cost_estimate_usd": round(cost, 4) if cost is not None else None,
        "sources": sources,
    }


# ── 探針瀑布（scout）──────────────────────────────────────────────────────────

CASCADE_FRAMINGS = [
    ("direct", "{q}"),
    ("counter", "What is the strongest counterargument or opposing evidence to the following? {q}"),
    ("landscape", "What are the key terms, main players, and notable recent developments relevant to: {q}"),
    ("falsifier", "What specific evidence, if it existed, would most change the answer to: {q}"),
]


def call_cascade(query: str, effort: str, model, timeout_min, files=None) -> dict:
    """Scout：四個框架並行快查，一次呼叫回齊 — 取代多個背景 sonar call 的編排負擔。"""
    from concurrent.futures import ThreadPoolExecutor

    _log(f"探針瀑布：{len(CASCADE_FRAMINGS)} 發並行（sonar-pro）")

    def one(framing):
        name, tpl = framing
        try:
            return name, call_sonar(tpl.format(q=query), effort, model, timeout_min), None
        except Exception as e:  # 單發失敗不拖垮整組
            return name, None, str(e)

    with ThreadPoolExecutor(max_workers=len(CASCADE_FRAMINGS)) as ex:
        results = list(ex.map(one, CASCADE_FRAMINGS))

    parts, sources, seen, usage, failures = [], [], set(), {}, {}
    total_cost = 0.0
    for name, r, err in results:
        if err:
            failures[name] = err
            parts.append(f"## 探針：{name}\n\n（失敗：{err}）")
            continue
        parts.append(f"## 探針：{name}\n\n{r['report_text']}")
        usage[name] = r.get("usage", {})
        total_cost += r.get("cost_estimate_usd") or 0.0
        for s in r.get("sources", []):
            url = s.get("url", "")
            if url and url not in seen:
                seen.add(url)
                sources.append(s)

    if len(failures) == len(CASCADE_FRAMINGS):
        raise RuntimeError(f"cascade 全數探針失敗：{failures}")
    if failures:
        usage["_failures"] = failures
    return {"model": f"sonar-pro ×{len(CASCADE_FRAMINGS)}", "effort": None,
            "report_text": "\n\n".join(parts),
            "usage": usage, "cost_estimate_usd": round(total_cost, 4), "sources": sources}


# ── Semantic Scholar ──────────────────────────────────────────────────────────

S2_FIELDS = "title,year,abstract,citationCount,authors,url,openAccessPdf,tldr"
S2_LIMIT = {"minimal": 5, "low": 10, "medium": 20, "high": 40}


def call_scholar(query: str, effort: str, model, timeout_min, files=None) -> dict:
    """Academic literature search. Query = keyword phrase, not a question. 1 req/sec."""
    key = os.getenv("S2_API_KEY")
    headers = {"x-api-key": key} if key else {}
    if not key:
        _log("無 S2_API_KEY — 走共享池（限速更嚴、可能 429）")
    limit = S2_LIMIT.get(effort, 20)
    params = {"query": query, "limit": limit, "fields": S2_FIELDS}
    _log(f"文獻檢索（semantic scholar, limit={limit}）")
    r = _get_with_retries("https://api.semanticscholar.org/graph/v1/paper/search",
                          headers=headers, params=params, timeout=30,
                          attempts=3, base_delay=1.5, label="semantic scholar")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    papers = data.get("data") or []

    lines = [f"## 文獻檢索結果（{len(papers)} / 共 {data.get('total', '?')} 篇，按相關性）\n"]
    sources = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:4])
        if len(p.get("authors") or []) > 4:
            authors += " et al."
        tldr = (p.get("tldr") or {}).get("text") or (p.get("abstract") or "")[:300]
        pdf = (p.get("openAccessPdf") or {}).get("url")
        url = p.get("url", "")
        lines.append(f"\n{i}. **{p.get('title', '?')}**（{p.get('year', '?')}）— 引用 {p.get('citationCount', 0)}\n")
        lines.append(f"   {authors}\n")
        if tldr:
            lines.append(f"   {tldr}\n")
        link = f"   [S2]({url})"
        if pdf:
            link += f" ｜ [PDF]({pdf})"
        lines.append(link + "\n")
        if url:
            sources.append({"title": p.get("title") or url,
                            "url": url,
                            "date": str(p.get("year")) if p.get("year") else None,
                            "citationCount": p.get("citationCount", 0)})

    return {"model": "s2-graph/paper-search", "effort": effort,
            "report_text": "".join(lines),
            "usage": {"total_results": data.get("total"), "returned": len(papers)},
            "cost_estimate_usd": 0.0, "sources": sources}


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _openai_headers():
    return {"Authorization": f"Bearer {_require_key('OPENAI_API_KEY')}",
            "Content-Type": "application/json"}


def _openai_extract(data: dict, model: str, effort) -> dict:
    text, sources, searches, seen = "", [], 0, set()
    for item in data.get("output", []):
        kind = item.get("type")
        if kind == "web_search_call":
            searches += 1
        elif kind == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text += c.get("text", "")
                    for a in c.get("annotations") or []:
                        url = a.get("url", "")
                        if a.get("type") == "url_citation" and url and url not in seen:
                            seen.add(url)
                            sources.append({"title": a.get("title") or url, "url": url})
    usage = dict(data.get("usage") or {})
    usage["num_web_searches"] = searches
    p_in, p_out = OPENAI_PRICE.get(model, (0.0, 0.0))
    cost = ((usage.get("input_tokens") or 0) * p_in / 1e6
            + (usage.get("output_tokens") or 0) * p_out / 1e6
            + searches * OPENAI_SEARCH_PER_1K / 1e3)
    return {
        "model": model,
        "effort": effort,
        "report_text": text,
        "usage": usage,
        "cost_estimate_usd": round(cost, 4),
        "sources": sources,
    }


def _openai_poll(resp_id: str, timeout_min: float) -> dict:
    headers = _openai_headers()
    token = f"openai:{resp_id}"
    t0 = time.monotonic()
    while True:
        elapsed = time.monotonic() - t0
        if elapsed > timeout_min * 60:
            raise JobError(f"輪詢超過 {timeout_min:.0f} 分鐘上限 — 稍後可 --resume \"{token}\"", resume=token)
        try:
            r = _get_with_retries(f"{OPENAI_BASE}/v1/responses/{resp_id}",
                                  headers=headers, timeout=30, attempts=3,
                                  base_delay=1.0, label="openai poll")
        except Exception as e:
            raise JobError(f"poll transport 失敗：{e}", resume=token)
        if r.status_code != 200:
            raise JobError(f"poll 失敗 HTTP {r.status_code}: {r.text[:300]}", resume=token)
        data = r.json()
        status = data.get("status", "unknown")
        _log(f"狀態：{status}（{int(elapsed)}s）")
        if status == "completed":
            return data
        if status in ("failed", "cancelled", "incomplete"):
            err = (data.get("error") or {}).get("message", "")
            if status == "incomplete":
                # incomplete 是終局狀態但常帶部分產出 — 落盤保錢，不默默當完整結果交付
                raw = _save_raw("openai", resp_id, data)
                raise JobError(f"研究以 incomplete 收場（部分產出已存 {raw}）：{err[:300]}",
                               resume=token, terminal=True)
            raise JobError(f"研究失敗，狀態 {status}：{err[:300]}", resume=token, terminal=True)
        time.sleep(20)


def _openai_submit(query: str, effort: str, model: str) -> str:
    import requests

    body = {"model": model, "input": query, "background": True,
            "tools": [{"type": "web_search_preview"}]}
    cap = OPENAI_TOOL_CAP.get(effort)
    if cap:
        body["max_tool_calls"] = cap
    _log(f"啟動研究（openai/{model} effort={effort} tool_cap={cap}）")
    r = requests.post(f"{OPENAI_BASE}/v1/responses", headers=_openai_headers(), json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"submit 失敗 HTTP {r.status_code}: {r.text[:300]}")
    resp_id = r.json()["id"]
    _mark_submitted("openai", resp_id, query=query, model=model, effort=effort)
    return resp_id


def call_openai(query: str, effort: str, model, timeout_min, files=None) -> dict:
    model = model or ("o3-deep-research" if effort == "high" else "o4-mini-deep-research")
    resp_id = _openai_submit(query, effort, model)
    data = _openai_poll(resp_id, timeout_min or 45)
    return _extract_guard(lambda d: _openai_extract(d, model, effort), data, "openai", resp_id)


# ── Gemini ────────────────────────────────────────────────────────────────────

def _gemini_client():
    from google import genai

    return genai.Client(api_key=_require_key("GEMINI_API_KEY"))


def _gemini_poll(client, interaction_id: str, timeout_min: float):
    token = f"gemini:{interaction_id}"
    t0 = time.monotonic()
    while True:
        elapsed = time.monotonic() - t0
        if elapsed > timeout_min * 60:
            raise JobError(f"輪詢超過 {timeout_min:.0f} 分鐘上限 — 稍後可 --resume \"{token}\"", resume=token)
        interaction = client.interactions.get(interaction_id)
        status = interaction.status
        _log(f"狀態：{status}（{int(elapsed)}s）")
        if status == "completed":
            return interaction
        if status in ("failed", "cancelled"):
            raise JobError(f"研究失敗，狀態：{status}", resume=token, terminal=True)
        time.sleep(15)


def _gemini_extract(interaction, agent: str) -> dict:
    # 新 schema（Interactions API 2026-05+）。文件的 steps[-1] 說法不可靠：實測正文與來源
    # 可能分佈在不同 step，且單一 step 的 text 可拆多個 content part。策略：逐 step 聚合
    # text，優先非 grounding/citation 類 step，再以長度 tie-break。
    steps = getattr(interaction, "steps", None) or []
    candidates = []
    for st in steps:
        label = " ".join(str(getattr(st, a, "") or "") for a in ("type", "name", "title")).lower()
        text = "\n\n".join(c.text for c in (getattr(st, "content", None) or [])
                           if getattr(c, "text", None))
        if text.strip():
            candidates.append((label, text))
    bodyish = [c for c in candidates if not re.search(r"ground|source|citation|search", c[0])]
    # 長報告會拆多個 step（實測 6.6k+14.7k+22.8k 三段）— 按序串接所有實質本體段，
    # 不取最長（會丟前半）；<600 字的段視為 query 回音/狀態訊息排除
    substantial = [c[1] for c in (bodyish or candidates) if len(c[1]) >= 600]
    if substantial:
        report_text = "\n\n".join(substantial)
    else:
        report_text = max(bodyish or candidates, key=lambda c: len(c[1]))[1] if candidates else ""
    if not report_text:  # 舊 schema fallback（萬一）
        report_text = "".join(o.text for o in (getattr(interaction, "outputs", None) or [])
                              if getattr(o, "text", None))
    if not report_text.strip():
        raise RuntimeError("Gemini 回報 completed 但 steps/outputs 都抽不到報告文字")
    # Gemini deep research 把來源以 markdown links 直接寫進報告本體（report_text 末尾），
    # 無獨立結構化 citations 欄位 — sources 留空，避免與內建來源段重複渲染。
    return {"model": agent, "effort": None, "report_text": report_text,
            "usage": {}, "cost_estimate_usd": None, "sources": []}


def _gemini_submit(client, query: str, agent: str) -> str:
    _log(f"啟動研究（gemini/{agent}）")
    interaction = client.interactions.create(input=query, agent=agent, background=True)
    _mark_submitted("gemini", interaction.id, query=query, model=agent)
    return interaction.id


def call_gemini(query: str, effort: str, model, timeout_min, files=None) -> dict:
    # 呼叫方式與舊版相同（走 **body）；差別在輸出解析（steps schema，見 _gemini_extract）。
    # model 可選 deep-research-preview-04-2026（預設）或 deep-research-max-preview-04-2026。
    client = _gemini_client()
    agent = model or "deep-research-preview-04-2026"
    interaction_id = _gemini_submit(client, query, agent)
    interaction = _gemini_poll(client, interaction_id, timeout_min or 30)
    return _extract_guard(lambda d: _gemini_extract(d, agent), interaction, "gemini", interaction_id)


# ── DeepSeek（加工層，不是研究引擎：無檢索、裸答事實幻覺率高）────────────────

def call_deepseek(query: str, effort: str, model, timeout_min, files=None) -> dict:
    import requests

    model = model or "deepseek-v4-pro"
    content = query
    for f in files or []:
        p = Path(f)
        content += f"\n\n=== FILE: {p.name} ===\n{p.read_text(encoding='utf-8', errors='replace')}"
    _log(f"加工（deepseek/{model}，{len(files or [])} 個檔案輸入）")
    # v4-pro 思考模式拒收 temperature/top_p — 不送；長輸出用 max_tokens 上限
    r = requests.post("https://api.deepseek.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {_require_key('DEEPSEEK_API_KEY')}",
                               "Content-Type": "application/json"},
                      json={"model": model,
                            "messages": [{"role": "user", "content": content}],
                            "max_tokens": 16384},
                      timeout=(30, 900))
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    return {"model": model, "effort": None,
            "report_text": data["choices"][0]["message"]["content"],
            "usage": data.get("usage") or {},
            "cost_estimate_usd": None, "sources": []}


def call_demo(query: str, effort: str, model, timeout_min, files=None) -> dict:
    """Local smoke-test provider: no network, no keys, same output contract."""
    model = model or "demo-local"
    _log("demo provider: no network, no external API, no cost")
    report_text = f"""# Demo Worker Result

This is a local smoke test for `scripts/deep_research.py`. It proves that the worker can:

- parse CLI arguments
- write a report under `<cwd>/reports/`
- print one JSON object on stdout
- append a ledger record when `--ledger` is supplied

It does **not** perform research and must not be used as evidence.

## Echo

Query: {query}
Effort: {effort}
"""
    return {"model": model, "effort": effort,
            "report_text": report_text,
            "usage": {"demo": True, "input_chars": len(query), "files": len(files or [])},
            "cost_estimate_usd": 0.0, "sources": []}


PROVIDERS = {"demo": call_demo, "sonar": call_sonar, "cascade": call_cascade, "scholar": call_scholar,
             "perplexity": call_perplexity, "openai": call_openai, "gemini": call_gemini,
             "deepseek": call_deepseek}


# ── Report + entry ────────────────────────────────────────────────────────────

def _slug(query: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", query).strip("-").lower()
    return s[:40].rstrip("-") or "query"


def save_report(provider: str, query: str, result: dict, wall_time_s: float) -> Path:
    reports_dir = Path.cwd() / "reports"
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 純 CJK query 的 slug 會退化成 "query" — hash(query+pid) 防同秒並行互相覆蓋
    digest = hashlib.sha1(f"{query}|{os.getpid()}".encode("utf-8")).hexdigest()[:6]
    report_path = reports_dir / f"deep_{timestamp}_{_slug(query)}_{digest}.md"

    lines = [
        "# Deep Research 報告\n",
        f"**查詢：** {query}\n",
        f"**時間：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"**Provider：** {provider}（{result['model']}）\n",
    ]
    if result.get("effort"):
        lines.append(f"**Effort：** {result['effort']}\n")
    lines.append(f"**Wall time：** {wall_time_s:.0f}s\n")
    if result.get("usage"):
        lines.append(f"**Usage：** `{json.dumps(result['usage'], ensure_ascii=False)}`\n")
    if result.get("cost_estimate_usd") is not None:
        lines.append(f"**成本估算：** ${result['cost_estimate_usd']:.4f}\n")
    lines.append("\n---\n\n")
    lines.append(result["report_text"])

    if result.get("sources"):
        lines.append("\n\n---\n\n## Sources\n\n")
        for s in result["sources"]:
            title = (s.get("title") or s.get("url", "")).replace("[", "\\[").replace("]", "\\]")
            url = s.get("url", "").replace(")", "%29")
            date = f"（{s['date']}）" if s.get("date") else ""
            lines.append(f"- [{title}]({url}){date}\n")

    report_path.write_text("".join(lines), encoding="utf-8")
    _log(f"報告已存：{report_path}")
    return report_path


def _finish(provider: str, query: str, result: dict, wall_time_s: float) -> dict:
    try:
        report_path = str(save_report(provider, query, result, wall_time_s))
    except OSError as e:
        # 存檔失敗 ≠ 內容損失：report 全文仍走 stdout JSON 交給 host
        _log(f"報告存檔失敗（內容仍在 stdout JSON）：{e}")
        report_path = None
    return {
        "query": query,
        "provider": provider,
        "model": result["model"],
        "effort": result.get("effort"),
        "report_path": report_path,
        "report": result["report_text"],
        "usage": result.get("usage", {}),
        "cost_estimate_usd": result.get("cost_estimate_usd"),
        "wall_time_s": round(wall_time_s, 1),
    }


def _append_ledger(path: str, record: dict):
    """機械 hook：append-only JSONL 帳本 — 記帳不靠 Organizer 自覺。
    Best-effort：並行 worker 各寫一行；單行 append 實務上夠原子（單次 write），但不做
    跨程序鎖 — 讀取端應逐行解析、容忍極少數崩潰殘行。寫入失敗不影響主流程。"""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)  # fresh session 首個動作即失敗時 reports/ 尚未建
        record["ts"] = datetime.now().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        _log(f"ledger 寫入失敗（不影響結果）：{e}")


def run(provider: str, query: str, effort: str, model, timeout_min, files=None) -> dict:
    t0 = time.monotonic()
    result = PROVIDERS[provider](query, effort, model, timeout_min, files=files)
    return _finish(provider, query, result, time.monotonic() - t0)


ASYNC_PROVIDERS = ("perplexity", "openai", "gemini")


def run_submit_only(provider: str, query: str, effort: str, model) -> dict:
    """提交即返回 — 多引擎 decision wave 的並行原語：一輪 --submit-only 齊發，
    再逐一 --resume 收割。submitted 事件已由 _mark_submitted 落帳。"""
    if provider == "perplexity":
        model = model or "sonar-deep-research"
        rid = _pplx_submit(query, effort, model)
    elif provider == "openai":
        model = model or ("o3-deep-research" if effort == "high" else "o4-mini-deep-research")
        rid = _openai_submit(query, effort, model)
    elif provider == "gemini":
        model = model or "deep-research-preview-04-2026"
        rid = _gemini_submit(_gemini_client(), query, model)
    else:
        raise RuntimeError(f"--submit-only 只支援 async providers（{'/'.join(ASYNC_PROVIDERS)}），"
                           f"收到：{provider}")
    token = f"{provider}:{rid}"
    return {"submitted": True, "provider": provider, "model": model, "effort": effort,
            "resume": token, "query": query, "next": f'--resume "{token}"'}


def run_resume(token: str, timeout_min) -> dict:
    global _CURRENT_RESUME
    provider, _, rid = token.partition(":")
    if not rid:
        raise RuntimeError(f'--resume 格式是 "provider:id"，收到：{token}')
    _CURRENT_RESUME = token
    t0 = time.monotonic()
    if provider == "perplexity":
        data = _pplx_poll(rid, timeout_min or 20)
        model = (data.get("response") or {}).get("model") or "sonar-deep-research"
        result = _extract_guard(lambda d: _pplx_extract(d, model, None), data, provider, rid)
    elif provider == "openai":
        data = _openai_poll(rid, timeout_min or 45)
        result = _extract_guard(lambda d: _openai_extract(d, d.get("model", "?"), None), data, provider, rid)
    elif provider == "gemini":
        client = _gemini_client()
        interaction = _gemini_poll(client, rid, timeout_min or 30)
        agent = getattr(interaction, "agent", None) or "deep-research-preview-04-2026"
        result = _extract_guard(lambda d: _gemini_extract(d, agent), interaction, provider, rid)
    else:
        raise RuntimeError(f"provider {provider} 不支援 resume（sonar / scholar / deepseek 為同步呼叫）")
    return _finish(provider, f"[resumed] {token}", result, time.monotonic() - t0)


def scan_pending(ledger_paths) -> list:
    """從帳本找『已提交未收割』的 async job。submitted / 非終局 failed / interrupted = pending；
    completed 或 terminal failed = cleared。逐行解析、容忍殘行（帳本契約如此）。"""
    state = {}
    for path in ledger_paths:
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            token = rec.get("resume")
            if not token:
                continue
            if rec.get("event") == "completed" or (rec.get("event") == "failed" and rec.get("terminal")):
                state[token] = ("cleared", rec, str(path))
            elif state.get(token, ("",))[0] != "cleared":
                state[token] = ("pending", rec, str(path))
    return [{"resume": token, "ledger": path, "last_event": rec}
            for token, (status, rec, path) in state.items() if status == "pending"]


if __name__ == "__main__":
    _fix_console_encoding()
    parser = argparse.ArgumentParser(description="Deep Research CLI（多 provider）")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="perplexity")
    parser.add_argument("--effort", choices=["minimal", "low", "medium", "high"], default="medium",
                        help="perplexity: reasoning_effort；openai: high→o3、其餘 o4-mini+tool cap；sonar/gemini 忽略")
    parser.add_argument("--model", default=None, help="覆寫該 provider 的預設 model")
    parser.add_argument("--timeout-min", type=float, default=None, help="輪詢上限（分鐘）")
    parser.add_argument("--resume", default=None, metavar="PROVIDER:ID", help="接手先前的 async job")
    parser.add_argument("--submit-only", action="store_true",
                        help="async provider 提交即返回（印 resume token），不輪詢 — 多引擎並行 wave 用")
    parser.add_argument("--list-pending", action="store_true",
                        help="掃描帳本列出已提交未收割的 async job（不打網路、不花錢）")
    parser.add_argument("--files", action="append", default=None, metavar="FILE",
                        help="deepseek 加工層的檔案輸入（一面旗一個檔，可重複）")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="append-only JSONL 帳本（harness 機械 hook）")
    parser.add_argument("query", nargs="*", help="研究問題")
    args = parser.parse_args()

    if args.list_pending:
        paths = [args.ledger] if args.ledger else sorted(Path.cwd().glob("reports/*.ledger.jsonl"))
        pending = scan_pending(paths)
        print(json.dumps({"pending": pending, "scanned": [str(p) for p in paths]},
                         ensure_ascii=False, indent=2))
        sys.exit(0)
    if args.submit_only and args.resume:
        parser.error("--submit-only 與 --resume 互斥（一個是提交、一個是收割）")
    if not args.resume and not args.query:
        parser.error("需要 query（或 --resume / --list-pending）")
    if args.files and args.provider != "deepseek":
        parser.error("--files 只支援 --provider deepseek（加工層）— 其他 provider 會默默忽略檔案")

    _load_env()
    _LEDGER_PATH = args.ledger  # module-scope：submitted / interrupted 事件從任何深度落帳
    try:
        if args.submit_only:
            out = run_submit_only(args.provider, " ".join(args.query), args.effort, args.model)
        elif args.resume:
            out = run_resume(args.resume, args.timeout_min)
        else:
            out = run(args.provider, " ".join(args.query), args.effort, args.model, args.timeout_min, files=args.files)
        if args.ledger and not out.get("submitted"):
            rec = {"event": "completed", "provider": out["provider"], "model": out["model"],
                   "effort": out.get("effort"), "cost_usd": out.get("cost_estimate_usd"),
                   "wall_s": out.get("wall_time_s"), "artifact": out.get("report_path"),
                   "query": out["query"][:200]}
            if _CURRENT_RESUME:
                rec["resume"] = _CURRENT_RESUME  # 讓 --list-pending 能配對清掉這筆
            _append_ledger(args.ledger, rec)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        token = _CURRENT_RESUME
        _ledger_event({"event": "interrupted",
                       "provider": (token or "").split(":")[0] or args.provider, "resume": token})
        print(json.dumps({"error": "interrupted", "resume": token}, ensure_ascii=False))
        sys.exit(130)
    except JobError as e:
        # provider 從 resume token 前綴取（--resume 未帶 --provider 時 args.provider 是 default）
        led_prov = (e.resume or args.resume or "").split(":")[0] or args.provider
        if args.ledger:
            _append_ledger(args.ledger, {"event": "failed", "provider": led_prov,
                                         "error": str(e)[:300], "resume": e.resume,
                                         "terminal": e.terminal})
        # 失敗也印 stdout（成功/失敗一致走 stdout；host 讀 stdout 拿 JSON，exit code 非零標示失敗）
        print(json.dumps({"error": str(e), "resume": e.resume, "terminal": e.terminal},
                         ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        led_prov = (args.resume or "").split(":")[0] or args.provider
        if args.ledger:
            _append_ledger(args.ledger, {"event": "failed", "provider": led_prov,
                                         "error": str(e)[:300], "terminal": True})
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
