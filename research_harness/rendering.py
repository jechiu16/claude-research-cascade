"""Deterministic, escaped HTML projection of canonical research state."""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .state import state_sha256
from .storage import (
    ORGANIZER_ROOTS,
    _append_event_unlocked,
    _atomic_write_bytes_unlocked,
    _commit_patch_unlocked,
    _load_state_unlocked,
    _read_events_unlocked,
    _recover_session_unlocked,
    session_lock,
)
from .validation import (
    ValidationReport,
    _renderable_human_reasons,
    _validate_loaded_session,
    tier_shortfall_labels,
)


@dataclass(frozen=True)
class RenderedReport:
    path: Path
    validation: ValidationReport
    state_sha256: str
    report_sha256: str


def _escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _pill(label: Any, kind: str = "neutral") -> str:
    return f'<span class="pill {kind}">{_escape(label)}</span>'


def _empty(label: str) -> str:
    return f'<p class="empty">{_escape(label)}</p>'


def _boolean_label(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "未記錄"


def _text_list(values: Any, empty_label: str = "尚未記錄") -> str:
    if not isinstance(values, list) or not values:
        return _empty(empty_label)
    return "<ul>" + "".join(f"<li>{_escape(value)}</li>" for value in values) + "</ul>"


def _render_safe_action(action: dict[str, Any]) -> str:
    return (
        '<article class="safe-action">'
        f'<h3>{_escape(action.get("id"))}: {_escape(action.get("description", "安全行動"))}</h3>'
        f'<p>可逆：{_boolean_label(action.get("reversible"))}</p>'
        f'<p>依賴主張：{_escape(", ".join(action.get("depends_on_claim_ids", [])) or "無")}</p>'
        "</article>"
    )


def _human_limitations(state: dict[str, Any], insufficient: bool = False) -> str:
    handoff = state.get("engineering_handoff", {})
    values = list(handoff.get("constraints", []))
    values.extend(state.get("open_questions", []))
    values.extend(
        claim.get("would_change_if")
        for claim in state.get("claims", [])
        if isinstance(claim, dict) and claim.get("would_change_if")
    )
    if insufficient:
        values.append("尚缺足夠的直接來源，結論可能改變")
    return _text_list(values, "尚未記錄限制或翻轉條件")


def _artifact_link(artifact: dict[str, Any] | None) -> str:
    if not artifact:
        return ""
    relative = artifact.get("relative_path")
    if (
        artifact.get("availability") != "available"
        or artifact.get("include_in_html") is not True
        or artifact.get("sensitivity") not in {"public", "internal"}
        or not isinstance(relative, str)
        or not relative.startswith("raw/")
        or ".." in Path(relative).parts
    ):
        return ""
    return f' <a class="artifact-link" href="{_escape(relative)}">原始資料</a>'


def _render_claims(state: dict[str, Any]) -> str:
    claims = state.get("claims", [])
    if not claims:
        return _empty("尚未記錄正式主張")
    rows: list[str] = []
    for claim in claims:
        load = _pill("關鍵主張", "critical") if claim.get("load_bearing") else ""
        status = _pill(claim.get("status", "未記錄狀態"), "status")
        qualifiers = _text_list(claim.get("qualifiers", []), "無限定條件")
        evidence = ", ".join(_escape(item) for item in claim.get("supporting_evidence_ids", [])) or "無"
        rows.append(
            '<article class="claim">'
            f'<div class="claim-head"><code>{_escape(claim.get("id"))}</code>{load}{status}</div>'
            f'<h3>{_escape(claim.get("text", "未命名主張"))}</h3>'
            f'<p><strong>範圍:</strong> {_escape(claim.get("scope", "未記錄"))}</p>'
            f'<p><strong>適用性:</strong> {_escape(claim.get("applicability", "未檢查"))}</p>'
            f'<p><strong>支持證據:</strong> {evidence}</p>'
            f'<details><summary>限定條件與翻轉條件</summary>{qualifiers}'
            f'<p><strong>重新評估條件:</strong> {_escape(claim.get("would_change_if", "未記錄"))}</p>'
            "</details></article>"
        )
    return "".join(rows)


def _render_evidence(state: dict[str, Any]) -> str:
    evidence_records = state.get("evidence", [])
    if not evidence_records:
        return _empty("尚未納入證據紀錄")
    artifacts = {
        artifact.get("id"): artifact
        for artifact in state.get("artifact_index", [])
        if isinstance(artifact, dict)
    }
    blocks: list[str] = []
    for evidence in evidence_records:
        excerpt = evidence.get("excerpt")
        excerpt = excerpt if isinstance(excerpt, str) else ""
        bounded = excerpt[:2000]
        truncation = '<p class="note">摘錄過長，顯示內容已截斷。</p>' if len(excerpt) > 2000 else ""
        artifact = artifacts.get(evidence.get("artifact_id"))
        blocks.append(
            "<details class=\"evidence\">"
            f'<summary><code>{_escape(evidence.get("id"))}</code> '
            f'{_escape(evidence.get("source_tier", "未記錄來源層級"))} / '
            f'{_escape(evidence.get("entailment", "未記錄推論關係"))}</summary>'
            '<div class="evidence-meta">'
            f'<span>來源 {_escape(evidence.get("source_id"))}</span>'
            f'<span>起源 {_escape(evidence.get("origin_id"))}</span>'
            f'<span>資料檔 {_escape(evidence.get("artifact_id"))}{_artifact_link(artifact)}</span>'
            "</div>"
            f'<blockquote>{_escape(bounded)}</blockquote>{truncation}'
            f'<p class="offsets">原文位元組範圍: {_escape(evidence.get("excerpt_start"))}..'
            f'{_escape(evidence.get("excerpt_end"))}</p>'
            "</details>"
        )
    return "".join(blocks)


def _render_sources(state: dict[str, Any]) -> str:
    origins = {
        origin.get("id"): origin
        for origin in state.get("source_origins", [])
        if isinstance(origin, dict)
    }
    sources = state.get("sources", [])
    if not sources:
        return _empty("尚未記錄來源")
    rows: list[str] = []
    for source in sources:
        origin = origins.get(source.get("origin_id"), {})
        url = source.get("url")
        title = _escape(source.get("title", source.get("id", "未命名來源")))
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            title = f'<a href="{_escape(url)}">{title}</a>'
        rows.append(
            "<tr>"
            f'<td><code>{_escape(source.get("id"))}</code></td><td>{title}</td>'
            f'<td>{_escape(source.get("tier", "未記錄來源層級"))}</td>'
            f'<td>{_escape(source.get("origin_id"))}</td>'
            f'<td>{_escape(origin.get("kind", "未記錄起源類型"))}</td>'
            f'<td>{_boolean_label(source.get("direct_fetch"))}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>ID</th><th>來源標題</th><th>來源層級</th>'
        '<th>起源</th><th>起源類型</th><th>直接擷取</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _render_verification(state: dict[str, Any]) -> str:
    records = state.get("verification", [])
    if not records:
        return _empty("尚未記錄驗證")
    return '<div class="verification-grid">' + "".join(
        '<article class="verification">'
        f'<code>{_escape(item.get("id"))}</code><h3>{_escape(item.get("kind", "未記錄驗證類型"))}</h3>'
        f'<p>已完成：{_boolean_label(item.get("completed"))}</p>'
        f'<p>上下文分離：{_boolean_label(item.get("context_separated"))}</p>'
        "</article>"
        for item in records
    ) + "</div>"


def _render_validation(report: ValidationReport) -> str:
    if not report.issues:
        return '<p class="gate-ok">所有決定性檢查均已通過。</p>'
    return "<ul class=\"issues\">" + "".join(
        f'<li class="{_escape(issue.level.lower())}"><strong>{_escape(issue.level)} '
        f'{_escape(issue.code)}</strong>: {_escape(issue.message)} <code>{_escape(issue.path)}</code></li>'
        for issue in report.issues
    ) + "</ul>"


def _render_human_reasons(state: dict[str, Any]) -> str:
    reasons: list[str] = []
    linked_sources: list[dict[str, Any]] = []
    for claim, sources in _renderable_human_reasons(state)[:3]:
        links: list[str] = []
        for source in sources:
            url = source["url"]
            title = source["title"]
            linked_sources.append(source)
            links.append(f'<a href="{_escape(url)}">{_escape(title)}</a>')
        suffix = "（" + "、".join(links) + "）" if links else ""
        reasons.append(f"<li>{_escape(claim.get('text', '未命名主張'))}{suffix}</li>")
    if not reasons:
        return _empty("尚未記錄核心理由")
    upstream_keys = {source.get("upstream_key") for source in linked_sources}
    if not upstream_keys or "unknown" in upstream_keys:
        upstream_label = "未知"
    elif len(upstream_keys) == 1:
        upstream_label = "相同"
    else:
        upstream_label = "不同"
    return (
        "<ul class=\"reason-list\">"
        + "".join(reasons)
        + "</ul><p><strong>上游關係：</strong>"
        + upstream_label
        + "</p>"
    )


def render_html(state: dict[str, Any], report: ValidationReport) -> str:
    """Render one state snapshot without reading clocks, files, or the network."""

    canonical_hash = state_sha256(state)
    valid = not report.errors and report.state_sha256 == canonical_hash
    summary = state.get("summary", {})
    contract = state.get("contract", {})
    status = summary.get("status", "未記錄狀態")
    organizer_recommendation = (
        report.human_recommendation or summary.get("human_recommendation") or "尚未記錄建議"
    )
    shortfall_human_status, shortfall_technical_status = tier_shortfall_labels(report.issues)
    display_status = str(status) if valid else f"{status} / INVALID"
    if valid and not report.tier_contract_met:
        display_status = f"BLOCKED / {shortfall_technical_status}"
    status_class = (
        "invalid"
        if not valid
        else "blocked"
        if not report.tier_contract_met
        else "pass"
        if status == "PASS"
        else "partial"
    )
    recommendation = organizer_recommendation
    human_status = report.human_status or summary.get("human_status") or "尚未記錄研究判斷"
    if not valid:
        human_status = "驗證未通過"
        recommendation = "驗證未通過，暫不作建議"
    elif not report.tier_contract_met:
        human_status = shortfall_human_status
        recommendation = f"{shortfall_human_status}，暫不作肯定建議"
    ceilings = contract.get("resource_envelope", {}).get("physical_ceiling", {})
    cost_budget = contract.get("resource_envelope", {}).get("cost_budget", {})
    public_profile = cost_budget.get("profile") or contract.get("tier", "未記錄成本層級")
    cost_rows = "".join(
        f'<tr><td>{_escape(cost_class)}</td><td>{_escape(cost_budget.get(cost_class))}</td></tr>'
        for cost_class in ("deep", "search", "free")
        if cost_class in cost_budget
    )
    quota_rows = "".join(
        f'<tr><td>{_escape(category)}</td><td>{_escape(count)}</td></tr>'
        for category, count in sorted(ceilings.items())
    )
    safe_actions = state.get("engineering_handoff", {}).get("safe_actions", [])
    safe_action_records = [action for action in safe_actions if isinstance(action, dict)]
    safe_action_html = (
        _empty("尚未記錄安全行動")
        if not safe_action_records
        else "".join(_render_safe_action(action) for action in safe_action_records)
    )
    first_reversible_action = next(
        (action for action in safe_action_records if action.get("reversible") is True), None
    )
    first_safe_action_html = (
        _render_safe_action(first_reversible_action)
        if first_reversible_action is not None
        else _empty("尚未記錄可逆安全行動")
    )
    if not valid:
        failure_summary = (
            f"報告包含 {len(report.errors)} 個驗證錯誤；詳細原因請展開技術細節。"
            if report.errors
            else "報告與目前狀態的完整性綁定失效；詳細原因請展開技術細節。"
        )
        human_first_html = f'''<section class="human-first"><div class="eyebrow">安全提示</div>
      <h2>報告驗證失敗，請勿依此行動</h2>
      <p><strong>研究狀態:</strong> 驗證未通過</p>
      <p><strong>建議:</strong> 驗證未通過，暫不作建議</p>
      <p class="decision-text">{_escape(failure_summary)}</p>
      <h3>安全下一步</h3><p>修正驗證問題後重新產生報告</p></section>'''
    else:
        if report.tier_contract_met:
            fallback_action = first_safe_action_html
        elif shortfall_technical_status == "EVIDENCE_INSUFFICIENT":
            fallback_action = (
                '<article class="safe-action"><h3>補上一個可直接查核的來源後再評估</h3>'
                '<p>可逆：是</p></article>'
            )
        else:
            fallback_action = (
                '<article class="safe-action"><h3>補齊交付要件後重新產生報告</h3>'
                '<p>可逆：是</p></article>'
            )
        human_first_html = f'''<section class="human-first"><div class="eyebrow">研究建議</div><h2>{_escape(recommendation)}</h2>
      <p><strong>研究狀態:</strong> {_escape(human_status)}</p>
      <div class="decision"><div class="eyebrow">有界結論</div><h3>結論</h3>
      <p class="decision-text">{_escape(summary.get("decision", "尚未記錄結論"))}</p>
      </div><h3>核心理由</h3>{_render_human_reasons(state)}
      <h3>限制與翻轉條件</h3>{_human_limitations(state, shortfall_technical_status == "EVIDENCE_INSUFFICIENT" and not report.tier_contract_met)}
      <h3>下一步</h3>{fallback_action}</section>'''

    return f"""<!doctype html>
<html lang="zh-Hant-TW">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta data-state-sha256="{canonical_hash}" content="canonical-state-binding">
  <title>研究工作階段 {_escape(state.get("session", {}).get("id"))}</title>
  <style>
    :root {{ --ink:#18201f; --muted:#60706b; --paper:#f4f0e6; --panel:#fffdf7;
      --line:#c8c0ad; --accent:#a33b20; --forest:#21564a; --gold:#c49335; --bad:#8d2118; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:
      radial-gradient(circle at 9% 4%, #e7d8b5 0, transparent 28rem),
      linear-gradient(135deg, #f8f4e9, var(--paper));
      font-family:"Noto Serif TC","PingFang TC","Songti TC","Iowan Old Style","Palatino Linotype",Georgia,serif; line-height:1.55; }}
    body::before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:.22;
      background-image:repeating-linear-gradient(90deg, transparent 0 79px, #998d7330 80px); }}
    main,header {{ position:relative; width:min(1120px,calc(100% - 32px)); margin:auto; }}
    header {{ padding:64px 0 32px; border-bottom:2px solid var(--ink); }}
    .eyebrow {{ text-transform:uppercase; letter-spacing:.18em; font:700 12px/1.2 Georgia,serif; color:var(--accent); }}
    h1 {{ margin:.25rem 0 .5rem; font-size:clamp(2.5rem,7vw,5.8rem); line-height:.92; max-width:13ch; }}
    h2 {{ margin:0 0 1.25rem; font-size:clamp(1.65rem,3vw,2.5rem); }}
    h3 {{ margin:.45rem 0; }}
    .status-line {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:22px; }}
    .verdict {{ border:2px solid currentColor; padding:6px 11px; font-weight:800; letter-spacing:.08em; }}
    .verdict.pass {{ color:var(--forest); }} .verdict.invalid {{ color:var(--bad); }}
    .verdict.partial {{ color:#78530c; }} .verdict.blocked {{ color:var(--bad); }}
    .hash {{ color:var(--muted); word-break:break-all; font:12px/1.4 Menlo,Consolas,monospace; }}
    main {{ padding:24px 0 80px; display:grid; gap:18px; }}
    section {{ background:color-mix(in srgb,var(--panel) 94%,transparent); border:1px solid var(--line);
      padding:clamp(22px,4vw,44px); box-shadow:0 14px 38px #4e46351a; }}
    .decision {{ border-left:8px solid var(--accent); }}
    .decision-text {{ font-size:clamp(1.35rem,2.6vw,2rem); max-width:38ch; }}
    .human-first {{ border-left:8px solid var(--forest); }}
    .human-first h2 {{ font-size:clamp(1.8rem,4vw,3.2rem); }}
    .reason-list {{ padding-left:1.2rem; }} .reason-list li {{ margin:.55rem 0; }}
    .kernel-details {{ margin-top:4px; }}
    .meta-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; }}
    .meta-card,.verification,.safe-action {{ background:#f6f0e1; border:1px solid var(--line); padding:15px; }}
    .claim {{ padding:22px 0; border-top:1px solid var(--line); }} .claim:first-child {{ border-top:0; }}
    .claim-head {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
    .pill {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px;
      font:700 11px/1.5 Menlo,Consolas,monospace; text-transform:uppercase; }}
    .pill.critical {{ color:var(--accent); border-color:var(--accent); }}
    details {{ margin:.8rem 0; }} summary {{ cursor:pointer; font-weight:700; }}
    .evidence {{ border:1px solid var(--line); background:#fbf7ed; padding:14px 17px; }}
    .evidence-meta {{ display:flex; flex-wrap:wrap; gap:8px 20px; color:var(--muted); margin:12px 0; }}
    blockquote {{ margin:14px 0; padding:16px 20px; border-left:4px solid var(--gold); background:#efe8d8;
      white-space:pre-wrap; overflow-wrap:anywhere; }}
    .offsets,.note,.empty {{ color:var(--muted); }}
    .table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; }}
    th,td {{ text-align:left; padding:10px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:.75rem; }}
    .verification-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }}
    .issues {{ padding-left:1.2rem; }} .issues li {{ margin:.55rem 0; }} .issues .error {{ color:var(--bad); }}
    .gate-ok {{ color:var(--forest); font-weight:800; }}
    code {{ font-family:Menlo,Consolas,monospace; font-size:.86em; }}
    a {{ color:var(--forest); text-underline-offset:3px; }}
    footer {{ margin-top:20px; color:var(--muted); font-size:.85rem; }}
    @media (max-width:620px) {{ header {{ padding-top:38px; }} section {{ padding:20px; }}
      .hash {{ font-size:10px; }} th,td {{ padding:8px; }} }}
    @media print {{ body {{ background:white; }} body::before {{ display:none; }} section {{ box-shadow:none; break-inside:avoid; }} }}
  </style>
</head>
<body>
  <header>
    <div class="eyebrow">研究報告</div>
    <h1>{_escape(state.get("framing", {}).get("question", "研究結果"))}</h1>
    <div class="status-line">{_pill(public_profile, "status")}</div>
  </header>
  <main>
    {human_first_html}
    <details class="kernel-details"><summary>技術細節</summary>
    <section class="decision"><div class="eyebrow">有界結論</div><h2>結論</h2>
      <p class="decision-text">{_escape(summary.get("decision", "尚未記錄結論"))}</p>
      <p><strong>更新時間:</strong> {_escape(state.get("session", {}).get("updated_at"))}</p>
      <p><strong>status:</strong> <span class="verdict {status_class}">{_escape(display_status)}</span></p>
      <p><strong>posture:</strong> {_escape(contract.get("posture", "未記錄研究模式"))}</p></section>
    <section><h2>研究契約</h2><div class="meta-grid">
      <div class="meta-card"><strong>成本檔位</strong><br>{_escape(public_profile)}</div>
      <div class="meta-card"><strong>研究模式</strong><br>{_escape(contract.get("posture"))}</div>
      <div class="meta-card"><strong>初始搜尋路由</strong><br>{_escape(contract.get("scout_route"))}</div>
      <div class="meta-card"><strong>關鍵主張下限</strong><br>{_escape(contract.get("evidence_floor", {}).get("minimum_load_bearing_claims"))}</div>
    </div>{f'<details><summary>成本向量</summary><table><tbody>{cost_rows}</tbody></table></details>' if cost_rows else ''}
    <details><summary>實體請求上限</summary><table><tbody>{quota_rows}</tbody></table></details></section>
    <section><h2>正式主張</h2>{_render_claims(state)}</section>
    <section><h2>證據紀錄</h2>{_render_evidence(state)}</section>
    <section><h2>來源與起源</h2>{_render_sources(state)}</section>
    <section><h2>驗證</h2>{_render_verification(state)}</section>
    <section><h2>工程交接</h2>{safe_action_html}
      <h3>限制條件</h3>{_text_list(state.get("engineering_handoff", {}).get("constraints", []))}
      <h3>驗收測試</h3>{_text_list(state.get("engineering_handoff", {}).get("acceptance_tests", []))}</section>
    <section><h2>待釐清問題</h2>{_text_list(state.get("open_questions", []))}</section>
    <section><h2>決定性檢查結果</h2>
      <p><strong>integrity_ok:</strong> {_boolean_label(report.integrity_ok)}</p>
      <p><strong>tier_contract_met:</strong> {_boolean_label(report.tier_contract_met)}</p>
      <p><strong>human_recommendation:</strong> {_escape(organizer_recommendation)}</p>
      {_render_validation(report)}</section>
    <p class="hash">state sha256 {canonical_hash}</p></details>
    <footer>本報告只從唯一正式 JSON 狀態決定性產生，不含模型撰寫的第二層報告、JavaScript 或遠端資產。</footer>
  </main>
</body>
</html>
"""


def _render_loaded_session_unlocked(
    session_dir: Path,
    state: dict[str, Any],
    validation: ValidationReport,
) -> RenderedReport:
    state_hash = state_sha256(state)
    payload = render_html(state, validation).encode("utf-8")
    report_hash = hashlib.sha256(payload).hexdigest()
    report_path = session_dir / "report.html"
    _atomic_write_bytes_unlocked(report_path, payload)
    _append_event_unlocked(
        session_dir,
        {
            "event": "report_generated",
            "at": state["session"]["updated_at"],
            "state_sha256": state_hash,
            "report_sha256": report_hash,
        },
    )
    return RenderedReport(report_path, validation, state_hash, report_hash)


def render_session_result(session_dir: Path) -> RenderedReport:
    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, event_errors = _read_events_unlocked(session_dir)
        validation = _validate_loaded_session(
            session_dir, state, events, event_errors, check_report=False
        )
        return _render_loaded_session_unlocked(session_dir, state, validation)


def finalize_session_result(session_dir: Path, now: str) -> RenderedReport:
    """Seal a sound-but-undeliverable status and render it under one session lock."""

    session_dir = Path(session_dir)
    with session_lock(session_dir):
        _recover_session_unlocked(session_dir)
        state = _load_state_unlocked(session_dir)
        events, event_errors = _read_events_unlocked(session_dir)
        validation = _validate_loaded_session(
            session_dir, state, events, event_errors, check_report=False
        )
        exhausted_classes = sorted(
            {
                event.get("cost_class")
                for event in events
                if event.get("event") == "budget_exhausted"
                and event.get("cost_class") in {"deep", "search"}
            }
        )
        existing_gap_ids = {
            item.get("id")
            for item in state.get("open_questions", [])
            if isinstance(item, dict)
        }
        budget_gap_operations = [
            {
                "op": "add",
                "path": "/open_questions/-",
                "value": {
                    "id": f"budget-exhausted-{cost_class}",
                    "question": (
                        f"{cost_class} 類外呼預算已用盡；未解缺口僅以現有材料交付，"
                        "需增加預算或下次重跑才能補強。"
                    ),
                },
            }
            for cost_class in exhausted_classes
            if f"budget-exhausted-{cost_class}" not in existing_gap_ids
        ]
        if budget_gap_operations:
            state = _commit_patch_unlocked(
                session_dir,
                budget_gap_operations,
                state["session"]["revision"],
                now,
                ORGANIZER_ROOTS,
                "organizer",
            )
            events, event_errors = _read_events_unlocked(session_dir)
            validation = _validate_loaded_session(
                session_dir, state, events, event_errors, check_report=False
            )
        if (
            validation.integrity_ok and not validation.ok
        ):
            seal_human_status, _ = tier_shortfall_labels(validation.issues)
            operations = []
            if state["summary"].get("status") != "BLOCKED":
                operations.append(
                    {"op": "replace", "path": "/summary/status", "value": "BLOCKED"}
                )
            if state["summary"].get("human_status") != seal_human_status:
                operations.append(
                    {
                        "op": "replace",
                        "path": "/summary/human_status",
                        "value": seal_human_status,
                    }
                )
            if operations:
                state = _commit_patch_unlocked(
                    session_dir,
                    operations,
                    state["session"]["revision"],
                    now,
                    ORGANIZER_ROOTS,
                    "organizer",
                )
                events, event_errors = _read_events_unlocked(session_dir)
                validation = _validate_loaded_session(
                    session_dir, state, events, event_errors, check_report=False
                )
        return _render_loaded_session_unlocked(session_dir, state, validation)
